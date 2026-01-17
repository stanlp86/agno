"""
High-level Prompt Manager for versioning, snapshots, editing, and forking.

This is the main API for interacting with the prompt versioning system.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from agno.prompt_versioning.models import (
    PromptDiff,
    PromptLineage,
    PromptMetadata,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
)
from agno.prompt_versioning.mlflow_backend import (
    MLflowPromptStore,
    generate_prompt_id,
)


class PromptManager:
    """
    High-level manager for prompt versioning operations.

    Provides a clean API for:
    - Creating new prompts
    - Editing prompts (creates new versions)
    - Creating snapshots (named versions)
    - Forking prompts (creating new prompts from existing ones)
    - Searching and listing prompts
    - Comparing versions

    Example:
        >>> manager = PromptManager(tracking_uri="mlruns")
        >>> prompt = manager.create(
        ...     name="greeting",
        ...     content="Hello, {{name}}! Welcome to {{app}}.",
        ...     description="A friendly greeting prompt"
        ... )
        >>> print(prompt.render(name="Alice", app="Agno"))
        Hello, Alice! Welcome to Agno.
        >>> # Edit the prompt (creates v2)
        >>> prompt = manager.edit(prompt.id, content="Hi {{name}}, welcome!")
        >>> # Create a snapshot for production
        >>> snapshot = manager.snapshot(prompt.id, "production-v1")
        >>> # Fork for experimentation
        >>> fork = manager.fork(prompt.id, "greeting_experimental")
    """

    def __init__(
        self,
        tracking_uri: str = "mlruns",
        experiment_prefix: str = "prompt_versioning",
    ):
        """
        Initialize the PromptManager.

        Args:
            tracking_uri: MLflow tracking URI (local path or server URL)
            experiment_prefix: Prefix for MLflow experiments
        """
        self.store = MLflowPromptStore(
            tracking_uri=tracking_uri,
            experiment_prefix=experiment_prefix,
        )

    def create(
        self,
        name: str,
        content: str,
        description: Optional[str] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        model_compatibility: Optional[List[str]] = None,
        use_case: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptVersion:
        """
        Create a new prompt.

        Args:
            name: Unique name for the prompt (alphanumeric, underscores, hyphens, dots)
            content: The prompt template content (use {{variable}} for placeholders)
            description: Description of the prompt's purpose
            author: Author name
            tags: List of tags for categorization
            model_compatibility: List of compatible model identifiers
            use_case: Intended use case description
            custom_metadata: Additional custom metadata

        Returns:
            The created PromptVersion

        Example:
            >>> prompt = manager.create(
            ...     name="summarizer",
            ...     content="Summarize the following text: {{text}}",
            ...     description="Text summarization prompt",
            ...     tags=["summarization", "text-processing"]
            ... )
        """
        prompt_id = generate_prompt_id()
        version = self.store.get_next_version(name)

        metadata = PromptMetadata(
            author=author,
            description=description,
            tags=tags or [],
            model_compatibility=model_compatibility or [],
            use_case=use_case,
            custom=custom_metadata or {},
        )

        prompt = PromptVersion(
            id=prompt_id,
            name=name,
            version=version,
            template=PromptTemplate(content=content),
            status=PromptStatus.DRAFT,
            metadata=metadata,
        )

        self.store.save(prompt)
        return prompt

    def edit(
        self,
        prompt_id: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        model_compatibility: Optional[List[str]] = None,
        use_case: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
        status: Optional[PromptStatus] = None,
    ) -> PromptVersion:
        """
        Edit a prompt, creating a new version.

        This creates a new version with the changes while preserving lineage.

        Args:
            prompt_id: ID of the prompt to edit
            content: New content (uses existing if not provided)
            description: New description
            author: New author
            tags: New tags (replaces existing)
            model_compatibility: New compatibility list
            use_case: New use case
            custom_metadata: New custom metadata (merged with existing)
            status: New status

        Returns:
            The new PromptVersion

        Example:
            >>> updated = manager.edit(
            ...     prompt.id,
            ...     content="Please summarize: {{text}}\n\nBe concise.",
            ...     tags=["summarization", "concise"]
            ... )
        """
        existing = self.store.load(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        # Build new metadata
        new_metadata = PromptMetadata(
            author=author if author is not None else existing.metadata.author,
            description=description if description is not None else existing.metadata.description,
            tags=tags if tags is not None else existing.metadata.tags,
            model_compatibility=(
                model_compatibility if model_compatibility is not None
                else existing.metadata.model_compatibility
            ),
            use_case=use_case if use_case is not None else existing.metadata.use_case,
            custom={
                **existing.metadata.custom,
                **(custom_metadata or {}),
            },
        )

        # Create new version
        new_version = self.store.get_next_version(existing.name)
        new_id = generate_prompt_id()

        prompt = PromptVersion(
            id=new_id,
            name=existing.name,
            version=new_version,
            template=PromptTemplate(
                content=content if content is not None else existing.content
            ),
            status=status if status is not None else PromptStatus.DRAFT,
            metadata=new_metadata,
            parent_id=existing.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.store.save(prompt)
        return prompt

    def snapshot(
        self,
        prompt_id: str,
        snapshot_name: str,
        description: Optional[str] = None,
    ) -> PromptVersion:
        """
        Create a named snapshot of a prompt version.

        Snapshots are immutable copies that can be referenced by name.
        Useful for marking production-ready versions.

        Args:
            prompt_id: ID of the prompt to snapshot
            snapshot_name: Name for the snapshot (e.g., "production-v1", "release-2024-01")
            description: Optional description for this snapshot

        Returns:
            The snapshot PromptVersion

        Example:
            >>> snapshot = manager.snapshot(
            ...     prompt.id,
            ...     "production-v1",
            ...     description="Approved for production use"
            ... )
        """
        existing = self.store.load(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        # Check if snapshot name already exists
        existing_snapshot = self.store.load_snapshot(existing.name, snapshot_name)
        if existing_snapshot is not None:
            raise ValueError(
                f"Snapshot '{snapshot_name}' already exists for prompt '{existing.name}'"
            )

        # Create snapshot version
        new_version = self.store.get_next_version(existing.name)
        new_id = generate_prompt_id()

        metadata = existing.metadata.model_copy()
        if description:
            metadata.description = description

        snapshot = PromptVersion(
            id=new_id,
            name=existing.name,
            version=new_version,
            template=PromptTemplate(content=existing.content),
            status=PromptStatus.SNAPSHOT,
            metadata=metadata,
            parent_id=existing.id,
            snapshot_name=snapshot_name,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.store.save(snapshot)
        return snapshot

    def fork(
        self,
        prompt_id: str,
        new_name: str,
        description: Optional[str] = None,
        author: Optional[str] = None,
    ) -> PromptVersion:
        """
        Fork a prompt to create a new independent prompt.

        The forked prompt starts at version 1 with its own lineage,
        but maintains a reference to the original.

        Args:
            prompt_id: ID of the prompt to fork
            new_name: Name for the forked prompt
            description: Description for the fork
            author: Author of the fork

        Returns:
            The new forked PromptVersion

        Example:
            >>> fork = manager.fork(
            ...     prompt.id,
            ...     "summarizer_verbose",
            ...     description="A more verbose summarization prompt"
            ... )
        """
        existing = self.store.load(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        # Check if new name already exists
        if self.store.load_by_name(new_name) is not None:
            raise ValueError(f"Prompt with name '{new_name}' already exists")

        new_id = generate_prompt_id()

        # Copy metadata with optional overrides
        metadata = existing.metadata.model_copy()
        if description:
            metadata.description = description
        if author:
            metadata.author = author
        metadata.add_tag("forked")

        fork = PromptVersion(
            id=new_id,
            name=new_name,
            version=1,
            template=PromptTemplate(content=existing.content),
            status=PromptStatus.DRAFT,
            metadata=metadata,
            forked_from=existing.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.store.save(fork)
        return fork

    def get(self, prompt_id: str) -> Optional[PromptVersion]:
        """
        Get a prompt by ID.

        Args:
            prompt_id: The prompt ID

        Returns:
            PromptVersion if found, None otherwise
        """
        return self.store.load(prompt_id)

    def get_by_name(
        self,
        name: str,
        version: Optional[int] = None,
    ) -> Optional[PromptVersion]:
        """
        Get a prompt by name and optional version.

        Args:
            name: Prompt name
            version: Version number (latest if not specified)

        Returns:
            PromptVersion if found, None otherwise
        """
        return self.store.load_by_name(name, version)

    def get_snapshot(self, name: str, snapshot_name: str) -> Optional[PromptVersion]:
        """
        Get a named snapshot.

        Args:
            name: Prompt name
            snapshot_name: Snapshot name

        Returns:
            PromptVersion if found, None otherwise
        """
        return self.store.load_snapshot(name, snapshot_name)

    def list_prompts(self) -> List[str]:
        """
        List all prompt names.

        Returns:
            List of prompt names
        """
        return self.store.list_prompts()

    def list_versions(self, name: str) -> List[PromptVersion]:
        """
        List all versions of a prompt.

        Args:
            name: Prompt name

        Returns:
            List of versions sorted by version number
        """
        return self.store.list_versions(name)

    def list_snapshots(self, name: str) -> List[tuple]:
        """
        List all snapshots for a prompt.

        Args:
            name: Prompt name

        Returns:
            List of (snapshot_name, prompt_version) tuples
        """
        return self.store.list_snapshots(name)

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
        return self.store.search(
            name_pattern=name_pattern,
            tags=tags,
            status=status,
            author=author,
            include_forks=include_forks,
        )

    def get_lineage(self, name: str) -> PromptLineage:
        """
        Get the full lineage for a prompt.

        Args:
            name: Prompt name

        Returns:
            PromptLineage with all versions and history
        """
        return self.store.get_lineage(name)

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
            PromptDiff with all changes
        """
        return self.store.compare(prompt_id_1, prompt_id_2)

    def delete(self, prompt_id: str) -> bool:
        """
        Delete a prompt version.

        Args:
            prompt_id: The prompt ID to delete

        Returns:
            True if deleted, False if not found
        """
        return self.store.delete(prompt_id)

    def activate(self, prompt_id: str) -> PromptVersion:
        """
        Set a prompt's status to ACTIVE.

        Args:
            prompt_id: The prompt ID

        Returns:
            Updated prompt version
        """
        return self.edit(prompt_id, status=PromptStatus.ACTIVE)

    def archive(self, prompt_id: str) -> PromptVersion:
        """
        Set a prompt's status to ARCHIVED.

        Args:
            prompt_id: The prompt ID

        Returns:
            Updated prompt version
        """
        return self.edit(prompt_id, status=PromptStatus.ARCHIVED)

    def render(
        self,
        prompt_id: Optional[str] = None,
        name: Optional[str] = None,
        version: Optional[int] = None,
        snapshot_name: Optional[str] = None,
        **variables: Any,
    ) -> str:
        """
        Render a prompt template with variables.

        Provide one of: prompt_id, name (with optional version), or name with snapshot_name.

        Args:
            prompt_id: Direct prompt ID
            name: Prompt name
            version: Version number (used with name)
            snapshot_name: Snapshot name (used with name)
            **variables: Variables to substitute in template

        Returns:
            Rendered prompt string

        Example:
            >>> result = manager.render(
            ...     name="greeting",
            ...     snapshot_name="production-v1",
            ...     name="Alice",
            ...     app="Agno"
            ... )
        """
        prompt = None

        if prompt_id:
            prompt = self.get(prompt_id)
        elif name and snapshot_name:
            prompt = self.get_snapshot(name, snapshot_name)
        elif name:
            prompt = self.get_by_name(name, version)

        if prompt is None:
            raise ValueError("Prompt not found")

        return prompt.render(**variables)

    def duplicate(
        self,
        prompt_id: str,
        new_name: Optional[str] = None,
    ) -> PromptVersion:
        """
        Duplicate a prompt as v1 of a new or same name.

        If new_name is not provided, creates a copy with suffix "_copy".

        Args:
            prompt_id: ID of prompt to duplicate
            new_name: Optional new name

        Returns:
            The duplicated prompt
        """
        existing = self.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        target_name = new_name or f"{existing.name}_copy"
        return self.fork(prompt_id, target_name)

    def export_lineage(self, name: str) -> Dict[str, Any]:
        """
        Export the full lineage of a prompt as a dictionary.

        Useful for backup, migration, or documentation.

        Args:
            name: Prompt name

        Returns:
            Dictionary with full lineage data
        """
        lineage = self.get_lineage(name)
        return {
            "name": lineage.name,
            "root_id": lineage.root_id,
            "versions": [
                {
                    "id": v.id,
                    "version": v.version,
                    "content": v.content,
                    "variables": list(v.variables),
                    "status": v.status.value,
                    "metadata": v.metadata.model_dump(),
                    "parent_id": v.parent_id,
                    "forked_from": v.forked_from,
                    "snapshot_name": v.snapshot_name,
                    "created_at": v.created_at.isoformat(),
                    "content_hash": v.content_hash,
                }
                for v in lineage.versions
            ],
            "snapshots": lineage.snapshots,
            "forks": lineage.forks,
        }
