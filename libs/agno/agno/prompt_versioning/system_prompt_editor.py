"""
SystemPromptEditor - Convenience layer for system prompt operations with Agent integration.

This module provides a high-level interface for managing Agent system prompts
as versioned artifacts with component-based decomposition.

Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 4.2
"""

from typing import List, Optional, Dict, Any, TYPE_CHECKING

from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.models import (
    PromptComponentType,
    PromptDiff,
    PromptVersion,
    SystemPromptComponent,
)

if TYPE_CHECKING:
    from agno.agent import Agent


class SystemPromptEditor:
    """
    Convenience layer for system prompt operations with Agent integration.

    Delegates to PromptManager for all persistence operations.
    Adds Agent-specific extraction and application.

    Example:
        >>> editor = SystemPromptEditor(tracking_uri="mlruns")
        >>>
        >>> # Create from components
        >>> components = [
        ...     SystemPromptComponent(
        ...         type=PromptComponentType.ROLE,
        ...         content="You are a helpful support agent.",
        ...         xml_tag="your_role"
        ...     )
        ... ]
        >>> prompt = editor.create("support_agent", components)
        >>>
        >>> # Edit a component
        >>> updated = editor.edit_component(
        ...     prompt.id,
        ...     PromptComponentType.ROLE,
        ...     "You are an expert support specialist.",
        ...     change_description="Enhanced role description"
        ... )
        >>>
        >>> # Preview components
        >>> previews = editor.preview_components(updated.id)
        >>> for name, content in previews.items():
        ...     print(f"--- {name} ---")
        ...     print(content)

    Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 4.2
    """

    def __init__(
        self,
        tracking_uri: str = "mlruns",
        experiment_prefix: str = "prompt_versioning",
    ):
        """
        Initialize SystemPromptEditor with PromptManager.

        Args:
            tracking_uri: MLflow tracking URI (local path or server URL)
            experiment_prefix: Prefix for MLflow experiments
        """
        self._manager = PromptManager(
            tracking_uri=tracking_uri,
            experiment_prefix=experiment_prefix,
        )

    @property
    def manager(self) -> PromptManager:
        """Access underlying PromptManager for advanced operations."""
        return self._manager

    # =========================================================================
    # DELEGATED METHODS (pass through to manager)
    # =========================================================================

    def create(
        self,
        name: str,
        components: List[SystemPromptComponent],
        description: Optional[str] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        model_compatibility: Optional[List[str]] = None,
    ) -> PromptVersion:
        """
        Create a system prompt from components.

        Args:
            name: Unique prompt name
            components: List of SystemPromptComponent objects
            description: Human-readable description
            author: Author name
            tags: Tags for categorization
            model_compatibility: List of compatible model identifiers

        Returns:
            Created PromptVersion with components
        """
        return self._manager.create_system_prompt(
            name=name,
            components=components,
            description=description,
            author=author,
            tags=tags,
            model_compatibility=model_compatibility,
        )

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
        Edit a component with full traceability.

        Args:
            prompt_id: ID of prompt to edit
            component_type: Type of component to edit
            new_content: New content for the component
            component_name: Name (required for CUSTOM type)
            author: Author of the edit
            change_description: Description of changes for audit trail

        Returns:
            New PromptVersion with updated component
        """
        return self._manager.edit_component(
            prompt_id=prompt_id,
            component_type=component_type,
            new_content=new_content,
            component_name=component_name,
            author=author,
            change_description=change_description,
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
        """
        return self._manager.add_component(
            prompt_id=prompt_id,
            component=component,
            author=author,
            change_description=change_description,
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
            component_name: Name (required for CUSTOM type)
            author: Author of change
            change_description: Description of changes

        Returns:
            New PromptVersion without the component
        """
        return self._manager.remove_component(
            prompt_id=prompt_id,
            component_type=component_type,
            component_name=component_name,
            author=author,
            change_description=change_description,
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
        """
        return self._manager.reorder_components(
            prompt_id=prompt_id,
            component_order=component_order,
            author=author,
            change_description=change_description,
        )

    def get(self, prompt_id: str) -> Optional[PromptVersion]:
        """Get prompt by ID."""
        return self._manager.get(prompt_id)

    def get_by_name(
        self,
        name: str,
        version: Optional[int] = None
    ) -> Optional[PromptVersion]:
        """Get prompt by name and optional version."""
        return self._manager.get_by_name(name, version)

    def get_components(self, prompt_id: str) -> List[SystemPromptComponent]:
        """Get components sorted by order."""
        return self._manager.get_components(prompt_id)

    def snapshot(
        self,
        prompt_id: str,
        snapshot_name: str,
        description: Optional[str] = None,
    ) -> PromptVersion:
        """Create a named snapshot."""
        return self._manager.snapshot(prompt_id, snapshot_name, description)

    def fork(
        self,
        prompt_id: str,
        new_name: str,
        description: Optional[str] = None,
        author: Optional[str] = None,
    ) -> PromptVersion:
        """Fork prompt to create a new independent prompt."""
        return self._manager.fork(prompt_id, new_name, description, author)

    def compare(
        self,
        from_id: str,
        to_id: str,
    ) -> PromptDiff:
        """Compare two versions."""
        return self._manager.compare(from_id, to_id)

    def search(
        self,
        name_pattern: Optional[str] = None,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
        component_types: Optional[List[PromptComponentType]] = None,
        model_compatibility: Optional[List[str]] = None,
    ) -> List[PromptVersion]:
        """Search system prompts."""
        return self._manager.search_system_prompts(
            name_pattern=name_pattern,
            tags=tags,
            author=author,
            component_types=component_types,
            model_compatibility=model_compatibility,
        )

    # =========================================================================
    # PREVIEW AND COMPOSITION
    # =========================================================================

    def compose(self, prompt_id: str, **variables) -> str:
        """
        Compose and render a system prompt.

        Args:
            prompt_id: Prompt ID
            **variables: Template variables to substitute

        Returns:
            Composed and rendered prompt string
        """
        return self._manager.render(prompt_id=prompt_id, **variables)

    def preview_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        component_name: Optional[str] = None,
        include_xml_tag: bool = True,
    ) -> str:
        """
        Preview a single component.

        Args:
            prompt_id: Prompt ID
            component_type: Type of component to preview
            component_name: Name (required for CUSTOM type)
            include_xml_tag: Whether to include XML tag wrapper

        Returns:
            Component content as string

        Raises:
            ValueError: If prompt or component not found
        """
        prompt = self.get(prompt_id)
        if prompt is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        comp = prompt.get_component(component_type, component_name)
        if comp is None:
            raise ValueError(f"Component not found: {component_type.value}")

        content = comp.content
        if include_xml_tag and comp.xml_tag:
            content = f"<{comp.xml_tag}>\n{content}\n</{comp.xml_tag}>"

        return content

    def preview_components(
        self,
        prompt_id: str,
        include_only: Optional[List[PromptComponentType]] = None,
        include_xml_tags: bool = True,
    ) -> Dict[str, str]:
        """
        Preview all components as a dictionary.

        Args:
            prompt_id: Prompt ID
            include_only: Optional list of component types to include
            include_xml_tags: Whether to include XML tags in preview

        Returns:
            Dict mapping component type/name to rendered content

        Example:
            >>> previews = editor.preview_components(prompt_id)
            >>> for name, content in previews.items():
            ...     print(f"--- {name} ---")
            ...     print(content)
        """
        prompt = self.get(prompt_id)
        if prompt is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if not prompt.is_system_prompt():
            raise ValueError("Not a system prompt")

        result = {}
        for comp in sorted(prompt.components, key=lambda c: c.order):
            # Filter by type if specified
            if include_only and comp.type not in include_only:
                continue

            # Generate key
            if comp.type == PromptComponentType.CUSTOM:
                key = f"custom:{comp.name}"
            else:
                key = comp.type.value

            # Generate content
            content = comp.content
            if include_xml_tags and comp.xml_tag:
                content = f"<{comp.xml_tag}>\n{content}\n</{comp.xml_tag}>"

            result[key] = content

        return result

    # =========================================================================
    # AGENT INTEGRATION
    # =========================================================================

    def create_from_agent(
        self,
        name: str,
        agent: "Agent",
        description: Optional[str] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> PromptVersion:
        """
        Create a system prompt by extracting components from an Agent.

        Args:
            name: Unique prompt name
            agent: Agent instance to extract from
            description: Description
            author: Author name
            tags: Additional tags

        Returns:
            Created PromptVersion with extracted components

        Note:
            Extracts static configuration only. Runtime values
            (memories, session state) are not extracted.

        Example:
            >>> from agno.agent import Agent
            >>> agent = Agent(
            ...     name="support",
            ...     role="A helpful support specialist",
            ...     instructions=["Be helpful", "Be concise"]
            ... )
            >>> prompt = editor.create_from_agent("support_v1", agent)
        """
        components = self._extract_from_agent(agent)

        extra_tags = list(tags or [])
        if hasattr(agent, "name") and agent.name:
            extra_tags.append(f"agent_{agent.name}")
        if hasattr(agent, "model") and agent.model:
            if hasattr(agent.model, "id"):
                extra_tags.append(f"model_{agent.model.id}")

        agent_name = getattr(agent, "name", "unknown")
        desc = description or f"Extracted from agent: {agent_name}"

        model_compat = None
        if hasattr(agent, "model") and agent.model:
            if hasattr(agent.model, "id"):
                model_compat = [agent.model.id]

        return self.create(
            name=name,
            components=components,
            description=desc,
            author=author,
            tags=extra_tags,
            model_compatibility=model_compat,
        )

    def apply_to_agent(
        self,
        prompt_id: str,
        agent: "Agent",
        override_system_message: bool = False,
    ) -> None:
        """
        Apply a versioned system prompt to an Agent.

        Args:
            prompt_id: ID of the prompt version to apply
            agent: Agent instance to modify
            override_system_message: If True, set agent.system_message directly;
                                     if False, set individual component attributes

        Note:
            This modifies the Agent in place. Changes are not persisted
            to the Agent's original configuration.

        Example:
            >>> editor.apply_to_agent(prod_prompt.id, agent)
            >>> # Agent now uses the versioned prompt
        """
        prompt = self.get(prompt_id)
        if prompt is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if override_system_message:
            # Option 1: Set composed prompt directly
            composed = self.compose(prompt_id)
            agent.system_message = composed
        else:
            # Option 2: Set individual attributes (preserves Agent structure)
            for comp in prompt.components:
                if comp.type == PromptComponentType.DESCRIPTION:
                    agent.description = comp.content
                elif comp.type == PromptComponentType.ROLE:
                    agent.role = comp.content
                elif comp.type == PromptComponentType.INSTRUCTIONS:
                    # Convert back to list if it was a list originally
                    if comp.content.startswith("- "):
                        agent.instructions = [
                            line.lstrip("- ").strip()
                            for line in comp.content.split("\n")
                            if line.strip()
                        ]
                    else:
                        agent.instructions = [comp.content]
                elif comp.type == PromptComponentType.EXPECTED_OUTPUT:
                    agent.expected_output = comp.content
                elif comp.type == PromptComponentType.ADDITIONAL_CONTEXT:
                    agent.additional_context = comp.content

    def get_agent_compatible_versions(
        self,
        model_id: str,
    ) -> List[PromptVersion]:
        """
        Get system prompts compatible with a specific model.

        Args:
            model_id: Model identifier (e.g., "gpt-4", "claude-3-opus")

        Returns:
            List of compatible PromptVersion objects
        """
        return self._manager.search_system_prompts(
            model_compatibility=[model_id]
        )

    # =========================================================================
    # EXPORT
    # =========================================================================

    def export_as_markdown(
        self,
        prompt_id: str,
        include_metadata: bool = True,
        include_history: bool = False,
    ) -> str:
        """
        Export a system prompt as readable markdown.

        Args:
            prompt_id: Prompt ID
            include_metadata: Include metadata section
            include_history: Include version history

        Returns:
            Markdown string

        Example:
            >>> md = editor.export_as_markdown(prompt_id)
            >>> with open("prompt_doc.md", "w") as f:
            ...     f.write(md)
        """
        prompt = self.get(prompt_id)
        if prompt is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        lines = [
            f"# System Prompt: {prompt.name}",
            "",
            f"**Version**: {prompt.version}",
            f"**Status**: {prompt.status.value}",
            f"**ID**: `{prompt.id}`",
            "",
        ]

        if include_metadata:
            lines.extend([
                "## Metadata",
                "",
                f"- **Author**: {prompt.metadata.author or 'Unknown'}",
                f"- **Description**: {prompt.metadata.description or 'None'}",
                f"- **Tags**: {', '.join(prompt.metadata.tags) if prompt.metadata.tags else 'None'}",
                f"- **Model Compatibility**: {', '.join(prompt.metadata.model_compatibility) if prompt.metadata.model_compatibility else 'Any'}",
                f"- **Created**: {prompt.created_at.isoformat()}",
                f"- **Updated**: {prompt.updated_at.isoformat()}",
                "",
            ])

        if prompt.change_description:
            lines.extend([
                "## Latest Changes",
                "",
                prompt.change_description,
                "",
            ])

        lines.extend([
            "## Components",
            "",
        ])

        if prompt.is_system_prompt():
            for comp in sorted(prompt.components, key=lambda c: c.order):
                comp_name = comp.name if comp.type == PromptComponentType.CUSTOM else comp.type.value
                lines.extend([
                    f"### {comp_name.replace('_', ' ').title()}",
                    "",
                    f"- **Order**: {comp.order}",
                    f"- **XML Tag**: `{comp.xml_tag or 'None'}`",
                    f"- **Enabled**: {comp.enabled}",
                    "",
                    "```",
                    comp.content,
                    "```",
                    "",
                ])
        else:
            lines.extend([
                "```",
                prompt.template.content,
                "```",
                "",
            ])

        if include_history and prompt.parent_id:
            lines.extend([
                "## Version History",
                "",
                f"- Parent: `{prompt.parent_id}`",
            ])
            if prompt.forked_from:
                lines.append(f"- Forked from: `{prompt.forked_from}`")
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _extract_from_agent(self, agent: "Agent") -> List[SystemPromptComponent]:
        """
        Extract components from Agent instance.

        Extracts static configuration attributes only.
        """
        components = []

        if hasattr(agent, "description") and agent.description:
            components.append(SystemPromptComponent(
                type=PromptComponentType.DESCRIPTION,
                content=agent.description,
                order=SystemPromptComponent.get_default_order(
                    PromptComponentType.DESCRIPTION
                ),
            ))

        if hasattr(agent, "role") and agent.role:
            components.append(SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content=agent.role,
                order=SystemPromptComponent.get_default_order(
                    PromptComponentType.ROLE
                ),
                xml_tag=SystemPromptComponent.get_default_xml_tag(
                    PromptComponentType.ROLE
                ),
            ))

        if hasattr(agent, "instructions") and agent.instructions:
            if isinstance(agent.instructions, list):
                content = "\n".join(f"- {i}" for i in agent.instructions)
            else:
                content = str(agent.instructions)

            components.append(SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content=content,
                order=SystemPromptComponent.get_default_order(
                    PromptComponentType.INSTRUCTIONS
                ),
                xml_tag=SystemPromptComponent.get_default_xml_tag(
                    PromptComponentType.INSTRUCTIONS
                ),
            ))

        if hasattr(agent, "expected_output") and agent.expected_output:
            components.append(SystemPromptComponent(
                type=PromptComponentType.EXPECTED_OUTPUT,
                content=agent.expected_output,
                order=SystemPromptComponent.get_default_order(
                    PromptComponentType.EXPECTED_OUTPUT
                ),
                xml_tag=SystemPromptComponent.get_default_xml_tag(
                    PromptComponentType.EXPECTED_OUTPUT
                ),
            ))

        if hasattr(agent, "additional_context") and agent.additional_context:
            components.append(SystemPromptComponent(
                type=PromptComponentType.ADDITIONAL_CONTEXT,
                content=agent.additional_context,
                order=SystemPromptComponent.get_default_order(
                    PromptComponentType.ADDITIONAL_CONTEXT
                ),
            ))

        return components
