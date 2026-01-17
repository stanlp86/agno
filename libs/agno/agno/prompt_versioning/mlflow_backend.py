"""
MLflow backend for prompt versioning storage.

This module provides MLflow integration for:
- Storing prompts as MLflow artifacts
- Tracking versions using MLflow runs
- Managing experiments for prompt lineages
- Tagging and searching prompts
"""

import json
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from agno.prompt_versioning.models import (
    PromptComponentType,
    PromptDiff,
    PromptLineage,
    PromptMetadata,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
    SystemPromptComponent,
)

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    from mlflow.entities import ViewType

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None
    MlflowClient = None


class MLflowConfig(BaseModel):
    """Configuration for MLflow backend."""

    tracking_uri: str = Field(
        default="mlruns",
        description="MLflow tracking URI (local path or server URL)"
    )
    experiment_prefix: str = Field(
        default="prompt_versioning",
        description="Prefix for experiment names"
    )
    artifact_path: str = Field(
        default="prompts",
        description="Path within run artifacts for prompt files"
    )


class MLflowPromptStore:
    """
    MLflow-backed storage for prompt versions.

    Uses MLflow experiments to organize prompts by name, and runs to track versions.
    Each prompt version is stored as:
    - Run parameters: metadata, status, parent info
    - Run metrics: version number
    - Run artifacts: prompt content as JSON file
    - Run tags: for searching and filtering
    """

    def __init__(
        self,
        tracking_uri: str = "mlruns",
        experiment_prefix: str = "prompt_versioning",
    ):
        """
        Initialize MLflow prompt store.

        Args:
            tracking_uri: MLflow tracking URI
            experiment_prefix: Prefix for experiment names
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError(
                "MLflow is required for MLflowPromptStore. "
                "Install it with: pip install mlflow"
            )

        self.config = MLflowConfig(
            tracking_uri=tracking_uri,
            experiment_prefix=experiment_prefix,
        )

        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri)
        self._experiment_cache: Dict[str, str] = {}

    def _get_experiment_name(self, prompt_name: str) -> str:
        """Get experiment name for a prompt."""
        return f"{self.config.experiment_prefix}/{prompt_name}"

    def _get_or_create_experiment(self, prompt_name: str) -> str:
        """Get or create MLflow experiment for a prompt."""
        exp_name = self._get_experiment_name(prompt_name)

        if exp_name in self._experiment_cache:
            return self._experiment_cache[exp_name]

        experiment = self.client.get_experiment_by_name(exp_name)
        if experiment is None:
            exp_id = self.client.create_experiment(exp_name)
        else:
            exp_id = experiment.experiment_id

        self._experiment_cache[exp_name] = exp_id
        return exp_id

    def _prompt_to_artifact(self, prompt: PromptVersion) -> Dict[str, Any]:
        """
        Convert prompt to artifact dict.

        Includes component serialization for system prompts.
        Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 5.2
        """
        data = {
            "id": prompt.id,
            "name": prompt.name,
            "version": prompt.version,
            "content": prompt.template.content,
            "variables": list(prompt.template.variables),
            "status": prompt.status.value,
            "metadata": prompt.metadata.model_dump(),
            "parent_id": prompt.parent_id,
            "forked_from": prompt.forked_from,
            "created_at": prompt.created_at.isoformat(),
            "updated_at": prompt.updated_at.isoformat(),
            "snapshot_name": prompt.snapshot_name,
            "content_hash": prompt.content_hash,
        }

        # Include components if present (system prompts)
        if prompt.components:
            data["components"] = [c.model_dump() for c in prompt.components]

        # Include change description for traceability
        if prompt.change_description:
            data["change_description"] = prompt.change_description

        return data

    def _artifact_to_prompt(self, data: Dict[str, Any]) -> PromptVersion:
        """
        Convert artifact dict to prompt.

        Includes component deserialization for system prompts.
        Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 5.2
        """
        # Load components if present
        components = None
        if "components" in data and data["components"]:
            components = [
                SystemPromptComponent(**c) for c in data["components"]
            ]

        return PromptVersion(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            template=PromptTemplate(content=data["content"]),
            status=PromptStatus(data["status"]),
            metadata=PromptMetadata(**data["metadata"]),
            parent_id=data.get("parent_id"),
            forked_from=data.get("forked_from"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            snapshot_name=data.get("snapshot_name"),
            components=components,
            change_description=data.get("change_description"),
        )

    def save(self, prompt: PromptVersion) -> str:
        """
        Save a prompt version to MLflow.

        Args:
            prompt: The prompt version to save

        Returns:
            The MLflow run ID
        """
        exp_id = self._get_or_create_experiment(prompt.name)

        with mlflow.start_run(experiment_id=exp_id) as run:
            # Log parameters
            mlflow.log_param("prompt_id", prompt.id)
            mlflow.log_param("prompt_name", prompt.name)
            mlflow.log_param("status", prompt.status.value)
            mlflow.log_param("content_hash", prompt.content_hash)

            if prompt.parent_id:
                mlflow.log_param("parent_id", prompt.parent_id)
            if prompt.forked_from:
                mlflow.log_param("forked_from", prompt.forked_from)
            if prompt.snapshot_name:
                mlflow.log_param("snapshot_name", prompt.snapshot_name)

            # Log metadata as params
            if prompt.metadata.author:
                mlflow.log_param("author", prompt.metadata.author)
            if prompt.metadata.description:
                mlflow.log_param("description", prompt.metadata.description[:250])
            if prompt.metadata.tags:
                mlflow.log_param("tags", ",".join(prompt.metadata.tags))

            # Log metrics
            mlflow.log_metric("version", prompt.version)
            mlflow.log_metric("variable_count", len(prompt.variables))
            mlflow.log_metric("content_length", len(prompt.content))

            # Set tags for searching
            mlflow.set_tag("prompt_id", prompt.id)
            mlflow.set_tag("prompt_name", prompt.name)
            mlflow.set_tag("version", str(prompt.version))
            mlflow.set_tag("status", prompt.status.value)
            if prompt.snapshot_name:
                mlflow.set_tag("snapshot", prompt.snapshot_name)
            if prompt.forked_from:
                mlflow.set_tag("is_fork", "true")
            for tag in prompt.metadata.tags:
                mlflow.set_tag(f"tag_{tag}", "true")

            # Save prompt as artifact
            artifact_data = self._prompt_to_artifact(prompt)
            with tempfile.TemporaryDirectory() as tmpdir:
                artifact_file = os.path.join(tmpdir, "prompt.json")
                with open(artifact_file, "w") as f:
                    json.dump(artifact_data, f, indent=2)
                mlflow.log_artifact(artifact_file, self.config.artifact_path)

            return run.info.run_id

    def load(self, prompt_id: str) -> Optional[PromptVersion]:
        """
        Load a prompt version by ID.

        Args:
            prompt_id: The prompt ID to load

        Returns:
            PromptVersion if found, None otherwise
        """
        # Search across all experiments
        runs = self.client.search_runs(
            experiment_ids=self._get_all_experiment_ids(),
            filter_string=f"tags.prompt_id = '{prompt_id}'",
            max_results=1,
        )

        if not runs:
            return None

        return self._load_from_run(runs[0])

    def load_by_name(
        self,
        name: str,
        version: Optional[int] = None,
    ) -> Optional[PromptVersion]:
        """
        Load a prompt by name and optional version.

        Args:
            name: Prompt name
            version: Specific version number (latest if None)

        Returns:
            PromptVersion if found, None otherwise
        """
        exp_name = self._get_experiment_name(name)
        experiment = self.client.get_experiment_by_name(exp_name)

        if experiment is None:
            return None

        if version is not None:
            filter_str = f"tags.version = '{version}'"
        else:
            filter_str = ""

        runs = self.client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=filter_str,
            order_by=["metrics.version DESC"],
            max_results=1,
        )

        if not runs:
            return None

        return self._load_from_run(runs[0])

    def load_snapshot(self, name: str, snapshot_name: str) -> Optional[PromptVersion]:
        """
        Load a specific snapshot by name.

        Args:
            name: Prompt name
            snapshot_name: Snapshot name

        Returns:
            PromptVersion if found, None otherwise
        """
        exp_name = self._get_experiment_name(name)
        experiment = self.client.get_experiment_by_name(exp_name)

        if experiment is None:
            return None

        runs = self.client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=f"tags.snapshot = '{snapshot_name}'",
            max_results=1,
        )

        if not runs:
            return None

        return self._load_from_run(runs[0])

    def _load_from_run(self, run) -> PromptVersion:
        """Load prompt from MLflow run."""
        artifact_uri = f"{run.info.artifact_uri}/{self.config.artifact_path}/prompt.json"

        # Handle local and remote URIs
        if artifact_uri.startswith("file://"):
            artifact_path = artifact_uri[7:]
        elif artifact_uri.startswith("/") or artifact_uri[1:3] == ":\\":
            artifact_path = artifact_uri
        else:
            # Download artifact for remote tracking servers
            local_path = self.client.download_artifacts(
                run.info.run_id,
                f"{self.config.artifact_path}/prompt.json",
            )
            artifact_path = local_path

        with open(artifact_path, "r") as f:
            data = json.load(f)

        return self._artifact_to_prompt(data)

    def _get_all_experiment_ids(self) -> List[str]:
        """Get all experiment IDs for prompt versioning."""
        experiments = self.client.search_experiments(
            filter_string=f"name LIKE '{self.config.experiment_prefix}/%'",
        )
        return [exp.experiment_id for exp in experiments]

    def list_prompts(self) -> List[str]:
        """List all prompt names."""
        experiments = self.client.search_experiments(
            filter_string=f"name LIKE '{self.config.experiment_prefix}/%'",
        )
        prefix_len = len(self.config.experiment_prefix) + 1
        return [exp.name[prefix_len:] for exp in experiments]

    def list_versions(self, name: str) -> List[PromptVersion]:
        """
        List all versions of a prompt.

        Args:
            name: Prompt name

        Returns:
            List of all versions sorted by version number
        """
        exp_name = self._get_experiment_name(name)
        experiment = self.client.get_experiment_by_name(exp_name)

        if experiment is None:
            return []

        runs = self.client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["metrics.version ASC"],
        )

        return [self._load_from_run(run) for run in runs]

    def list_snapshots(self, name: str) -> List[Tuple[str, PromptVersion]]:
        """
        List all snapshots for a prompt.

        Args:
            name: Prompt name

        Returns:
            List of (snapshot_name, prompt_version) tuples
        """
        exp_name = self._get_experiment_name(name)
        experiment = self.client.get_experiment_by_name(exp_name)

        if experiment is None:
            return []

        runs = self.client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string="tags.snapshot != ''",
        )

        result = []
        for run in runs:
            prompt = self._load_from_run(run)
            if prompt.snapshot_name:
                result.append((prompt.snapshot_name, prompt))

        return result

    def search(
        self,
        name_pattern: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[PromptStatus] = None,
        author: Optional[str] = None,
        include_forks: bool = True,
    ) -> List[PromptVersion]:
        """
        Search for prompts matching criteria.

        Args:
            name_pattern: Pattern to match prompt names
            tags: Tags that must be present
            status: Status filter
            author: Author filter
            include_forks: Whether to include forked prompts

        Returns:
            List of matching prompts
        """
        filter_parts = []

        if status:
            filter_parts.append(f"tags.status = '{status.value}'")
        if author:
            filter_parts.append(f"params.author = '{author}'")
        if not include_forks:
            filter_parts.append("tags.is_fork != 'true'")
        if tags:
            for tag in tags:
                filter_parts.append(f"tags.tag_{tag} = 'true'")

        filter_string = " AND ".join(filter_parts) if filter_parts else ""

        # Get relevant experiment IDs
        if name_pattern:
            experiments = self.client.search_experiments(
                filter_string=f"name LIKE '{self.config.experiment_prefix}/{name_pattern}%'",
            )
            exp_ids = [exp.experiment_id for exp in experiments]
        else:
            exp_ids = self._get_all_experiment_ids()

        if not exp_ids:
            return []

        runs = self.client.search_runs(
            experiment_ids=exp_ids,
            filter_string=filter_string,
            order_by=["metrics.version DESC"],
        )

        return [self._load_from_run(run) for run in runs]

    def get_lineage(self, name: str) -> PromptLineage:
        """
        Get the full lineage for a prompt.

        Args:
            name: Prompt name

        Returns:
            PromptLineage with all versions and metadata
        """
        versions = self.list_versions(name)

        if not versions:
            raise ValueError(f"No prompt found with name: {name}")

        root = versions[0]
        snapshots = {}
        forks = []

        for v in versions:
            if v.snapshot_name:
                snapshots[v.snapshot_name] = v.id
            if v.forked_from:
                forks.append(v.id)

        return PromptLineage(
            root_id=root.id,
            name=name,
            versions=versions,
            forks=forks,
            snapshots=snapshots,
        )

    def delete(self, prompt_id: str) -> bool:
        """
        Delete a prompt version.

        Args:
            prompt_id: The prompt ID to delete

        Returns:
            True if deleted, False if not found
        """
        runs = self.client.search_runs(
            experiment_ids=self._get_all_experiment_ids(),
            filter_string=f"tags.prompt_id = '{prompt_id}'",
            max_results=1,
        )

        if not runs:
            return False

        self.client.delete_run(runs[0].info.run_id)
        return True

    def get_next_version(self, name: str) -> int:
        """
        Get the next version number for a prompt.

        Args:
            name: Prompt name

        Returns:
            Next version number (1 if no versions exist)
        """
        latest = self.load_by_name(name)
        if latest is None:
            return 1
        return latest.version + 1

    def compare(
        self,
        prompt_id_1: str,
        prompt_id_2: str,
    ) -> PromptDiff:
        """
        Compare two prompt versions.

        Args:
            prompt_id_1: First prompt ID
            prompt_id_2: Second prompt ID

        Returns:
            PromptDiff with changes
        """
        p1 = self.load(prompt_id_1)
        p2 = self.load(prompt_id_2)

        if p1 is None:
            raise ValueError(f"Prompt not found: {prompt_id_1}")
        if p2 is None:
            raise ValueError(f"Prompt not found: {prompt_id_2}")

        return PromptDiff.compute(p1, p2)


def generate_prompt_id() -> str:
    """Generate a unique prompt ID."""
    return f"prompt_{uuid.uuid4().hex[:12]}"
