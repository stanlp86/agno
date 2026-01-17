# SystemPromptEditor API Specification (Greenfield)

> **Status**: ✅ Implemented
> **Version**: 2.0.0
> **Last Updated**: 2026-01-17
> **Authors**: Engineering Team
> **Implementation**: Complete with 115 new tests (313 total)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Principles](#2-design-principles)
3. [Data Model Specification](#3-data-model-specification)
4. [API Specification](#4-api-specification)
5. [Storage Schema](#5-storage-schema)
6. [Integration with Agent](#6-integration-with-agent)
7. [Memory and Knowledge Integration](#7-memory-and-knowledge-integration)
8. [Blast Radius Analysis](#8-blast-radius-analysis)
9. [Benefits & Use Cases](#9-benefits--use-cases)
10. [Risks & Mitigations](#10-risks--mitigations)
11. [Future Enhancements](#11-future-enhancements)
12. [Testing Strategy](#12-testing-strategy)
13. [Code Examples](#13-code-examples)
14. [Implementation Checklist](#14-implementation-checklist)
15. [Cross-Reference Index](#15-cross-reference-index)

---

## 1. Overview

### 1.1 Purpose

The SystemPromptEditor provides a unified interface for managing Agno Agent system prompts as first-class versioned artifacts with component-based decomposition.

### 1.2 Scope

- Native component support in prompt versioning models
- Agent-aware prompt extraction and application
- Semantic understanding of Agno's XML tag structure
- Full MLflow-backed versioning, snapshots, and forks
- Complete traceability with change descriptions

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

### 1.4 System Prompt Components Overview

The `Agent.get_system_message()` method (lines 7742-8083 in `/libs/agno/agno/agent/agent.py`) builds prompts from these sources:

| Component | Source | XML Tag | Optional | Priority |
|-----------|--------|---------|----------|----------|
| **Description** | `agent.description` | None | Yes | 1 |
| **Role** | `agent.role` | `<your_role>` | Yes | 2 |
| **Instructions** | `agent.instructions` + model instructions | `<instructions>` | Yes | 3 |
| **Additional Info** | Datetime, location, name, agentic filters | `<additional_information>` | Yes | 4 |
| **Tool Instructions** | `agent._tool_instructions` | None | Yes | 5 |
| **Expected Output** | `agent.expected_output` | `<expected_output>` | Yes | 6 |
| **Additional Context** | `agent.additional_context` | None | Yes | 7 |
| **Memories** | MemoryManager (user memories) | `<memories_from_previous_interactions>` | Yes | 8 |
| **Cultural Knowledge** | CultureManager | `<cultural_knowledge>` | Yes | 9 |
| **Session Summary** | SessionSummaryManager | `<summary_of_previous_interactions>` | Yes | 10 |
| **Model Instructions** | Model-specific guidance | None | Yes | 11 |
| **JSON Output Format** | Output schema instructions | None | Conditional | 12 |
| **Session State** | Runtime session variables | `<session_state>` | Yes | 13 |

> **Cross-ref**: See [Section 15](#15-cross-reference-index) for file paths and line numbers.

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
| **Full Traceability** | Every change captured with description and author |
| **Design for Future** | Order values allow insertion; models support extension |

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

    # NEW: Change tracking for traceability
    change_description: Optional[str] = Field(
        default=None,
        description="Description of changes from parent version"
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

    # NEW: Change description from the newer version
    change_description: Optional[str] = Field(
        default=None,
        description="Change description from the to_version"
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
            change_description=to_prompt.change_description,
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
        change_description: Optional[str] = None,  # Full traceability
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

        Note:
            The change_description is stored in the new version for
            full traceability and audit trail.
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
        return self._create_new_version(
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
            author=author,
            change_description=change_description or f"Added {component.type.value} component"
        )

    def remove_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        component_name: Optional[str] = None,
        author: Optional[str] = None,
        change_description: Optional[str] = None,
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
            author=author,
            change_description=change_description or f"Removed {component_type.value} component"
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

        return self._create_new_version(
            existing,
            components=components,
            author=author,
            change_description=change_description or "Reordered components"
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
        model_compatibility: Optional[List[str]] = None,
    ) -> List[PromptVersion]:
        """
        Search system prompts.

        Args:
            name_pattern: Pattern to match names
            tags: Required tags
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
                search_tags.append(f"component:{ct.value}")

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
        change_description: Optional[str] = None,
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
            change_description=change_description,
        )

        self.store.save(new_version)
        return new_version
```

### 4.2 SystemPromptEditor (Convenience Layer)

A thin convenience layer that adds Agent integration and utility methods.

```python
# File: prompt_versioning/system_prompt_editor.py (NEW)

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.models import (
    PromptVersion,
    PromptComponentType,
    SystemPromptComponent,
    PromptDiff,
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
        ...     "New role content",
        ...     change_description="Updated role for premium support"
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

    def edit_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        new_content: str,
        component_name: Optional[str] = None,
        author: Optional[str] = None,
        change_description: Optional[str] = None,
    ) -> PromptVersion:
        """Edit a component with full traceability."""
        return self._manager.edit_component(
            prompt_id=prompt_id,
            component_type=component_type,
            new_content=new_content,
            component_name=component_name,
            author=author,
            change_description=change_description,
        )

    def add_component(self, *args, **kwargs) -> PromptVersion:
        """Add a component."""
        return self._manager.add_component(*args, **kwargs)

    def remove_component(self, *args, **kwargs) -> PromptVersion:
        """Remove a component."""
        return self._manager.remove_component(*args, **kwargs)

    def reorder_components(self, *args, **kwargs) -> PromptVersion:
        """Reorder components."""
        return self._manager.reorder_components(*args, **kwargs)

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

    def compare(self, *args, **kwargs) -> PromptDiff:
        """Compare versions."""
        return self._manager.compare(*args, **kwargs)

    def search(self, **kwargs) -> List[PromptVersion]:
        """Search system prompts."""
        return self._manager.search_system_prompts(**kwargs)

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
        """
        components = self._extract_from_agent(agent)

        extra_tags = list(tags or [])
        if hasattr(agent, "name") and agent.name:
            extra_tags.append(f"agent:{agent.name}")
        if hasattr(agent, "model") and hasattr(agent.model, "id"):
            extra_tags.append(f"model:{agent.model.id}")

        return self.create(
            name=name,
            components=components,
            description=description or f"Extracted from agent: {getattr(agent, 'name', 'unknown')}",
            author=author,
            tags=extra_tags,
            model_compatibility=[agent.model.id] if hasattr(agent, "model") and hasattr(agent.model, "id") else None,
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
  "change_description": "Updated instructions for clarity",
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

    # NEW: Include change description
    if prompt.change_description:
        data["change_description"] = prompt.change_description

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
        change_description=data.get("change_description"),
    )
```

---

## 6. Integration with Agent

### 6.1 Agent Priority Chain (Backward Compatibility)

When Agent integrates with SystemPromptEditor, the following priority chain applies:

```python
class Agent:
    """Agent with system prompt versioning support."""

    # Phase 1: Keep existing system_message attribute
    system_message: Optional[Union[str, Callable, Message]] = None

    # Phase 2: Add new system_prompt_version_id attribute
    system_prompt_version_id: Optional[str] = None
    system_prompt_editor: Optional[SystemPromptEditor] = None

    def get_system_message(self, session, ...):
        """Existing method - enhanced with versioning support."""

        # Priority 1: Versioned system prompt (if configured)
        if self.system_prompt_version_id and self.system_prompt_editor:
            prompt_content = self.system_prompt_editor.compose(
                self.system_prompt_version_id,
            )
            return Message(role=self.system_message_role, content=prompt_content)

        # Priority 2: Direct system_message (backward compatible)
        if self.system_message is not None:
            return self._process_system_message(self.system_message)

        # Priority 3: Build from components (current behavior)
        return self._build_system_message_from_components(...)
```

### 6.2 Current State (Read-Only Extraction)

```python
# Extract agent config to versioned prompt
editor = SystemPromptEditor()
prompt = editor.create_from_agent("my_agent_v1", agent)

# Get composed prompt for external use
composed = editor.compose(prompt.id)
```

### 6.3 Future State (Agent Modification)

When Agent is modified to support versioned prompts:

```python
# Configure agent to use versioned prompt
agent = Agent(
    name="support",
    system_prompt_version_id="prompt_abc123",
    system_prompt_editor=SystemPromptEditor(),
)

# Agent automatically uses versioned prompt in get_system_message()
response = agent.run("Help me with my subscription")
```

---

## 7. Memory and Knowledge Integration

### 7.1 Memory Manager Integration

The MemoryManager (`/libs/agno/agno/memory/manager.py`) injects memories into system prompts:

```python
# From memory/manager.py - System prompt includes existing memories
system_message_content += "<memories_from_previous_interactions>"
for _memory in user_memories:
    system_message_content += f"\n- {_memory.memory}"
system_message_content += "\n</memories_from_previous_interactions>\n\n"

# Optionally includes memory update capabilities
if self.enable_agentic_memory:
    system_message_content += (
        "\n<updating_user_memories>\n"
        "- You have access to the `update_user_memory` tool...\n"
        "</updating_user_memories>\n\n"
    )
```

**Integration as Component**:

```python
memory_component = SystemPromptComponent(
    type=PromptComponentType.MEMORIES,
    content=memory_markdown,  # Formatted list of memories
    xml_tag="memories_from_previous_interactions",
    order=80,
    enabled=True,
    metadata={
        "source": "MemoryManager",
        "strategy": "last_n",  # or "agentic", "first_n"
        "limit": 10
    }
)
```

### 7.2 Knowledge Integration

Knowledge documents are added to **user messages** (not system prompts), but knowledge instructions can be included as a component:

```python
# From agent.py lines 8578-8588
if self.add_knowledge_to_context and references is not None:
    user_msg_content_str += "\n\nUse the following references from the knowledge base:\n"
    user_msg_content_str += "<references>\n"
    user_msg_content_str += self._convert_documents_to_string(references.references) + "\n"
    user_msg_content_str += "</references>"
```

**Knowledge Instructions Component**:

```python
knowledge_component = SystemPromptComponent(
    type=PromptComponentType.CUSTOM,
    name="knowledge_instructions",
    content="""You have access to a knowledge base via the search_knowledge_base tool.
When the user asks questions that might be answered by knowledge base documents,
use the tool to find relevant information.""",
    order=50,
    xml_tag="knowledge_access",
    enabled=True,
)
```

### 7.3 Session Summary Integration

```python
session_summary_component = SystemPromptComponent(
    type=PromptComponentType.SESSION_SUMMARY,
    content=session_summary_text,
    xml_tag="summary_of_previous_interactions",
    order=85,
    enabled=True,
    metadata={
        "source": "SessionSummaryManager",
        "session_id": session.id
    }
)
```

---

## 8. Blast Radius Analysis

### 8.1 Summary

| Change | Files Modified | Risk | Rationale |
|--------|----------------|------|-----------|
| Add `PromptComponentType` | models.py | LOW | New enum, additive |
| Add `SystemPromptComponent` | models.py | LOW | New model, additive |
| Add `components` to `PromptVersion` | models.py | LOW | Optional field, no breaking change |
| Add `change_description` to `PromptVersion` | models.py | LOW | Optional field, additive |
| Enhance `PromptDiff` | models.py | LOW | Additional optional fields |
| Add component methods to `PromptManager` | manager.py | LOW | New methods, additive |
| Modify `MLflowPromptStore` serialization | mlflow_backend.py | LOW | Backward-compatible (optional field) |
| Add `SystemPromptEditor` | NEW FILE | NONE | New file |

### 8.2 No Breaking Changes

- All new fields are optional
- Existing methods unchanged
- Non-component prompts continue to work
- Existing MLflow artifacts remain readable

### 8.3 Side Effect Analysis

| Operation | Potential Side Effect | Mitigation |
|-----------|----------------------|------------|
| Component composition | Order changes output | Validate order uniqueness |
| Agent extraction | Missing attributes | Graceful handling with defaults |
| MLflow serialization | Large artifact size | Compress if needed |
| Version creation | Rapid version growth | Archival policy |

---

## 9. Benefits & Use Cases

### 9.1 For Prompt Engineers

- **Version control**: Track all changes with full history and descriptions
- **A/B testing**: Create experimental variants via forks
- **Snapshot releases**: Create named versions for specific deployments
- **Component reuse**: Share common prompt patterns across agents
- **Detailed documentation**: Export with full component breakdown

### 9.2 For Developers

- **Programmatic control**: Create, edit, and apply prompts via API
- **Integration**: Seamlessly works with existing Agent system
- **Template variables**: Parameterized prompts for dynamic behavior
- **Model compatibility**: Track which models work with which prompts

### 9.3 For Teams

- **Collaboration**: Tag and search prompts by team/project
- **Audit trail**: Full metadata including author, timestamp, change descriptions
- **Approval workflows**: Status transitions (draft → active → archived)
- **Production safety**: Snapshots prevent accidental changes

### 9.4 Use Case Examples

| Use Case | How SystemPromptEditor Helps |
|----------|------------------------------|
| Production deployment | Create snapshot, test, deploy with confidence |
| Prompt experimentation | Fork, modify, A/B test without affecting production |
| Team collaboration | Tag by team, search by author, review changes |
| Compliance/audit | Full traceability with change descriptions |
| Multi-model support | Track model compatibility per prompt version |

---

## 10. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Performance degradation** | Slow prompt composition | Low | Cache composed prompts, lazy-load components |
| **Storage growth** | Disk space exhaustion | Medium | Implement archival policy for old versions |
| **Migration complexity** | Integration errors | Low | Provide automated migration tools, clear docs |
| **Composability edge cases** | Incorrect prompt output | Medium | Comprehensive test suite with realistic prompts |
| **Race conditions** | Data inconsistency | Low | See MLFLOW_INTEGRATION.md limitations section |
| **Component ordering conflicts** | Unexpected output | Low | Validate order uniqueness, use 10-increment scale |

> **Cross-ref**: See `/libs/agno/agno/prompt_versioning/docs/MLFLOW_INTEGRATION.md` for detailed MLflow limitations and workarounds.

---

## 11. Future Enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| **Visual Editor** | Web UI for component editing | Medium |
| **Prompt Optimization** | AI-assisted suggestions for improvements | Low |
| **A/B Testing Framework** | Built-in evaluation and metrics | Medium |
| **Multi-language Support** | Generate prompts in different languages | Low |
| **Component Library** | Pre-built prompt components for common use cases | Medium |
| **Real-time Analytics** | Track which prompt versions perform best | Low |
| **Collaborative Editing** | Multi-user editing with conflict resolution | Low |
| **Prompt Chain Management** | Version entire workflows, not just single prompts | Medium |

---

## 12. Testing Strategy

### 12.1 Test Organization

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

### 12.2 Test Examples

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

def test_change_description_captured():
    """Change description is stored in version."""
    version = PromptVersion(
        id="test",
        name="test",
        template=PromptTemplate(content="test"),
        change_description="Updated role for premium support"
    )
    assert version.change_description == "Updated role for premium support"

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

def test_edit_component_creates_version_with_description(manager):
    """Editing creates new version with change description."""
    prompt = manager.create_system_prompt("test", [...])

    updated = manager.edit_component(
        prompt.id,
        PromptComponentType.ROLE,
        "New content",
        change_description="Updated role for premium support"
    )

    assert updated.version == 2
    assert updated.parent_id == prompt.id
    assert updated.change_description == "Updated role for premium support"

def test_reorder_components(manager):
    """Reordering creates new version."""
    prompt = manager.create_system_prompt("test", [
        SystemPromptComponent(type=PromptComponentType.ROLE, content="role", order=20),
        SystemPromptComponent(type=PromptComponentType.INSTRUCTIONS, content="inst", order=30),
    ])

    updated = manager.reorder_components(
        prompt.id,
        {PromptComponentType.INSTRUCTIONS: 15}  # Move before role
    )

    components = manager.get_components(updated.id)
    assert components[0].type == PromptComponentType.INSTRUCTIONS

# E2E: test_component_workflows.py

def test_full_iteration_workflow(editor):
    """Create, edit, snapshot, fork."""
    # Create
    v1 = editor.create("agent", components)

    # Edit with description
    v2 = editor.edit_component(
        v1.id,
        PromptComponentType.ROLE,
        "New role",
        change_description="Improved role clarity"
    )

    # Add guardrails
    v3 = editor.add_component(v2.id, guardrails)

    # Snapshot
    prod = editor.snapshot(v3.id, "production-v1")

    # Fork for A/B
    variant = editor.fork(v3.id, "agent_variant_b")

    # Verify
    assert prod.snapshot_name == "production-v1"
    assert variant.forked_from == v3.id

def test_export_as_markdown(editor):
    """Export produces valid markdown."""
    prompt = editor.create("test", components)
    md = editor.export_as_markdown(prompt.id)

    assert "# System Prompt: test" in md
    assert "## Components" in md
```

### 12.3 Coverage Requirements

| Category | Target | Focus |
|----------|--------|-------|
| Unit | 95% | Model validation, composition |
| Integration | 85% | Manager + Store |
| E2E | 80% | Full workflows |

---

## 13. Code Examples

### 13.1 Creating a System Prompt from Agent

```python
from agno.prompt_versioning.system_prompt_editor import SystemPromptEditor
from agno.agent import Agent

# Initialize editor
editor = SystemPromptEditor(tracking_uri="mlruns")

# Create an agent
agent = Agent(
    name="customer_support",
    role="A friendly customer support specialist",
    instructions=[
        "Always respond with empathy",
        "Provide detailed solutions",
        "Escalate complex issues"
    ],
    description="Customer support agent for SaaS platform"
)

# Capture current prompt as versioned artifact
sys_prompt = editor.create_from_agent(
    name="customer_support_main",
    agent=agent,
    author="alice@company.com",
    tags=["production", "customer_support"],
    description="Main customer support system prompt"
)

print(f"Created system prompt version: {sys_prompt.id}")
print(f"Version number: {sys_prompt.version}")
print(f"Composed prompt length: {len(sys_prompt.template.content)}")
```

### 13.2 Editing Components with Traceability

```python
# Update the role with more specific guidance
updated = editor.edit_component(
    prompt_id=sys_prompt.id,
    component_type=PromptComponentType.ROLE,
    new_content="""You are an expert customer support specialist for our SaaS platform.
You combine technical knowledge with empathy to solve customer issues.
You are authorized to:
- Provide refunds for unsatisfied customers
- Offer service upgrades
- Escalate to technical team when needed""",
    author="alice@company.com",
    change_description="Added authorization details and upgrade authority"
)

print(f"Updated to version: {updated.version}")
print(f"Change: {updated.change_description}")
```

### 13.3 Adding Custom Components (Guardrails)

```python
from agno.prompt_versioning.models import SystemPromptComponent, PromptComponentType

# Add guardrails as a custom component
guardrails = SystemPromptComponent(
    type=PromptComponentType.CUSTOM,
    name="guardrails",
    content="""IMPORTANT CONSTRAINTS:
- Never share internal pricing with customers
- Never promise features not in our roadmap
- Always acknowledge response time limits during outages
- Maintain professional tone even with frustrated customers""",
    order=25,  # Right after role
    xml_tag="guardrails",
    enabled=True,
    metadata={"category": "safety"}
)

updated = editor.add_component(
    prompt_id=sys_prompt.id,
    component=guardrails,
    author="alice@company.com",
    change_description="Added safety guardrails for customer interactions"
)
```

### 13.4 Creating Snapshots for Deployment

```python
# Create production snapshot
prod_snapshot = editor.snapshot(
    prompt_id=updated.id,
    snapshot_name="production-2026-01",
    description="January 2026 production release"
)

# Create staging snapshot for testing
staging_snapshot = editor.snapshot(
    prompt_id=updated.id,
    snapshot_name="staging-experimental",
    description="Experimental features for staging environment"
)

print(f"Production: {prod_snapshot.snapshot_name}")
print(f"Staging: {staging_snapshot.snapshot_name}")
```

### 13.5 Comparing Versions

```python
# See what changed between versions
diff = editor.compare(
    from_id=sys_prompt.id,
    to_id=updated.id
)

print("Change Description:", diff.change_description)
print("\nComponents Changed:")
for component_type, changes in diff.components_changed.items():
    print(f"  {component_type}:")
    print(f"    Old: {changes['old'][:50]}...")
    print(f"    New: {changes['new'][:50]}...")

print("\nComponents Added:")
for comp in diff.components_added:
    print(f"  - {comp['type']}: {comp.get('name', 'N/A')}")
```

### 13.6 Applying to Agent at Runtime

```python
# Apply versioned prompt to agent
prod_version = editor.get_by_name("customer_support_main", version=3)
editor.apply_to_agent(
    prompt_id=prod_version.id,
    agent=agent,
    override_system_message=True
)

# Now when agent.get_system_message() is called,
# it uses the versioned system prompt
response = agent.run("Help me with my subscription")
```

### 13.7 Exporting for Documentation

```python
# Export as markdown for documentation
markdown = editor.export_as_markdown(
    prompt_id=prod_version.id,
    include_metadata=True,
    include_history=True
)

with open("prompt_documentation.md", "w") as f:
    f.write(markdown)

# Output includes:
# - Component breakdown
# - Variables used
# - Model compatibility
# - Version history
# - Change annotations
```

### 13.8 Searching and Filtering

```python
# Find production prompts for customer support
prompts = editor.search(
    tags=["production", "customer_support"],
    author="alice@company.com"
)

for prompt in prompts:
    print(f"{prompt.name} v{prompt.version}: {prompt.metadata.description}")

# Find prompts compatible with specific model
gpt4_prompts = editor.get_agent_compatible_versions("gpt-4")
for p in gpt4_prompts:
    print(f"- {p.name}")
```

---

## 14. Implementation Checklist

> **Status**: ✅ Complete (2026-01-17)

### Phase 1: Models

- [x] Add `PromptComponentType` enum to `models.py`
- [x] Add `SystemPromptComponent` model to `models.py`
- [x] Add `components` field to `PromptVersion`
- [x] Add `change_description` field to `PromptVersion`
- [x] Add `is_system_prompt()`, `get_component()` methods
- [x] Enhance `PromptDiff.compute()` for component diff
- [x] Unit tests (41 tests in `test_component_models.py`)

### Phase 2: Storage

- [x] Update `_prompt_to_artifact()` for components
- [x] Update `_artifact_to_prompt()` for components
- [x] Integration tests (17 tests in `test_mlflow_components.py`)

### Phase 3: Manager

- [x] Add `create_system_prompt()` method
- [x] Add `edit_component()` method with `change_description`
- [x] Add `add_component()`, `remove_component()` methods
- [x] Add `reorder_components()` method
- [x] Add `get_components()` method
- [x] Add `search_system_prompts()` method
- [x] Integration tests (38 tests in `test_manager_components.py`)

### Phase 4: SystemPromptEditor

- [x] Create `system_prompt_editor.py`
- [x] Implement Agent extraction (`create_from_agent`)
- [x] Implement Agent application (`apply_to_agent`)
- [x] Implement `preview_components()` (plural, returns Dict)
- [x] Implement `get_agent_compatible_versions()`
- [x] Implement `export_as_markdown()`
- [x] Implement convenience delegation methods
- [x] E2E tests (19 tests in `test_system_prompt_editor.py`)
- [x] Documentation (REFERENCE.md, COMPREHENSIVE_GUIDE.md updated)

### Review Checkpoints

- [x] Design Review: Before Phase 1
- [x] Code Review: After each phase
- [x] Final Review: After Phase 4

### Test Summary

| Test Suite | Tests | Location |
|------------|-------|----------|
| Component Models | 41 | `tests/unit/test_component_models.py` |
| MLflow Serialization | 17 | `tests/integration/test_mlflow_components.py` |
| Manager Components | 38 | `tests/integration/test_manager_components.py` |
| SystemPromptEditor E2E | 19 | `tests/e2e/test_system_prompt_editor.py` |
| **Total New Tests** | **115** | |
| **Total Suite** | **313** | All prompt versioning tests |

---

## 15. Cross-Reference Index

### File Paths and Line Numbers

| Reference | File | Lines | Description |
|-----------|------|-------|-------------|
| Agent.get_system_message | `/libs/agno/agno/agent/agent.py` | 7742-8083 | System prompt construction |
| XML tag structure | `/libs/agno/agno/agent/agent.py` | 7742-8083 | Tag conventions |
| MemoryManager prompt injection | `/libs/agno/agno/memory/manager.py` | ~200-250 | Memory to prompt |
| Knowledge references | `/libs/agno/agno/agent/agent.py` | 8578-8588 | RAG integration |
| PromptManager | `/libs/agno/agno/prompt_versioning/manager.py` | All | Core versioning API |
| PromptVersion | `/libs/agno/agno/prompt_versioning/models.py` | ~100-200 | Version model |
| MLflowPromptStore | `/libs/agno/agno/prompt_versioning/mlflow_backend.py` | All | Storage backend |
| MLflow limitations | `/libs/agno/agno/prompt_versioning/docs/MLFLOW_INTEGRATION.md` | Section 8 | Workarounds |

### Related Documentation

| Document | Location | Description |
|----------|----------|-------------|
| REFERENCE.md | `/libs/agno/agno/prompt_versioning/REFERENCE.md` | Quick API reference |
| COMPREHENSIVE_GUIDE.md | `/libs/agno/agno/prompt_versioning/docs/COMPREHENSIVE_GUIDE.md` | Full user guide |
| MLFLOW_INTEGRATION.md | `/libs/agno/agno/prompt_versioning/docs/MLFLOW_INTEGRATION.md` | MLflow deep dive |
| SYSTEM_PROMPT_EDITOR_DESIGN.md | `/libs/agno/agno/prompt_versioning/docs/SYSTEM_PROMPT_EDITOR_DESIGN.md` | High-level design |

### Model Cross-References

| Model | Extends/Uses | Purpose |
|-------|--------------|---------|
| `SystemPromptComponent` | Pydantic BaseModel | Individual component |
| `PromptVersion.components` | List[SystemPromptComponent] | Native storage |
| `PromptDiff.components_*` | Component diff fields | Change tracking |
| `SystemPromptEditor` | PromptManager | Agent integration |

---

## Appendix: Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `models.py` | MODIFY | Add PromptComponentType, SystemPromptComponent, modify PromptVersion, PromptDiff |
| `mlflow_backend.py` | MODIFY | Component and change_description serialization |
| `manager.py` | MODIFY | Add component-aware methods including reorder_components |
| `system_prompt_editor.py` | NEW | Agent integration layer with export and preview |

---

*End of Specification*
