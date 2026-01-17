# SystemPromptEditor API Specification (Greenfield)

> **Status**: Draft Specification
> **Version**: 1.0.0
> **Last Updated**: 2026-01-17
> **Authors**: Engineering Team

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Principles](#2-design-principles)
3. [Data Model Specification](#3-data-model-specification)
4. [API Specification](#4-api-specification)
5. [Storage Schema](#5-storage-schema)
6. [Integration with Agent](#6-integration-with-agent)
7. [Blast Radius Analysis](#7-blast-radius-analysis)
8. [Testing Strategy](#8-testing-strategy)
9. [Implementation Checklist](#9-implementation-checklist)

---

## 1. Overview

### 1.1 Purpose

The SystemPromptEditor provides a unified interface for managing Agno Agent system prompts as first-class versioned artifacts with component-based decomposition.

### 1.2 Scope

- Native component support in prompt versioning models
- Agent-aware prompt extraction and application
- Semantic understanding of Agno's XML tag structure
- Full MLflow-backed versioning, snapshots, and forks

### 1.3 Architecture (Simplified)

```
┌─────────────────────────────────────────────────────────────────┐
│                    SystemPromptEditor                            │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              PromptManager (ENHANCED)                        │ │
│  │   - Native component support                                 │ │
│  │   - create(), edit(), snapshot(), fork()                     │ │
│  │   - Component-level operations                               │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              MLflowPromptStore (ENHANCED)                    │ │
│  │   - save(), load(), search()                                 │ │
│  │   - Component serialization                                  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Key Simplification**: Single unified architecture. No wrapper patterns or indirection.

---

## 2. Design Principles

### 2.1 Core Principles

| Principle | Application |
|-----------|-------------|
| **Native Integration** | Components are first-class fields, not serialized metadata |
| **Single Source of Truth** | All data in `PromptVersion` |
| **Composition Over Complexity** | Simple, flat model hierarchy |
| **Explicit Over Implicit** | All operations traceable |
| **Fail Fast** | Validate early, error clearly |

### 2.2 What We Remove (vs. Backward-Compatible Design)

- ~~Extension via `PromptMetadata.custom`~~
- ~~Wrapper pattern around PromptManager~~
- ~~Separate experiment prefix isolation~~
- ~~Backward compatibility layer~~
- ~~Complex indirection~~

---

## 3. Data Model Specification

### 3.1 PromptComponentType

```python
# File: prompt_versioning/models.py (ADD)

class PromptComponentType(str, Enum):
    """
    Enumeration of system prompt component types.

    Maps to Agent.get_system_message() construction order.
    Cross-ref: agent/agent.py lines 7742-8083

    Order values (10, 20, 30...) allow insertion without renumbering.
    """

    # Core identity
    DESCRIPTION = "description"           # Order: 10
    ROLE = "role"                         # Order: 20

    # Behavioral
    INSTRUCTIONS = "instructions"         # Order: 30
    TOOL_INSTRUCTIONS = "tool_instructions"  # Order: 40
    EXPECTED_OUTPUT = "expected_output"   # Order: 50

    # Context
    ADDITIONAL_INFO = "additional_info"   # Order: 60
    ADDITIONAL_CONTEXT = "additional_context"  # Order: 70

    # Memory (memory/manager.py integration)
    MEMORIES = "memories"                 # Order: 80
    SESSION_SUMMARY = "session_summary"   # Order: 85

    # Knowledge
    CULTURAL_KNOWLEDGE = "cultural_knowledge"  # Order: 90

    # Runtime
    SESSION_STATE = "session_state"       # Order: 95

    # Extension
    CUSTOM = "custom"                     # Order: user-defined
```

### 3.2 SystemPromptComponent

```python
# File: prompt_versioning/models.py (ADD)

class SystemPromptComponent(BaseModel):
    """
    Individual component of a system prompt.

    Stored directly in PromptVersion.components field.

    Design Notes:
    - `order` uses 10-increment scale for insertability
    - `xml_tag` follows Agno convention: <tag_name>content</tag_name>
    - `metadata` for component-specific config

    Cross-ref: Agent XML tags at agent/agent.py:7742-8083
    """

    type: PromptComponentType = Field(
        ...,
        description="Component type"
    )

    content: str = Field(
        ...,
        description="Component content (may include {{variables}})"
    )

    name: Optional[str] = Field(
        default=None,
        description="Name for CUSTOM type components (required for CUSTOM)"
    )

    order: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Render order (0-100)"
    )

    xml_tag: Optional[str] = Field(
        default=None,
        description="XML tag wrapper (e.g., 'your_role' -> <your_role>...</your_role>)"
    )

    enabled: bool = Field(
        default=True,
        description="Whether to include in composition"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Component-specific metadata"
    )

    @field_validator("name")
    @classmethod
    def validate_custom_name(cls, v, info):
        """CUSTOM type requires a name."""
        if info.data.get("type") == PromptComponentType.CUSTOM and not v:
            raise ValueError("CUSTOM components must have a name")
        return v

    @classmethod
    def get_default_order(cls, component_type: PromptComponentType) -> int:
        """Get default order for a component type."""
        orders = {
            PromptComponentType.DESCRIPTION: 10,
            PromptComponentType.ROLE: 20,
            PromptComponentType.INSTRUCTIONS: 30,
            PromptComponentType.TOOL_INSTRUCTIONS: 40,
            PromptComponentType.EXPECTED_OUTPUT: 50,
            PromptComponentType.ADDITIONAL_INFO: 60,
            PromptComponentType.ADDITIONAL_CONTEXT: 70,
            PromptComponentType.MEMORIES: 80,
            PromptComponentType.SESSION_SUMMARY: 85,
            PromptComponentType.CULTURAL_KNOWLEDGE: 90,
            PromptComponentType.SESSION_STATE: 95,
            PromptComponentType.CUSTOM: 50,
        }
        return orders.get(component_type, 50)

    @classmethod
    def get_default_xml_tag(cls, component_type: PromptComponentType) -> Optional[str]:
        """Get default XML tag for a component type."""
        tags = {
            PromptComponentType.ROLE: "your_role",
            PromptComponentType.INSTRUCTIONS: "instructions",
            PromptComponentType.EXPECTED_OUTPUT: "expected_output",
            PromptComponentType.ADDITIONAL_INFO: "additional_information",
            PromptComponentType.MEMORIES: "memories_from_previous_interactions",
            PromptComponentType.SESSION_SUMMARY: "summary_of_previous_interactions",
            PromptComponentType.CULTURAL_KNOWLEDGE: "cultural_knowledge",
            PromptComponentType.SESSION_STATE: "session_state",
        }
        return tags.get(component_type)
```

### 3.3 PromptVersion (MODIFIED)

```python
# File: prompt_versioning/models.py (MODIFY)

class PromptVersion(BaseModel):
    """
    A versioned prompt with full tracking information.

    MODIFICATION: Added native `components` field for system prompts.
    """

    # Existing fields (unchanged)
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable name")
    version: int = Field(default=1, ge=1, description="Version number")
    template: PromptTemplate = Field(..., description="The prompt template")
    status: PromptStatus = Field(default=PromptStatus.DRAFT)
    metadata: PromptMetadata = Field(default_factory=PromptMetadata)
    parent_id: Optional[str] = Field(default=None)
    forked_from: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    snapshot_name: Optional[str] = Field(default=None)
    content_hash: str = Field(default="")

    # NEW: Native component support
    components: Optional[List[SystemPromptComponent]] = Field(
        default=None,
        description="Optional list of components for system prompts. "
                    "If present, template.content is the composed result."
    )

    def is_system_prompt(self) -> bool:
        """Check if this is a component-based system prompt."""
        return self.components is not None and len(self.components) > 0

    def get_component(
        self,
        component_type: PromptComponentType,
        component_name: Optional[str] = None
    ) -> Optional[SystemPromptComponent]:
        """
        Get a specific component by type.

        Args:
            component_type: Type of component
            component_name: Name (required for CUSTOM type)

        Returns:
            Component if found, None otherwise
        """
        if not self.components:
            return None

        for comp in self.components:
            if comp.type == component_type:
                if component_type == PromptComponentType.CUSTOM:
                    if comp.name == component_name:
                        return comp
                else:
                    return comp
        return None

    def get_components_by_type(
        self,
        component_type: PromptComponentType
    ) -> List[SystemPromptComponent]:
        """Get all components of a given type (useful for CUSTOM)."""
        if not self.components:
            return []
        return [c for c in self.components if c.type == component_type]
```

### 3.4 PromptDiff (MODIFIED)

```python
# File: prompt_versioning/models.py (MODIFY)

class PromptDiff(BaseModel):
    """
    Represents differences between two prompt versions.

    MODIFICATION: Added component-level diff fields.
    """

    # Existing fields (unchanged)
    from_version: str
    to_version: str
    content_changed: bool = False
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    metadata_changes: Dict[str, Any] = Field(default_factory=dict)
    variables_added: Set[str] = Field(default_factory=set)
    variables_removed: Set[str] = Field(default_factory=set)

    # NEW: Component-level diff
    components_added: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Components added in to_version"
    )
    components_removed: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Components removed from from_version"
    )
    components_changed: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Components with changed content: {type: {old, new}}"
    )

    @classmethod
    def compute(cls, from_prompt: PromptVersion, to_prompt: PromptVersion) -> "PromptDiff":
        """Compute diff between two prompt versions."""
        # Existing logic for content/metadata/variables...

        # NEW: Component diff
        components_added = []
        components_removed = []
        components_changed = {}

        if from_prompt.components or to_prompt.components:
            from_comps = from_prompt.components or []
            to_comps = to_prompt.components or []

            def comp_key(c: SystemPromptComponent) -> str:
                if c.type == PromptComponentType.CUSTOM:
                    return f"custom:{c.name}"
                return c.type.value

            from_map = {comp_key(c): c for c in from_comps}
            to_map = {comp_key(c): c for c in to_comps}

            from_keys = set(from_map.keys())
            to_keys = set(to_map.keys())

            components_added = [
                to_map[k].model_dump() for k in (to_keys - from_keys)
            ]
            components_removed = [
                from_map[k].model_dump() for k in (from_keys - to_keys)
            ]

            for k in (from_keys & to_keys):
                if from_map[k].content != to_map[k].content:
                    components_changed[k] = {
                        "old": from_map[k].content,
                        "new": to_map[k].content,
                    }

        return cls(
            from_version=from_prompt.id,
            to_version=to_prompt.id,
            content_changed=from_prompt.content != to_prompt.content,
            # ... existing fields ...
            components_added=components_added,
            components_removed=components_removed,
            components_changed=components_changed,
        )
```

---

## 4. API Specification

### 4.1 PromptManager (ENHANCED)

The existing `PromptManager` is enhanced with native component support.

```python
# File: prompt_versioning/manager.py (MODIFY)

class PromptManager:
    """
    High-level manager for prompt versioning operations.

    MODIFICATION: Added component-aware methods.
    """

    # Existing methods (unchanged signatures)
    def create(...) -> PromptVersion: ...
    def edit(...) -> PromptVersion: ...
    def snapshot(...) -> PromptVersion: ...
    def fork(...) -> PromptVersion: ...
    def get(...) -> Optional[PromptVersion]: ...
    def get_by_name(...) -> Optional[PromptVersion]: ...
    def search(...) -> List[PromptVersion]: ...
    def compare(...) -> PromptDiff: ...
    def render(...) -> str: ...

    # NEW: Component-aware methods

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
        """
        # Validate no duplicate non-CUSTOM components
        self._validate_components(components)

        # Compose content from components
        content = self._compose_components(components)

        # Add system_prompt tag
        all_tags = list(tags or [])
        all_tags.append("system_prompt")
        for comp in components:
            if comp.type == PromptComponentType.CUSTOM:
                all_tags.append(f"component:custom:{comp.name}")
            else:
                all_tags.append(f"component:{comp.type.value}")

        # Create version with components
        prompt_id = generate_prompt_id()
        version = PromptVersion(
            id=prompt_id,
            name=name,
            version=1,
            template=PromptTemplate(content=content),
            status=PromptStatus.DRAFT,
            metadata=PromptMetadata(
                author=author,
                description=description,
                tags=all_tags,
                model_compatibility=model_compatibility or [],
            ),
            components=components,  # Native storage
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
    ) -> PromptVersion:
        """
        Edit a specific component, creating a new version.

        Args:
            prompt_id: ID of prompt to edit
            component_type: Type of component to edit
            new_content: New content
            component_name: Required for CUSTOM type
            author: Author of edit

        Returns:
            New PromptVersion with updated component
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

        # Create new version
        return self._create_new_version(
            existing,
            components=components,
            author=author
        )

    def add_component(
        self,
        prompt_id: str,
        component: SystemPromptComponent,
        author: Optional[str] = None,
    ) -> PromptVersion:
        """Add a new component to a system prompt."""
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

        return self._create_new_version(
            existing,
            components=components,
            author=author
        )

    def remove_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        component_name: Optional[str] = None,
        author: Optional[str] = None,
    ) -> PromptVersion:
        """Remove a component from a system prompt."""
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

        return self._create_new_version(
            existing,
            components=components,
            author=author
        )

    def get_components(self, prompt_id: str) -> List[SystemPromptComponent]:
        """Get components of a system prompt, sorted by order."""
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
    ) -> List[PromptVersion]:
        """
        Search system prompts.

        Args:
            name_pattern: Pattern to match names
            tags: Required tags
            author: Author filter
            component_types: Filter by component types present

        Returns:
            Matching system prompts
        """
        search_tags = ["system_prompt"]
        if tags:
            search_tags.extend(tags)
        if component_types:
            for ct in component_types:
                search_tags.append(f"component:{ct.value}")

        return self.search(
            name_pattern=name_pattern,
            tags=search_tags,
            author=author,
        )

    # Internal helpers

    def _validate_components(
        self,
        components: List[SystemPromptComponent]
    ) -> None:
        """Validate no duplicate non-CUSTOM types."""
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

    def _create_new_version(
        self,
        existing: PromptVersion,
        components: List[SystemPromptComponent],
        author: Optional[str] = None,
    ) -> PromptVersion:
        """Create new version from existing with updated components."""
        content = self._compose_components(components)

        # Update tags
        tags = [t for t in existing.metadata.tags
                if not t.startswith("component:")]
        for comp in components:
            if comp.type == PromptComponentType.CUSTOM:
                tags.append(f"component:custom:{comp.name}")
            else:
                tags.append(f"component:{comp.type.value}")

        new_version = PromptVersion(
            id=generate_prompt_id(),
            name=existing.name,
            version=existing.version + 1,
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
        )

        self.store.save(new_version)
        return new_version
```

### 4.2 SystemPromptEditor (Convenience Layer)

A thin convenience layer that adds Agent integration.

```python
# File: prompt_versioning/system_prompt_editor.py (NEW)

from typing import List, Optional, TYPE_CHECKING
from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.models import (
    PromptVersion,
    PromptComponentType,
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
        >>> # Create from agent
        >>> prompt = editor.create_from_agent("support_v1", agent)
        >>>
        >>> # Edit component
        >>> updated = editor.edit_component(
        ...     prompt.id,
        ...     PromptComponentType.ROLE,
        ...     "New role content"
        ... )
    """

    def __init__(
        self,
        tracking_uri: str = "mlruns",
        experiment_prefix: str = "prompt_versioning",
    ):
        """Initialize with PromptManager."""
        self._manager = PromptManager(
            tracking_uri=tracking_uri,
            experiment_prefix=experiment_prefix,
        )

    @property
    def manager(self) -> PromptManager:
        """Access underlying PromptManager."""
        return self._manager

    # =========================================================================
    # DELEGATED METHODS (pass through to manager)
    # =========================================================================

    def create(
        self,
        name: str,
        components: List[SystemPromptComponent],
        **kwargs
    ) -> PromptVersion:
        """Create system prompt from components."""
        return self._manager.create_system_prompt(name, components, **kwargs)

    def edit_component(self, *args, **kwargs) -> PromptVersion:
        """Edit a component."""
        return self._manager.edit_component(*args, **kwargs)

    def add_component(self, *args, **kwargs) -> PromptVersion:
        """Add a component."""
        return self._manager.add_component(*args, **kwargs)

    def remove_component(self, *args, **kwargs) -> PromptVersion:
        """Remove a component."""
        return self._manager.remove_component(*args, **kwargs)

    def get(self, prompt_id: str) -> Optional[PromptVersion]:
        """Get prompt by ID."""
        return self._manager.get(prompt_id)

    def get_by_name(self, name: str, version: Optional[int] = None) -> Optional[PromptVersion]:
        """Get prompt by name."""
        return self._manager.get_by_name(name, version)

    def get_components(self, prompt_id: str) -> List[SystemPromptComponent]:
        """Get components sorted by order."""
        return self._manager.get_components(prompt_id)

    def snapshot(self, *args, **kwargs) -> PromptVersion:
        """Create snapshot."""
        return self._manager.snapshot(*args, **kwargs)

    def fork(self, *args, **kwargs) -> PromptVersion:
        """Fork prompt."""
        return self._manager.fork(*args, **kwargs)

    def compare(self, *args, **kwargs):
        """Compare versions."""
        return self._manager.compare(*args, **kwargs)

    def search(self, **kwargs) -> List[PromptVersion]:
        """Search system prompts."""
        return self._manager.search_system_prompts(**kwargs)

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
        """
        components = self._extract_from_agent(agent)

        extra_tags = list(tags or [])
        if hasattr(agent, "name") and agent.name:
            extra_tags.append(f"agent:{agent.name}")

        return self.create(
            name=name,
            components=components,
            description=description or f"Extracted from agent",
            author=author,
            tags=extra_tags,
        )

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
        """Preview a single component."""
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

    def _extract_from_agent(self, agent: "Agent") -> List[SystemPromptComponent]:
        """Extract components from Agent instance."""
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
```

---

## 5. Storage Schema

### 5.1 MLflow Artifact Structure

Components are stored natively in the prompt artifact:

```json
{
  "id": "prompt_abc123",
  "name": "support_agent",
  "version": 2,
  "content": "<your_role>\nYou are...\n</your_role>\n\n<instructions>\n...\n</instructions>",
  "variables": ["user_name"],
  "status": "active",
  "metadata": {
    "author": "alice@company.com",
    "description": "Support agent prompt",
    "tags": ["system_prompt", "component:role", "component:instructions"],
    "model_compatibility": ["gpt-4"],
    "use_case": "customer_support",
    "custom": {}
  },
  "components": [
    {
      "type": "role",
      "content": "You are a helpful support specialist.",
      "name": null,
      "order": 20,
      "xml_tag": "your_role",
      "enabled": true,
      "metadata": {}
    },
    {
      "type": "instructions",
      "content": "- Be helpful\n- Be concise",
      "name": null,
      "order": 30,
      "xml_tag": "instructions",
      "enabled": true,
      "metadata": {}
    }
  ],
  "parent_id": "prompt_xyz789",
  "forked_from": null,
  "created_at": "2026-01-17T10:30:00Z",
  "updated_at": "2026-01-17T12:45:00Z",
  "snapshot_name": null,
  "content_hash": "a1b2c3d4e5f6g7h8"
}
```

### 5.2 MLflowPromptStore Modifications

```python
# File: prompt_versioning/mlflow_backend.py (MODIFY)

def _prompt_to_artifact(self, prompt: PromptVersion) -> Dict[str, Any]:
    """Convert prompt to artifact dict."""
    data = {
        # Existing fields...
        "id": prompt.id,
        "name": prompt.name,
        "version": prompt.version,
        "content": prompt.template.content,
        "variables": list(prompt.template.variables),
        # ...
    }

    # NEW: Include components
    if prompt.components:
        data["components"] = [c.model_dump() for c in prompt.components]

    return data

def _artifact_to_prompt(self, data: Dict[str, Any]) -> PromptVersion:
    """Convert artifact dict to prompt."""
    # Existing fields...

    # NEW: Load components
    components = None
    if "components" in data and data["components"]:
        components = [
            SystemPromptComponent(**c) for c in data["components"]
        ]

    return PromptVersion(
        # Existing fields...
        components=components,
    )
```

---

## 6. Integration with Agent

### 6.1 Current State (Read-Only)

```python
# Extract agent config to versioned prompt
editor = SystemPromptEditor()
prompt = editor.create_from_agent("my_agent_v1", agent)

# Get composed prompt for external use
composed = editor.compose(prompt.id)
```

### 6.2 Future State (Agent Modification)

When Agent is modified to support versioned prompts:

```python
class Agent:
    system_prompt_id: Optional[str] = None

    def get_system_message(self, ...):
        if self.system_prompt_id:
            editor = SystemPromptEditor()
            return editor.compose(self.system_prompt_id)
        # ... existing logic
```

---

## 7. Blast Radius Analysis

### 7.1 Summary

| Change | Files Modified | Risk | Rationale |
|--------|----------------|------|-----------|
| Add `PromptComponentType` | models.py | LOW | New enum, additive |
| Add `SystemPromptComponent` | models.py | LOW | New model, additive |
| Add `components` to `PromptVersion` | models.py | LOW | Optional field, no breaking change |
| Enhance `PromptDiff` | models.py | LOW | Additional optional fields |
| Add component methods to `PromptManager` | manager.py | LOW | New methods, additive |
| Modify `MLflowPromptStore` serialization | mlflow_backend.py | LOW | Backward-compatible (optional field) |
| Add `SystemPromptEditor` | NEW FILE | NONE | New file |

### 7.2 No Breaking Changes

- All new fields are optional
- Existing methods unchanged
- Non-component prompts continue to work

---

## 8. Testing Strategy

### 8.1 Test Organization

```
tests/
├── unit/
│   ├── test_component_models.py         # PromptComponentType, SystemPromptComponent
│   └── test_prompt_version_components.py # PromptVersion.components
├── integration/
│   ├── test_manager_components.py       # PromptManager component methods
│   └── test_mlflow_components.py        # MLflow component serialization
└── e2e/
    ├── test_component_workflows.py      # Full workflows
    └── test_agent_integration.py        # Agent extraction
```

### 8.2 Test Examples

```python
# Unit: test_component_models.py

def test_component_type_default_order():
    """Each type has a default order."""
    assert SystemPromptComponent.get_default_order(
        PromptComponentType.ROLE
    ) == 20

def test_custom_requires_name():
    """CUSTOM type must have name."""
    with pytest.raises(ValueError):
        SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            content="content"
        )

# Integration: test_manager_components.py

def test_create_system_prompt(manager):
    """Create prompt with components."""
    components = [
        SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="You are helpful."
        )
    ]

    prompt = manager.create_system_prompt("test", components)

    assert prompt.is_system_prompt()
    assert len(prompt.components) == 1

def test_edit_component_creates_version(manager):
    """Editing creates new version."""
    prompt = manager.create_system_prompt("test", [...])

    updated = manager.edit_component(
        prompt.id,
        PromptComponentType.ROLE,
        "New content"
    )

    assert updated.version == 2
    assert updated.parent_id == prompt.id

# E2E: test_component_workflows.py

def test_full_iteration_workflow(editor):
    """Create, edit, snapshot, fork."""
    # Create
    v1 = editor.create("agent", components)

    # Edit
    v2 = editor.edit_component(v1.id, ...)

    # Add guardrails
    v3 = editor.add_component(v2.id, guardrails)

    # Snapshot
    prod = editor.snapshot(v3.id, "production-v1")

    # Fork for A/B
    variant = editor.fork(v3.id, "agent_variant_b")

    # Verify
    assert prod.snapshot_name == "production-v1"
    assert variant.forked_from == v3.id
```

### 8.3 Coverage Requirements

| Category | Target | Focus |
|----------|--------|-------|
| Unit | 95% | Model validation, composition |
| Integration | 85% | Manager + Store |
| E2E | 80% | Full workflows |

---

## 9. Implementation Checklist

### Phase 1: Models

- [ ] Add `PromptComponentType` enum to `models.py`
- [ ] Add `SystemPromptComponent` model to `models.py`
- [ ] Add `components` field to `PromptVersion`
- [ ] Add `is_system_prompt()`, `get_component()` methods
- [ ] Enhance `PromptDiff.compute()` for component diff
- [ ] Unit tests (95% coverage)

### Phase 2: Storage

- [ ] Update `_prompt_to_artifact()` for components
- [ ] Update `_artifact_to_prompt()` for components
- [ ] Integration tests for serialization

### Phase 3: Manager

- [ ] Add `create_system_prompt()` method
- [ ] Add `edit_component()` method
- [ ] Add `add_component()`, `remove_component()` methods
- [ ] Add `get_components()` method
- [ ] Add `search_system_prompts()` method
- [ ] Integration tests (85% coverage)

### Phase 4: SystemPromptEditor

- [ ] Create `system_prompt_editor.py`
- [ ] Implement Agent extraction
- [ ] Implement convenience methods
- [ ] E2E tests (80% coverage)
- [ ] Documentation

### Review Checkpoints

- [ ] Design Review: Before Phase 1
- [ ] Code Review: After each phase
- [ ] Final Review: After Phase 4

---

## Appendix: Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `models.py` | MODIFY | Add PromptComponentType, SystemPromptComponent, modify PromptVersion |
| `mlflow_backend.py` | MODIFY | Component serialization |
| `manager.py` | MODIFY | Add component-aware methods |
| `system_prompt_editor.py` | NEW | Agent integration layer |

---

*End of Specification*
