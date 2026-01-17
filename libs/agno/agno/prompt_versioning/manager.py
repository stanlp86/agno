"""
High-level Prompt Manager for versioning, snapshots, editing, and forking.

This is the main API for interacting with the prompt versioning system.
Supports both traditional prompts and component-based system prompts.

Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 4.1
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

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

        # Deep copy components if present (for system prompts)
        components = None
        if existing.components:
            components = [
                SystemPromptComponent(**c.model_dump())
                for c in existing.components
            ]

        fork = PromptVersion(
            id=new_id,
            name=new_name,
            version=1,
            template=PromptTemplate(content=existing.content),
            status=PromptStatus.DRAFT,
            metadata=metadata,
            forked_from=existing.id,
            components=components,
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
        prompt_name: Optional[str] = None,
        version: Optional[int] = None,
        snapshot_name: Optional[str] = None,
        **variables: Any,
    ) -> str:
        """
        Render a prompt template with variables.

        Provide one of: prompt_id, prompt_name (with optional version), or prompt_name with snapshot_name.

        Args:
            prompt_id: Direct prompt ID
            prompt_name: Prompt name (use this instead of 'name' to avoid conflicts with template variables)
            version: Version number (used with prompt_name)
            snapshot_name: Snapshot name (used with prompt_name)
            **variables: Variables to substitute in template

        Returns:
            Rendered prompt string

        Example:
            >>> result = manager.render(
            ...     prompt_name="greeting",
            ...     snapshot_name="production-v1",
            ...     name="Alice",
            ...     app="Agno"
            ... )
        """
        prompt = None

        if prompt_id:
            prompt = self.get(prompt_id)
        elif prompt_name and snapshot_name:
            prompt = self.get_snapshot(prompt_name, snapshot_name)
        elif prompt_name:
            prompt = self.get_by_name(prompt_name, version)

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

    # =========================================================================
    # SYSTEM PROMPT COMPONENT METHODS
    # Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 4.1
    # =========================================================================

    def create_system_prompt(
        self,
        name: str,
        components: List[SystemPromptComponent],
        description: Optional[str] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        model_compatibility: Optional[List[str]] = None,
    ) -> PromptVersion:
        """
        Create a new system prompt from components.

        Args:
            name: Unique prompt name
            components: List of SystemPromptComponent objects
            description: Human-readable description
            author: Author name
            tags: Tags for categorization
            model_compatibility: Compatible models

        Returns:
            Created PromptVersion with components

        Raises:
            ValueError: If duplicate non-CUSTOM component types

        Example:
            >>> components = [
            ...     SystemPromptComponent(
            ...         type=PromptComponentType.ROLE,
            ...         content="You are a helpful assistant.",
            ...         xml_tag="your_role"
            ...     ),
            ...     SystemPromptComponent(
            ...         type=PromptComponentType.INSTRUCTIONS,
            ...         content="Be concise and accurate.",
            ...         xml_tag="instructions"
            ...     ),
            ... ]
            >>> prompt = manager.create_system_prompt("my_agent", components)
        """
        # Validate no duplicate non-CUSTOM components
        self._validate_components(components)

        # Compose content from components
        content = self._compose_components(components)

        # Build tags including system_prompt marker
        # Note: Using underscores instead of colons to avoid MLflow search syntax issues
        all_tags = list(tags or [])
        all_tags.append("system_prompt")
        for comp in components:
            if comp.type == PromptComponentType.CUSTOM:
                all_tags.append(f"component_custom_{comp.name}")
            else:
                all_tags.append(f"component_{comp.type.value}")

        # Create version with components
        prompt_id = generate_prompt_id()
        version_num = self.store.get_next_version(name)

        version = PromptVersion(
            id=prompt_id,
            name=name,
            version=version_num,
            template=PromptTemplate(content=content),
            status=PromptStatus.DRAFT,
            metadata=PromptMetadata(
                author=author,
                description=description,
                tags=all_tags,
                model_compatibility=model_compatibility or [],
            ),
            components=components,
        )

        self.store.save(version)
        return version

    def edit_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        new_content: str,
        component_name: Optional[str] = None,
        author: Optional[str] = None,
        change_description: Optional[str] = None,
    ) -> PromptVersion:
        """
        Edit a specific component, creating a new version.

        Args:
            prompt_id: ID of prompt to edit
            component_type: Type of component to edit
            new_content: New content
            component_name: Required for CUSTOM type
            author: Author of edit
            change_description: Description of changes for traceability

        Returns:
            New PromptVersion with updated component

        Raises:
            ValueError: If prompt not found or not a system prompt

        Note:
            The change_description is stored in the new version for
            full traceability and audit trail.

        Example:
            >>> updated = manager.edit_component(
            ...     prompt_id,
            ...     PromptComponentType.ROLE,
            ...     "New role content",
            ...     change_description="Updated role for premium support"
            ... )
        """
        existing = self.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if not existing.is_system_prompt():
            raise ValueError("Not a system prompt. Use edit() instead.")

        # Deep copy components
        components = [
            SystemPromptComponent(**c.model_dump())
            for c in existing.components
        ]

        # Find and update
        found = False
        for comp in components:
            if comp.type == component_type:
                if component_type == PromptComponentType.CUSTOM:
                    if comp.name == component_name:
                        comp.content = new_content
                        found = True
                        break
                else:
                    comp.content = new_content
                    found = True
                    break

        if not found:
            raise ValueError(f"Component not found: {component_type.value}")

        # Create new version with change description
        return self._create_component_version(
            existing,
            components=components,
            author=author,
            change_description=change_description
        )

    def add_component(
        self,
        prompt_id: str,
        component: SystemPromptComponent,
        author: Optional[str] = None,
        change_description: Optional[str] = None,
    ) -> PromptVersion:
        """
        Add a new component to a system prompt.

        Args:
            prompt_id: ID of prompt to modify
            component: Component to add
            author: Author of change
            change_description: Description of changes

        Returns:
            New PromptVersion with added component

        Raises:
            ValueError: If duplicate non-CUSTOM component type
        """
        existing = self.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if not existing.is_system_prompt():
            raise ValueError("Not a system prompt")

        # Check duplicates for non-CUSTOM
        if component.type != PromptComponentType.CUSTOM:
            for c in existing.components:
                if c.type == component.type:
                    raise ValueError(
                        f"Component {component.type.value} already exists"
                    )

        components = list(existing.components) + [component]

        desc = change_description or f"Added {component.type.value} component"
        return self._create_component_version(
            existing,
            components=components,
            author=author,
            change_description=desc
        )

    def remove_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        component_name: Optional[str] = None,
        author: Optional[str] = None,
        change_description: Optional[str] = None,
    ) -> PromptVersion:
        """
        Remove a component from a system prompt.

        Args:
            prompt_id: ID of prompt to modify
            component_type: Type of component to remove
            component_name: Required for CUSTOM type
            author: Author of change
            change_description: Description of changes

        Returns:
            New PromptVersion without the component

        Raises:
            ValueError: If component not found
        """
        existing = self.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if not existing.is_system_prompt():
            raise ValueError("Not a system prompt")

        # Filter out component
        if component_type == PromptComponentType.CUSTOM:
            components = [
                c for c in existing.components
                if not (c.type == component_type and c.name == component_name)
            ]
        else:
            components = [
                c for c in existing.components
                if c.type != component_type
            ]

        if len(components) == len(existing.components):
            raise ValueError(f"Component not found: {component_type.value}")

        desc = change_description or f"Removed {component_type.value} component"
        return self._create_component_version(
            existing,
            components=components,
            author=author,
            change_description=desc
        )

    def reorder_components(
        self,
        prompt_id: str,
        component_order: Dict[PromptComponentType, int],
        author: Optional[str] = None,
        change_description: Optional[str] = None,
    ) -> PromptVersion:
        """
        Change the order in which components are rendered.

        Args:
            prompt_id: ID of prompt to reorder
            component_order: Dict mapping component types to new order values
            author: Author of change
            change_description: Description of reordering

        Returns:
            New PromptVersion with reordered components

        Example:
            >>> manager.reorder_components(
            ...     prompt_id,
            ...     {
            ...         PromptComponentType.INSTRUCTIONS: 15,  # Move before role
            ...         PromptComponentType.ROLE: 25,
            ...     }
            ... )
        """
        existing = self.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if not existing.is_system_prompt():
            raise ValueError("Not a system prompt")

        # Deep copy and update orders
        components = []
        for c in existing.components:
            comp = SystemPromptComponent(**c.model_dump())
            if c.type in component_order:
                comp.order = component_order[c.type]
            components.append(comp)

        return self._create_component_version(
            existing,
            components=components,
            author=author,
            change_description=change_description or "Reordered components"
        )

    def get_components(self, prompt_id: str) -> List[SystemPromptComponent]:
        """
        Get components of a system prompt, sorted by order.

        Args:
            prompt_id: ID of prompt

        Returns:
            List of components sorted by order

        Raises:
            ValueError: If prompt not found or not a system prompt
        """
        prompt = self.get(prompt_id)
        if prompt is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if not prompt.is_system_prompt():
            raise ValueError("Not a system prompt")

        return sorted(prompt.components, key=lambda c: c.order)

    def search_system_prompts(
        self,
        name_pattern: Optional[str] = None,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
        component_types: Optional[List[PromptComponentType]] = None,
        model_compatibility: Optional[List[str]] = None,
    ) -> List[PromptVersion]:
        """
        Search system prompts.

        Args:
            name_pattern: Pattern to match names
            tags: Required tags (in addition to system_prompt)
            author: Author filter
            component_types: Filter by component types present
            model_compatibility: Filter by compatible models

        Returns:
            Matching system prompts
        """
        search_tags = ["system_prompt"]
        if tags:
            search_tags.extend(tags)
        if component_types:
            for ct in component_types:
                search_tags.append(f"component_{ct.value}")

        results = self.search(
            name_pattern=name_pattern,
            tags=search_tags,
            author=author,
        )

        # Additional filter by model compatibility if specified
        if model_compatibility:
            results = [
                r for r in results
                if any(m in r.metadata.model_compatibility for m in model_compatibility)
            ]

        return results

    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================

    def _validate_components(
        self,
        components: List[SystemPromptComponent]
    ) -> None:
        """Validate no duplicate non-CUSTOM component types."""
        seen = set()
        for c in components:
            if c.type != PromptComponentType.CUSTOM:
                if c.type in seen:
                    raise ValueError(f"Duplicate component: {c.type.value}")
                seen.add(c.type)

    def _compose_components(
        self,
        components: List[SystemPromptComponent]
    ) -> str:
        """Compose components into prompt content."""
        sorted_comps = sorted(
            [c for c in components if c.enabled],
            key=lambda c: c.order
        )

        parts = []
        for comp in sorted_comps:
            content = comp.content
            if comp.xml_tag:
                content = f"<{comp.xml_tag}>\n{content}\n</{comp.xml_tag}>"
            parts.append(content)

        return "\n\n".join(parts)

    def _create_component_version(
        self,
        existing: PromptVersion,
        components: List[SystemPromptComponent],
        author: Optional[str] = None,
        change_description: Optional[str] = None,
    ) -> PromptVersion:
        """Create new version from existing with updated components."""
        content = self._compose_components(components)

        # Update tags (using underscores to avoid MLflow search syntax issues)
        tags = [t for t in existing.metadata.tags
                if not t.startswith("component_")]
        for comp in components:
            if comp.type == PromptComponentType.CUSTOM:
                tags.append(f"component_custom_{comp.name}")
            else:
                tags.append(f"component_{comp.type.value}")

        new_version_num = self.store.get_next_version(existing.name)

        new_version = PromptVersion(
            id=generate_prompt_id(),
            name=existing.name,
            version=new_version_num,
            template=PromptTemplate(content=content),
            status=PromptStatus.DRAFT,
            metadata=PromptMetadata(
                author=author or existing.metadata.author,
                description=existing.metadata.description,
                tags=tags,
                model_compatibility=existing.metadata.model_compatibility,
                use_case=existing.metadata.use_case,
                custom=existing.metadata.custom,
            ),
            parent_id=existing.id,
            components=components,
            change_description=change_description,
        )

        self.store.save(new_version)
        return new_version
