# SystemPromptEditor API Specification

> **Status**: Draft Specification
> **Version**: 0.1.0
> **Last Updated**: 2026-01-17
> **Authors**: Engineering Team

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Principles](#2-design-principles)
3. [Existing Contract Analysis](#3-existing-contract-analysis)
4. [Data Model Specification](#4-data-model-specification)
5. [API Specification](#5-api-specification)
6. [Integration Points](#6-integration-points)
7. [Blast Radius Analysis](#7-blast-radius-analysis)
8. [Testing Strategy](#8-testing-strategy)
9. [Migration & Compatibility](#9-migration--compatibility)
10. [Implementation Checklist](#10-implementation-checklist)

---

## 1. Overview

### 1.1 Purpose

The SystemPromptEditor provides a specialized interface for managing Agno Agent system prompts as first-class versioned artifacts. It **extends** (not replaces) the existing prompt versioning system by adding:

- Component-based decomposition of system prompts
- Agent-aware prompt extraction and application
- Semantic understanding of Agno's XML tag structure

### 1.2 Scope

**In Scope:**
- Decomposing Agent prompts into typed components
- Storing components via existing PromptVersion.metadata.custom
- Composing components back into system prompts
- Integration with PromptManager for all persistence operations

**Out of Scope:**
- Modifying Agent.get_system_message() internals
- Creating new persistence backends
- Real-time prompt assembly (runtime concern)

### 1.3 Key Constraint

> **CRITICAL**: All data MUST flow through existing `PromptVersion` and `PromptManager` contracts.
> No parallel data models or storage mechanisms.

---

## 2. Design Principles

### 2.1 Adherence to Existing Contracts

```
┌─────────────────────────────────────────────────────────────────┐
│                    SystemPromptEditor                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              COMPOSITION LAYER (NEW)                     │    │
│  │   - Component decomposition                              │    │
│  │   - XML tag handling                                     │    │
│  │   - Agent integration                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              PromptManager (EXISTING)                    │    │
│  │   - create(), edit(), snapshot(), fork()                 │    │
│  │   - get(), search(), compare()                           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              MLflowPromptStore (EXISTING)                │    │
│  │   - save(), load(), search()                             │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Extension Points Used

| Existing Contract | Extension Mechanism | Purpose |
|-------------------|---------------------|---------|
| `PromptMetadata.custom` | Dict[str, Any] | Store component definitions |
| `PromptMetadata.tags` | List[str] | Tag with "system_prompt", component types |
| `PromptVersion.template.content` | str | Store composed prompt |
| `PromptManager` | Delegation | All CRUD operations |

### 2.3 Principles Checklist

- [ ] **Single Source of Truth**: All data in PromptVersion
- [ ] **Backward Compatible**: Existing prompts unaffected
- [ ] **Composition Over Inheritance**: Wrap, don't extend classes
- [ ] **Explicit Over Implicit**: No magic, all operations traceable
- [ ] **Fail Fast**: Validate early, error clearly

---

## 3. Existing Contract Analysis

### 3.1 PromptVersion (models.py:112-204)

**Immutable Fields (DO NOT MODIFY):**
```python
class PromptVersion(BaseModel):
    id: str                           # Unique identifier
    name: str                         # Validated: ^[\w\-\.]+$
    version: int                      # >= 1
    template: PromptTemplate          # Content + variables
    status: PromptStatus              # DRAFT|ACTIVE|ARCHIVED|SNAPSHOT
    metadata: PromptMetadata          # ← Extension point
    parent_id: Optional[str]          # Lineage tracking
    forked_from: Optional[str]        # Fork tracking
    created_at: datetime              # Immutable after creation
    updated_at: datetime              # Set on modification
    snapshot_name: Optional[str]      # For snapshots
    content_hash: str                 # Auto-computed SHA256[:16]
```

**Cross-Reference**: See models.py lines 112-204 for full implementation.

### 3.2 PromptMetadata (models.py:21-46)

**Extension Point via `custom` field:**
```python
class PromptMetadata(BaseModel):
    author: Optional[str]
    description: Optional[str]
    tags: List[str]                   # ← Tag with "system_prompt"
    model_compatibility: List[str]
    use_case: Optional[str]
    custom: Dict[str, Any]            # ← Store components here
```

**IMPORTANT**: The `custom` field is the designated extension point. All system prompt component data MUST be stored here.

### 3.3 PromptTemplate (models.py:48-109)

**Capabilities:**
- Variable extraction: `{{variable}}` pattern
- Full render: `render(**kwargs)` - requires all variables
- Partial render: `partial_render(**kwargs)` - fills available

**Constraint**: Template variables use `{{name}}` syntax. System prompt components should NOT introduce conflicting syntax.

### 3.4 PromptManager (manager.py:24-605)

**Available Operations (delegate to these):**
| Method | Purpose | Use in SystemPromptEditor |
|--------|---------|---------------------------|
| `create()` | New prompt | Create system prompt |
| `edit()` | New version | Edit component |
| `snapshot()` | Named snapshot | Snapshot system prompt |
| `fork()` | Independent copy | Fork system prompt |
| `get()` | Load by ID | Get system prompt |
| `get_by_name()` | Load by name | Get by name |
| `search()` | Find prompts | Search system prompts |
| `compare()` | Diff versions | Compare versions |
| `render()` | Substitute vars | Render composed prompt |

---

## 4. Data Model Specification

### 4.1 PromptComponentType (NEW)

```python
# File: prompt_versioning/system_prompt_models.py
# Cross-ref: Agent.get_system_message() at agent/agent.py:7742-8083

from enum import Enum

class PromptComponentType(str, Enum):
    """
    Enumeration of system prompt component types.

    Maps 1:1 to Agent.get_system_message() construction order.
    See: agent/agent.py lines 7742-8083

    NOTE: Order values (10, 20, 30...) allow insertion of custom
    components between standard ones without renumbering.
    """

    # Core identity (agent/agent.py:7760-7780)
    DESCRIPTION = "description"          # Order: 10
    ROLE = "role"                         # Order: 20

    # Behavioral (agent/agent.py:7780-7850)
    INSTRUCTIONS = "instructions"         # Order: 30
    TOOL_INSTRUCTIONS = "tool_instructions"  # Order: 40
    EXPECTED_OUTPUT = "expected_output"   # Order: 50

    # Context (agent/agent.py:7850-7950)
    ADDITIONAL_INFO = "additional_info"   # Order: 60
    ADDITIONAL_CONTEXT = "additional_context"  # Order: 70

    # Memory (memory/manager.py integration)
    MEMORIES = "memories"                 # Order: 80
    SESSION_SUMMARY = "session_summary"   # Order: 85

    # Knowledge (knowledge/knowledge.py integration)
    CULTURAL_KNOWLEDGE = "cultural_knowledge"  # Order: 90

    # Runtime (agent/agent.py:7950-8000)
    SESSION_STATE = "session_state"       # Order: 95

    # Extension point
    CUSTOM = "custom"                     # Order: user-defined
```

### 4.2 SystemPromptComponent (NEW)

```python
# File: prompt_versioning/system_prompt_models.py

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator

class SystemPromptComponent(BaseModel):
    """
    Individual component of a system prompt.

    Stored in PromptMetadata.custom["components"] as list of dicts.

    Design Notes:
    - `order` uses 10-increment scale for insertability
    - `xml_tag` follows Agno convention: <tag_name>content</tag_name>
    - `metadata` for component-specific config (e.g., memory limits)

    Cross-ref: Agent XML tags at agent/agent.py:7742-8083
    """

    type: PromptComponentType = Field(
        ...,
        description="Component type from PromptComponentType enum"
    )

    content: str = Field(
        ...,
        description="The component content (may include {{variables}})"
    )

    name: Optional[str] = Field(
        default=None,
        description="Custom name for CUSTOM type components"
    )

    order: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Render order (0-100). Standard types use 10-increment scale."
    )

    xml_tag: Optional[str] = Field(
        default=None,
        description="XML tag wrapper. E.g., 'your_role' -> <your_role>...</your_role>"
    )

    enabled: bool = Field(
        default=True,
        description="Whether to include in composition"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Component-specific metadata (e.g., memory_limit, source)"
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
        """
        Get default order for a component type.

        Returns:
            Default order value (10-100 scale)
        """
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
            PromptComponentType.CUSTOM: 50,  # Middle by default
        }
        return orders.get(component_type, 50)

    @classmethod
    def get_default_xml_tag(cls, component_type: PromptComponentType) -> Optional[str]:
        """
        Get default XML tag for a component type.

        Cross-ref: agent/agent.py XML conventions

        Returns:
            XML tag name or None if no wrapper
        """
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

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize for storage in PromptMetadata.custom.

        NOTE: Uses model_dump() for Pydantic v2 compatibility.
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemPromptComponent":
        """Deserialize from PromptMetadata.custom storage."""
        return cls(**data)
```

### 4.3 Storage Schema

Components are stored in `PromptMetadata.custom` with this schema:

```python
# PromptMetadata.custom schema for system prompts
{
    "type": "system_prompt",           # Discriminator
    "version": "1.0",                   # Schema version for migration
    "agent_source": {                   # Optional: source agent info
        "name": "customer_support",
        "class": "agno.agent.Agent"
    },
    "components": [                     # List of SystemPromptComponent dicts
        {
            "type": "role",
            "content": "You are a helpful assistant.",
            "name": null,
            "order": 20,
            "xml_tag": "your_role",
            "enabled": true,
            "metadata": {}
        },
        {
            "type": "instructions",
            "content": "- Be concise\n- Be helpful",
            "name": null,
            "order": 30,
            "xml_tag": "instructions",
            "enabled": true,
            "metadata": {}
        }
    ],
    "composition_options": {            # Optional composition config
        "include_xml_tags": true,
        "separator": "\n\n"
    }
}
```

### 4.4 Tag Convention

System prompts are identified by tags in `PromptMetadata.tags`:

```python
# Required tag for system prompts
"system_prompt"

# Component type tags (auto-added)
"component:role"
"component:instructions"
"component:custom:guardrails"  # For custom components

# Optional semantic tags
"agent:customer_support"
"model:gpt-4"
```

---

## 5. API Specification

### 5.1 SystemPromptEditor Class

```python
# File: prompt_versioning/system_prompt_editor.py

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.models import PromptVersion, PromptMetadata
from agno.prompt_versioning.system_prompt_models import (
    PromptComponentType,
    SystemPromptComponent,
)

if TYPE_CHECKING:
    from agno.agent import Agent

# =============================================================================
# CONSTANTS
# =============================================================================

SYSTEM_PROMPT_TAG = "system_prompt"
SCHEMA_VERSION = "1.0"


class SystemPromptEditor:
    """
    High-level editor for system prompts with component-based management.

    Delegates all persistence to PromptManager. Adds:
    - Component decomposition and composition
    - Agent prompt extraction
    - XML tag handling

    Design:
    - COMPOSITION over inheritance (wraps PromptManager)
    - All data stored via PromptMetadata.custom
    - No direct MLflow access (single responsibility)

    Cross-references:
    - PromptManager: manager.py
    - Agent.get_system_message(): agent/agent.py:7742-8083
    - MemoryManager: memory/manager.py

    Example:
        >>> editor = SystemPromptEditor(tracking_uri="mlruns")
        >>>
        >>> # Create from components
        >>> sys_prompt = editor.create(
        ...     name="support_agent",
        ...     components=[
        ...         SystemPromptComponent(
        ...             type=PromptComponentType.ROLE,
        ...             content="You are a support specialist."
        ...         ),
        ...         SystemPromptComponent(
        ...             type=PromptComponentType.INSTRUCTIONS,
        ...             content="- Be helpful\\n- Be concise"
        ...         )
        ...     ]
        ... )
        >>>
        >>> # Edit a specific component
        >>> updated = editor.edit_component(
        ...     sys_prompt.id,
        ...     PromptComponentType.ROLE,
        ...     "You are a SENIOR support specialist."
        ... )
    """

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def __init__(
        self,
        tracking_uri: str = "mlruns",
        experiment_prefix: str = "system_prompts",
    ):
        """
        Initialize SystemPromptEditor.

        Args:
            tracking_uri: MLflow tracking URI (passed to PromptManager)
            experiment_prefix: Experiment prefix (passed to PromptManager)

        Note:
            Creates a NEW PromptManager instance with system_prompt-specific
            experiment prefix to isolate from regular prompts.
        """
        self._manager = PromptManager(
            tracking_uri=tracking_uri,
            experiment_prefix=experiment_prefix,
        )

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def manager(self) -> PromptManager:
        """
        Access underlying PromptManager.

        Use for operations not wrapped by SystemPromptEditor.

        WARNING: Direct manager operations bypass component validation.
        """
        return self._manager

    # =========================================================================
    # CREATION METHODS
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
        Create a new system prompt from components.

        Args:
            name: Unique prompt name (alphanumeric, underscores, hyphens, dots)
            components: List of SystemPromptComponent objects
            description: Human-readable description
            author: Author name
            tags: Additional tags (system_prompt tag added automatically)
            model_compatibility: Compatible model identifiers

        Returns:
            Created PromptVersion with components in metadata.custom

        Raises:
            ValueError: If name invalid or duplicate component types

        Side Effects:
            - Creates MLflow experiment if not exists
            - Creates MLflow run with prompt artifact

        Blast Radius: LOW
            - Creates new data only
            - No modification of existing prompts

        Example:
            >>> components = [
            ...     SystemPromptComponent(
            ...         type=PromptComponentType.ROLE,
            ...         content="You are a helpful assistant."
            ...     )
            ... ]
            >>> prompt = editor.create("my_agent", components)
        """
        # Validate no duplicate non-CUSTOM components
        self._validate_components(components)

        # Compose content from components
        content = self._compose_content(components)

        # Build custom metadata
        custom_metadata = self._build_custom_metadata(components)

        # Build tags
        all_tags = self._build_tags(components, tags)

        # Delegate to PromptManager
        return self._manager.create(
            name=name,
            content=content,
            description=description,
            author=author,
            tags=all_tags,
            model_compatibility=model_compatibility,
            custom_metadata=custom_metadata,
        )

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
            description: Human-readable description
            author: Author name
            tags: Additional tags

        Returns:
            Created PromptVersion with extracted components

        Note:
            Extracts static configuration only. Runtime values (memories,
            session state) are captured as empty placeholders.

        Cross-ref: Agent attributes at agent/agent.py:200-500

        Blast Radius: LOW
            - Read-only access to agent
            - Creates new prompt only

        Example:
            >>> agent = Agent(role="Helper", instructions=["Be nice"])
            >>> prompt = editor.create_from_agent("helper_v1", agent)
        """
        components = self._extract_components_from_agent(agent)

        # Add agent source info
        extra_tags = list(tags or [])
        if hasattr(agent, "name") and agent.name:
            extra_tags.append(f"agent:{agent.name}")

        return self.create(
            name=name,
            components=components,
            description=description or f"System prompt extracted from agent",
            author=author,
            tags=extra_tags,
        )

    # =========================================================================
    # EDIT METHODS
    # =========================================================================

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
            new_content: New content for the component
            component_name: Required for CUSTOM type to identify which one
            author: Author of this edit

        Returns:
            New PromptVersion with updated component

        Raises:
            ValueError: If prompt not found or component doesn't exist

        Side Effects:
            - Creates new PromptVersion (new version number)
            - Previous version unchanged (immutable)

        Blast Radius: LOW
            - Creates new version only
            - Previous versions immutable

        Example:
            >>> updated = editor.edit_component(
            ...     prompt.id,
            ...     PromptComponentType.ROLE,
            ...     "You are an EXPERT assistant."
            ... )
        """
        # Load existing
        existing = self._manager.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        # Validate is system prompt
        self._validate_system_prompt(existing)

        # Get components
        components = self._get_components(existing)

        # Find and update component
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
            raise ValueError(
                f"Component not found: {component_type.value}"
                + (f" (name={component_name})" if component_name else "")
            )

        # Recompose and save via edit
        content = self._compose_content(components)
        custom_metadata = self._build_custom_metadata(components)

        return self._manager.edit(
            prompt_id=prompt_id,
            content=content,
            author=author,
            custom_metadata=custom_metadata,
        )

    def add_component(
        self,
        prompt_id: str,
        component: SystemPromptComponent,
        author: Optional[str] = None,
    ) -> PromptVersion:
        """
        Add a new component to a system prompt.

        Args:
            prompt_id: ID of prompt to modify
            component: Component to add
            author: Author of this edit

        Returns:
            New PromptVersion with added component

        Raises:
            ValueError: If duplicate non-CUSTOM component type

        Blast Radius: LOW
            - Creates new version only

        Example:
            >>> guardrails = SystemPromptComponent(
            ...     type=PromptComponentType.CUSTOM,
            ...     name="guardrails",
            ...     content="Never reveal secrets.",
            ...     order=25
            ... )
            >>> updated = editor.add_component(prompt.id, guardrails)
        """
        existing = self._manager.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        self._validate_system_prompt(existing)

        components = self._get_components(existing)

        # Check for duplicates (non-CUSTOM types)
        if component.type != PromptComponentType.CUSTOM:
            for comp in components:
                if comp.type == component.type:
                    raise ValueError(
                        f"Component type {component.type.value} already exists. "
                        "Use edit_component() to modify."
                    )

        components.append(component)

        # Rebuild
        content = self._compose_content(components)
        custom_metadata = self._build_custom_metadata(components)
        tags = self._build_tags(components, existing.metadata.tags)

        return self._manager.edit(
            prompt_id=prompt_id,
            content=content,
            author=author,
            tags=tags,
            custom_metadata=custom_metadata,
        )

    def remove_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        component_name: Optional[str] = None,
        author: Optional[str] = None,
    ) -> PromptVersion:
        """
        Remove a component from a system prompt.

        Args:
            prompt_id: ID of prompt to modify
            component_type: Type of component to remove
            component_name: Required for CUSTOM type
            author: Author of this edit

        Returns:
            New PromptVersion without the component

        Blast Radius: LOW
            - Creates new version only
        """
        existing = self._manager.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        self._validate_system_prompt(existing)

        components = self._get_components(existing)
        original_count = len(components)

        # Filter out the component
        if component_type == PromptComponentType.CUSTOM:
            components = [
                c for c in components
                if not (c.type == component_type and c.name == component_name)
            ]
        else:
            components = [c for c in components if c.type != component_type]

        if len(components) == original_count:
            raise ValueError(f"Component not found: {component_type.value}")

        # Rebuild
        content = self._compose_content(components)
        custom_metadata = self._build_custom_metadata(components)
        tags = self._build_tags(components, existing.metadata.tags)

        return self._manager.edit(
            prompt_id=prompt_id,
            content=content,
            author=author,
            tags=tags,
            custom_metadata=custom_metadata,
        )

    def reorder_components(
        self,
        prompt_id: str,
        new_order: Dict[str, int],
        author: Optional[str] = None,
    ) -> PromptVersion:
        """
        Change component ordering.

        Args:
            prompt_id: ID of prompt to modify
            new_order: Dict mapping component type (or "custom:name") to order
            author: Author of this edit

        Returns:
            New PromptVersion with reordered components

        Example:
            >>> updated = editor.reorder_components(
            ...     prompt.id,
            ...     {"role": 10, "custom:guardrails": 15, "instructions": 20}
            ... )
        """
        existing = self._manager.get(prompt_id)
        if existing is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        self._validate_system_prompt(existing)

        components = self._get_components(existing)

        # Apply new orders
        for comp in components:
            key = comp.type.value
            if comp.type == PromptComponentType.CUSTOM:
                key = f"custom:{comp.name}"

            if key in new_order:
                comp.order = new_order[key]

        # Rebuild (order is applied in _compose_content)
        content = self._compose_content(components)
        custom_metadata = self._build_custom_metadata(components)

        return self._manager.edit(
            prompt_id=prompt_id,
            content=content,
            author=author,
            custom_metadata=custom_metadata,
        )

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def get(self, prompt_id: str) -> Optional[PromptVersion]:
        """
        Get a system prompt by ID.

        Delegates to PromptManager.get().
        """
        return self._manager.get(prompt_id)

    def get_by_name(
        self,
        name: str,
        version: Optional[int] = None,
    ) -> Optional[PromptVersion]:
        """
        Get a system prompt by name and optional version.

        Delegates to PromptManager.get_by_name().
        """
        return self._manager.get_by_name(name, version)

    def get_components(self, prompt_id: str) -> List[SystemPromptComponent]:
        """
        Get components of a system prompt.

        Args:
            prompt_id: ID of the prompt

        Returns:
            List of SystemPromptComponent objects sorted by order

        Raises:
            ValueError: If prompt not found or not a system prompt
        """
        prompt = self._manager.get(prompt_id)
        if prompt is None:
            raise ValueError(f"Prompt not found: {prompt_id}")

        self._validate_system_prompt(prompt)

        components = self._get_components(prompt)
        return sorted(components, key=lambda c: c.order)

    def search(
        self,
        name_pattern: Optional[str] = None,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
        component_types: Optional[List[PromptComponentType]] = None,
    ) -> List[PromptVersion]:
        """
        Search system prompts.

        Args:
            name_pattern: Pattern to match prompt names
            tags: Tags that must be present
            author: Author filter
            component_types: Filter by component types present

        Returns:
            List of matching system prompts
        """
        # Always filter to system prompts
        search_tags = [SYSTEM_PROMPT_TAG]
        if tags:
            search_tags.extend(tags)

        # Add component type filters
        if component_types:
            for ct in component_types:
                search_tags.append(f"component:{ct.value}")

        return self._manager.search(
            name_pattern=name_pattern,
            tags=search_tags,
            author=author,
        )

    # =========================================================================
    # VERSIONING METHODS (DELEGATED)
    # =========================================================================

    def snapshot(
        self,
        prompt_id: str,
        snapshot_name: str,
        description: Optional[str] = None,
    ) -> PromptVersion:
        """
        Create a named snapshot.

        Delegates to PromptManager.snapshot().

        Blast Radius: LOW - creates new immutable version
        """
        return self._manager.snapshot(prompt_id, snapshot_name, description)

    def fork(
        self,
        prompt_id: str,
        new_name: str,
        description: Optional[str] = None,
        author: Optional[str] = None,
    ) -> PromptVersion:
        """
        Fork a system prompt.

        Delegates to PromptManager.fork().

        Blast Radius: LOW - creates new independent prompt
        """
        return self._manager.fork(prompt_id, new_name, description, author)

    def compare(
        self,
        prompt_id_1: str,
        prompt_id_2: str,
    ) -> Dict[str, Any]:
        """
        Compare two system prompt versions with component-level diff.

        Returns:
            Dict with:
                - content_diff: PromptDiff from PromptManager
                - components_added: List of added components
                - components_removed: List of removed components
                - components_changed: Dict of changed components
        """
        # Get base diff
        base_diff = self._manager.compare(prompt_id_1, prompt_id_2)

        # Get component-level diff
        p1 = self._manager.get(prompt_id_1)
        p2 = self._manager.get(prompt_id_2)

        comp1 = self._get_components(p1) if self._is_system_prompt(p1) else []
        comp2 = self._get_components(p2) if self._is_system_prompt(p2) else []

        # Build component key -> component maps
        def comp_key(c: SystemPromptComponent) -> str:
            if c.type == PromptComponentType.CUSTOM:
                return f"custom:{c.name}"
            return c.type.value

        map1 = {comp_key(c): c for c in comp1}
        map2 = {comp_key(c): c for c in comp2}

        keys1 = set(map1.keys())
        keys2 = set(map2.keys())

        added = [map2[k].to_dict() for k in (keys2 - keys1)]
        removed = [map1[k].to_dict() for k in (keys1 - keys2)]
        changed = {}

        for k in (keys1 & keys2):
            if map1[k].content != map2[k].content:
                changed[k] = {
                    "old": map1[k].content,
                    "new": map2[k].content,
                }

        return {
            "content_diff": base_diff.model_dump(),
            "components_added": added,
            "components_removed": removed,
            "components_changed": changed,
        }

    # =========================================================================
    # COMPOSITION METHODS
    # =========================================================================

    def compose(
        self,
        prompt_id: str,
        **variables: Any,
    ) -> str:
        """
        Compose and render a system prompt.

        Args:
            prompt_id: ID of the prompt
            **variables: Variables to substitute

        Returns:
            Fully composed and rendered system prompt string
        """
        return self._manager.render(prompt_id=prompt_id, **variables)

    def preview_component(
        self,
        prompt_id: str,
        component_type: PromptComponentType,
        component_name: Optional[str] = None,
        **variables: Any,
    ) -> str:
        """
        Preview a single component with optional variable rendering.

        Args:
            prompt_id: ID of the prompt
            component_type: Type of component to preview
            component_name: Name for CUSTOM components
            **variables: Variables to substitute

        Returns:
            Rendered component content
        """
        components = self.get_components(prompt_id)

        for comp in components:
            if comp.type == component_type:
                if component_type == PromptComponentType.CUSTOM:
                    if comp.name == component_name:
                        return self._render_component(comp, variables)
                else:
                    return self._render_component(comp, variables)

        raise ValueError(f"Component not found: {component_type.value}")

    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================

    def _validate_components(
        self,
        components: List[SystemPromptComponent]
    ) -> None:
        """
        Validate component list.

        Raises:
            ValueError: If duplicate non-CUSTOM types
        """
        seen_types = set()
        for comp in components:
            if comp.type != PromptComponentType.CUSTOM:
                if comp.type in seen_types:
                    raise ValueError(
                        f"Duplicate component type: {comp.type.value}"
                    )
                seen_types.add(comp.type)

    def _validate_system_prompt(self, prompt: PromptVersion) -> None:
        """
        Validate that a prompt is a system prompt.

        Raises:
            ValueError: If not a system prompt
        """
        if not self._is_system_prompt(prompt):
            raise ValueError(
                f"Prompt {prompt.id} is not a system prompt. "
                f"Missing '{SYSTEM_PROMPT_TAG}' tag or custom metadata."
            )

    def _is_system_prompt(self, prompt: PromptVersion) -> bool:
        """Check if prompt is a system prompt."""
        if SYSTEM_PROMPT_TAG not in prompt.metadata.tags:
            return False
        custom = prompt.metadata.custom
        return custom.get("type") == "system_prompt"

    def _get_components(
        self,
        prompt: PromptVersion
    ) -> List[SystemPromptComponent]:
        """
        Extract components from prompt metadata.

        Returns:
            List of SystemPromptComponent objects
        """
        custom = prompt.metadata.custom
        component_dicts = custom.get("components", [])
        return [SystemPromptComponent.from_dict(d) for d in component_dicts]

    def _compose_content(
        self,
        components: List[SystemPromptComponent]
    ) -> str:
        """
        Compose components into final prompt content.

        Components are sorted by order, then wrapped in XML tags if specified.
        """
        sorted_components = sorted(
            [c for c in components if c.enabled],
            key=lambda c: c.order
        )

        parts = []
        for comp in sorted_components:
            content = comp.content

            # Wrap in XML tag if specified
            if comp.xml_tag:
                content = f"<{comp.xml_tag}>\n{content}\n</{comp.xml_tag}>"

            parts.append(content)

        return "\n\n".join(parts)

    def _render_component(
        self,
        component: SystemPromptComponent,
        variables: Dict[str, Any],
    ) -> str:
        """Render a single component with variable substitution."""
        content = component.content

        # Simple variable substitution
        for var, value in variables.items():
            content = content.replace(f"{{{{{var}}}}}", str(value))

        # Add XML tag if present
        if component.xml_tag:
            content = f"<{component.xml_tag}>\n{content}\n</{component.xml_tag}>"

        return content

    def _build_custom_metadata(
        self,
        components: List[SystemPromptComponent]
    ) -> Dict[str, Any]:
        """Build custom metadata dict for storage."""
        return {
            "type": "system_prompt",
            "version": SCHEMA_VERSION,
            "components": [c.to_dict() for c in components],
        }

    def _build_tags(
        self,
        components: List[SystemPromptComponent],
        existing_tags: Optional[List[str]] = None,
    ) -> List[str]:
        """Build tag list including system_prompt and component tags."""
        tags = set(existing_tags or [])
        tags.add(SYSTEM_PROMPT_TAG)

        for comp in components:
            if comp.type == PromptComponentType.CUSTOM:
                tags.add(f"component:custom:{comp.name}")
            else:
                tags.add(f"component:{comp.type.value}")

        # Remove duplicate system_prompt if in existing
        return list(tags)

    def _extract_components_from_agent(
        self,
        agent: "Agent"
    ) -> List[SystemPromptComponent]:
        """
        Extract components from an Agent instance.

        Cross-ref: Agent attributes at agent/agent.py

        Note:
            Only extracts static configuration. Runtime values
            (memories, session state) are not extracted.
        """
        components = []

        # Description (agent/agent.py attribute)
        if hasattr(agent, "description") and agent.description:
            components.append(SystemPromptComponent(
                type=PromptComponentType.DESCRIPTION,
                content=agent.description,
                order=SystemPromptComponent.get_default_order(
                    PromptComponentType.DESCRIPTION
                ),
            ))

        # Role (agent/agent.py attribute)
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

        # Instructions (agent/agent.py attribute)
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

        # Expected output (agent/agent.py attribute)
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

        # Additional context (agent/agent.py attribute)
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

## 6. Integration Points

### 6.1 Integration with Agent

**Read-Only Integration** (no Agent modification required):

```python
# Usage: Extract agent config to versioned prompt

from agno.agent import Agent
from agno.prompt_versioning import SystemPromptEditor

agent = Agent(
    name="support",
    role="Support specialist",
    instructions=["Be helpful", "Be concise"]
)

editor = SystemPromptEditor()
versioned = editor.create_from_agent("support_v1", agent)

# Later: Get composed prompt for use
composed = editor.compose(versioned.id)
```

**Future Integration Point** (Agent modification):

If Agent is later modified to support versioned prompts:

```python
# Proposed Agent attribute (NOT implemented here)
class Agent:
    system_prompt_version_id: Optional[str] = None

    def get_system_message(self, ...):
        if self.system_prompt_version_id:
            # Load from SystemPromptEditor
            ...
```

**Blast Radius**: NONE for current spec (read-only agent access)

### 6.2 Integration with MemoryManager

Memory content is a **runtime concern**, not stored in versioned prompts. However, we provide a placeholder component:

```python
# Example: Memory placeholder
memory_placeholder = SystemPromptComponent(
    type=PromptComponentType.MEMORIES,
    content="{{memories}}",  # Runtime substitution
    order=80,
    xml_tag="memories_from_previous_interactions",
    metadata={"runtime": True}
)

# At runtime, compose with actual memories:
composed = editor.compose(prompt_id, memories=formatted_memories)
```

### 6.3 Integration with Knowledge/RAG

Similar to memories, knowledge is runtime:

```python
knowledge_placeholder = SystemPromptComponent(
    type=PromptComponentType.CUSTOM,
    name="knowledge_instructions",
    content="Use {{knowledge_base}} when answering questions.",
    order=75,
)
```

---

## 7. Blast Radius Analysis

### 7.1 Summary

| Operation | Blast Radius | Affected Systems |
|-----------|--------------|------------------|
| `create()` | LOW | MLflow only (new data) |
| `edit_component()` | LOW | Creates new version (immutable history) |
| `add_component()` | LOW | Creates new version |
| `remove_component()` | LOW | Creates new version |
| `snapshot()` | LOW | Creates immutable snapshot |
| `fork()` | LOW | Creates independent prompt |
| `get()`, `search()` | NONE | Read-only |

### 7.2 Detailed Analysis

#### New Files (LOW RISK)

| File | Risk | Rationale |
|------|------|-----------|
| `system_prompt_models.py` | LOW | New file, no existing code affected |
| `system_prompt_editor.py` | LOW | New file, wraps existing APIs |

#### Modified Files (NONE PROPOSED)

This spec does NOT require modification of:
- `models.py` - Uses existing `custom` field
- `manager.py` - Delegates all operations
- `mlflow_backend.py` - No changes needed
- `agent.py` - Read-only access

#### MLflow Storage Impact

```
BEFORE:
mlruns/
└── prompt_versioning/
    └── existing_prompts...

AFTER:
mlruns/
├── prompt_versioning/          # Unchanged
│   └── existing_prompts...
└── system_prompts/             # NEW experiment prefix
    └── new_system_prompts...
```

**Impact**: Isolated experiment namespace. No effect on existing prompts.

---

## 8. Testing Strategy

### 8.1 Test Organization

```
tests/
├── unit/
│   ├── test_system_prompt_models.py      # Model validation
│   └── test_system_prompt_composition.py # Composition logic
├── integration/
│   ├── test_system_prompt_editor.py      # Editor + Manager
│   └── test_system_prompt_storage.py     # Editor + MLflow
└── e2e/
    ├── test_system_prompt_workflows.py   # Full scenarios
    └── test_system_prompt_agent.py       # Agent integration
```

### 8.2 Unit Tests

**test_system_prompt_models.py**

```python
"""
Unit tests for SystemPromptComponent and PromptComponentType.

Tests model validation, serialization, and defaults.
NO external dependencies (no MLflow, no file system).
"""

import pytest
from agno.prompt_versioning.system_prompt_models import (
    PromptComponentType,
    SystemPromptComponent,
)


class TestPromptComponentType:
    """Tests for PromptComponentType enum."""

    def test_all_types_have_string_values(self):
        """Each type should have a string value."""
        for ct in PromptComponentType:
            assert isinstance(ct.value, str)
            assert len(ct.value) > 0

    def test_types_match_agent_components(self):
        """
        Types should match agent.py components.
        Cross-ref: agent/agent.py:7742-8083
        """
        expected = {
            "description", "role", "instructions", "tool_instructions",
            "expected_output", "additional_info", "additional_context",
            "memories", "session_summary", "cultural_knowledge",
            "session_state", "custom"
        }
        actual = {ct.value for ct in PromptComponentType}
        assert actual == expected


class TestSystemPromptComponent:
    """Tests for SystemPromptComponent model."""

    def test_basic_creation(self):
        """Create component with required fields."""
        comp = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="You are helpful."
        )
        assert comp.type == PromptComponentType.ROLE
        assert comp.content == "You are helpful."
        assert comp.enabled is True

    def test_custom_requires_name(self):
        """CUSTOM type must have a name."""
        with pytest.raises(ValueError, match="must have a name"):
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                content="Custom content"
            )

    def test_custom_with_name(self):
        """CUSTOM type with name is valid."""
        comp = SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="guardrails",
            content="Custom content"
        )
        assert comp.name == "guardrails"

    def test_order_bounds(self):
        """Order must be 0-100."""
        with pytest.raises(ValueError):
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="test",
                order=101
            )

        with pytest.raises(ValueError):
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="test",
                order=-1
            )

    def test_default_order(self):
        """get_default_order returns correct values."""
        assert SystemPromptComponent.get_default_order(
            PromptComponentType.ROLE
        ) == 20
        assert SystemPromptComponent.get_default_order(
            PromptComponentType.INSTRUCTIONS
        ) == 30

    def test_default_xml_tag(self):
        """get_default_xml_tag returns correct tags."""
        assert SystemPromptComponent.get_default_xml_tag(
            PromptComponentType.ROLE
        ) == "your_role"
        assert SystemPromptComponent.get_default_xml_tag(
            PromptComponentType.DESCRIPTION
        ) is None

    def test_serialization_roundtrip(self):
        """to_dict and from_dict are inverses."""
        original = SystemPromptComponent(
            type=PromptComponentType.INSTRUCTIONS,
            content="- Be helpful",
            order=30,
            xml_tag="instructions",
            metadata={"source": "test"}
        )

        serialized = original.to_dict()
        restored = SystemPromptComponent.from_dict(serialized)

        assert restored.type == original.type
        assert restored.content == original.content
        assert restored.order == original.order
        assert restored.xml_tag == original.xml_tag
        assert restored.metadata == original.metadata
```

**test_system_prompt_composition.py**

```python
"""
Unit tests for prompt composition logic.

Tests composition without external dependencies.
"""

import pytest
from agno.prompt_versioning.system_prompt_models import (
    PromptComponentType,
    SystemPromptComponent,
)
# Assuming we expose _compose_content for testing
from agno.prompt_versioning.system_prompt_editor import SystemPromptEditor


class TestComposition:
    """Tests for component composition."""

    @pytest.fixture
    def editor(self, tmp_path):
        """Create editor with temp storage."""
        return SystemPromptEditor(
            tracking_uri=str(tmp_path / "mlruns")
        )

    def test_compose_single_component(self, editor):
        """Single component composes to its content."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are helpful."
            )
        ]
        result = editor._compose_content(components)
        assert result == "You are helpful."

    def test_compose_with_xml_tag(self, editor):
        """XML tags wrap content."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are helpful.",
                xml_tag="your_role"
            )
        ]
        result = editor._compose_content(components)
        expected = "<your_role>\nYou are helpful.\n</your_role>"
        assert result == expected

    def test_compose_respects_order(self, editor):
        """Components are ordered by `order` field."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions",
                order=30
            ),
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role",
                order=20
            ),
        ]
        result = editor._compose_content(components)
        assert result.index("Role") < result.index("Instructions")

    def test_compose_skips_disabled(self, editor):
        """Disabled components are excluded."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role",
                enabled=True
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Hidden",
                enabled=False
            ),
        ]
        result = editor._compose_content(components)
        assert "Role" in result
        assert "Hidden" not in result

    def test_compose_multiple_custom(self, editor):
        """Multiple CUSTOM components allowed."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Guardrail content",
                order=25
            ),
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="personality",
                content="Personality content",
                order=26
            ),
        ]
        result = editor._compose_content(components)
        assert "Guardrail content" in result
        assert "Personality content" in result
```

### 8.3 Integration Tests

**test_system_prompt_editor.py**

```python
"""
Integration tests for SystemPromptEditor with PromptManager.

Uses temporary MLflow storage.
"""

import pytest
import tempfile
from agno.prompt_versioning.system_prompt_editor import SystemPromptEditor
from agno.prompt_versioning.system_prompt_models import (
    PromptComponentType,
    SystemPromptComponent,
)


class TestSystemPromptEditorIntegration:
    """Integration tests for SystemPromptEditor."""

    @pytest.fixture
    def editor(self):
        """Create editor with temp storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SystemPromptEditor(tracking_uri=tmpdir)

    def test_create_and_retrieve(self, editor):
        """Create prompt and retrieve by ID."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are helpful."
            )
        ]

        created = editor.create(
            name="test_prompt",
            components=components,
            author="test"
        )

        retrieved = editor.get(created.id)

        assert retrieved is not None
        assert retrieved.name == "test_prompt"
        assert "system_prompt" in retrieved.metadata.tags

    def test_edit_component_creates_version(self, editor):
        """Editing component creates new version."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Original role"
            )
        ]

        v1 = editor.create("test", components)
        v2 = editor.edit_component(
            v1.id,
            PromptComponentType.ROLE,
            "Updated role"
        )

        assert v2.version == 2
        assert v2.parent_id == v1.id
        assert "Updated role" in v2.content

    def test_add_component(self, editor):
        """Add component to existing prompt."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        v1 = editor.create("test", components)
        v2 = editor.add_component(
            v1.id,
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Be concise"
            )
        )

        retrieved_components = editor.get_components(v2.id)
        types = [c.type for c in retrieved_components]

        assert PromptComponentType.ROLE in types
        assert PromptComponentType.INSTRUCTIONS in types

    def test_remove_component(self, editor):
        """Remove component from prompt."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions"
            )
        ]

        v1 = editor.create("test", components)
        v2 = editor.remove_component(
            v1.id,
            PromptComponentType.INSTRUCTIONS
        )

        retrieved_components = editor.get_components(v2.id)
        types = [c.type for c in retrieved_components]

        assert PromptComponentType.ROLE in types
        assert PromptComponentType.INSTRUCTIONS not in types

    def test_duplicate_type_rejected(self, editor):
        """Cannot add duplicate non-CUSTOM type."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        v1 = editor.create("test", components)

        with pytest.raises(ValueError, match="already exists"):
            editor.add_component(
                v1.id,
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Duplicate role"
                )
            )

    def test_snapshot_preserves_components(self, editor):
        """Snapshot preserves component structure."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        v1 = editor.create("test", components)
        snapshot = editor.snapshot(v1.id, "prod-v1")

        snap_components = editor.get_components(snapshot.id)
        assert len(snap_components) == 1
        assert snap_components[0].type == PromptComponentType.ROLE

    def test_search_by_component_type(self, editor):
        """Search filters by component type."""
        editor.create("with_role", [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ])
        editor.create("with_instructions", [
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions"
            )
        ])

        results = editor.search(
            component_types=[PromptComponentType.ROLE]
        )

        names = [r.name for r in results]
        assert "with_role" in names
        assert "with_instructions" not in names
```

### 8.4 End-to-End Tests

**test_system_prompt_workflows.py**

```python
"""
End-to-end workflow tests.

Tests complete user scenarios with realistic data.
"""

import pytest
import tempfile
from agno.prompt_versioning.system_prompt_editor import SystemPromptEditor
from agno.prompt_versioning.system_prompt_models import (
    PromptComponentType,
    SystemPromptComponent,
)


class TestPromptEngineeringWorkflow:
    """
    Scenario: Prompt engineer iterates on a support agent prompt.
    """

    @pytest.fixture
    def editor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SystemPromptEditor(tracking_uri=tmpdir)

    def test_full_iteration_workflow(self, editor):
        """
        Complete workflow:
        1. Create initial prompt
        2. Edit role for clarity
        3. Add guardrails
        4. Create production snapshot
        5. Fork for A/B test
        6. Compare versions
        """
        # 1. Create initial prompt
        v1 = editor.create(
            name="support_agent",
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="You are a support agent.",
                    xml_tag="your_role"
                ),
                SystemPromptComponent(
                    type=PromptComponentType.INSTRUCTIONS,
                    content="- Help users\n- Be polite",
                    xml_tag="instructions"
                )
            ],
            author="alice@company.com",
            description="Support agent v1"
        )

        assert v1.version == 1
        assert "system_prompt" in v1.metadata.tags

        # 2. Edit role for clarity
        v2 = editor.edit_component(
            v1.id,
            PromptComponentType.ROLE,
            "You are a SENIOR support specialist with billing expertise.",
            author="alice@company.com"
        )

        assert v2.version == 2
        assert "SENIOR" in v2.content

        # 3. Add guardrails
        v3 = editor.add_component(
            v2.id,
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="- Never share internal pricing\n- Escalate billing disputes",
                order=25,
                xml_tag="guardrails"
            ),
            author="bob@company.com"
        )

        assert v3.version == 3
        components = editor.get_components(v3.id)
        custom_components = [c for c in components if c.type == PromptComponentType.CUSTOM]
        assert len(custom_components) == 1
        assert custom_components[0].name == "guardrails"

        # 4. Create production snapshot
        prod = editor.snapshot(
            v3.id,
            "production-2026-01",
            "Approved for production"
        )

        assert prod.snapshot_name == "production-2026-01"

        # 5. Fork for A/B test
        variant_b = editor.fork(
            v3.id,
            "support_agent_variant_b",
            "A/B test: More concise responses",
            "charlie@company.com"
        )

        assert variant_b.name == "support_agent_variant_b"
        assert variant_b.forked_from == v3.id

        # Edit the fork
        variant_b_v2 = editor.edit_component(
            variant_b.id,
            PromptComponentType.INSTRUCTIONS,
            "- Help users\n- Be EXTREMELY concise"
        )

        # 6. Compare versions
        diff = editor.compare(v1.id, v3.id)

        assert len(diff["components_added"]) == 1  # guardrails
        assert "role" in diff["components_changed"]


class TestAgentExtractionWorkflow:
    """
    Scenario: Extract and version an existing agent's prompt.
    """

    @pytest.fixture
    def mock_agent(self):
        """Mock Agent-like object."""
        class MockAgent:
            name = "helper"
            role = "You are a helpful assistant."
            instructions = ["Be concise", "Be accurate"]
            expected_output = None
            additional_context = None
            description = "A helper agent"
        return MockAgent()

    @pytest.fixture
    def editor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SystemPromptEditor(tracking_uri=tmpdir)

    def test_extract_from_agent(self, editor, mock_agent):
        """Extract agent config to versioned prompt."""
        prompt = editor.create_from_agent(
            name="helper_v1",
            agent=mock_agent,
            author="dev@company.com"
        )

        assert prompt.name == "helper_v1"
        assert "agent:helper" in prompt.metadata.tags

        components = editor.get_components(prompt.id)
        types = {c.type for c in components}

        assert PromptComponentType.DESCRIPTION in types
        assert PromptComponentType.ROLE in types
        assert PromptComponentType.INSTRUCTIONS in types

    def test_extracted_prompt_renders(self, editor, mock_agent):
        """Extracted prompt can be composed."""
        prompt = editor.create_from_agent("helper_v1", mock_agent)
        composed = editor.compose(prompt.id)

        assert "helpful assistant" in composed
        assert "Be concise" in composed
```

### 8.5 Test Coverage Requirements

| Category | Minimum Coverage | Focus Areas |
|----------|------------------|-------------|
| Unit | 95% | Model validation, composition logic |
| Integration | 85% | Editor + Manager interaction |
| E2E | 80% | Complete workflows |

---

## 9. Migration & Compatibility

### 9.1 Backward Compatibility

**Guarantee**: Existing prompts created with `PromptManager` remain fully functional.

**Mechanism**:
- SystemPromptEditor uses separate experiment prefix (`system_prompts` vs `prompt_versioning`)
- No modifications to existing models
- Regular prompts lack `system_prompt` tag and custom metadata

### 9.2 Forward Compatibility

**Schema Version**: Store `"version": "1.0"` in custom metadata for future migrations.

```python
# Future migration example
def migrate_v1_to_v2(custom_metadata: dict) -> dict:
    if custom_metadata.get("version") == "1.0":
        # Apply migration
        custom_metadata["version"] = "2.0"
        # ... migrate fields ...
    return custom_metadata
```

### 9.3 Interoperability

SystemPromptEditor prompts can be accessed via regular PromptManager:

```python
# Create with SystemPromptEditor
editor = SystemPromptEditor()
sys_prompt = editor.create("my_agent", components)

# Access via PromptManager (content is pre-composed)
manager = PromptManager()
regular = manager.get(sys_prompt.id)
assert regular.content == editor.compose(sys_prompt.id)
```

---

## 10. Implementation Checklist

### Phase 1: Models (Week 1)

- [ ] Create `system_prompt_models.py`
- [ ] Implement `PromptComponentType` enum
- [ ] Implement `SystemPromptComponent` model
- [ ] Unit tests for models (95% coverage)

### Phase 2: Editor Core (Week 2)

- [ ] Create `system_prompt_editor.py`
- [ ] Implement `create()` method
- [ ] Implement `edit_component()` method
- [ ] Implement `add_component()` / `remove_component()`
- [ ] Integration tests (85% coverage)

### Phase 3: Query & Versioning (Week 3)

- [ ] Implement `get_components()`
- [ ] Implement `search()` with component filters
- [ ] Implement `compare()` with component diff
- [ ] Delegate `snapshot()`, `fork()`

### Phase 4: Agent Integration (Week 4)

- [ ] Implement `create_from_agent()`
- [ ] Implement `compose()` / `preview_component()`
- [ ] E2E tests (80% coverage)
- [ ] Documentation

### Review Checkpoints

- [ ] **Design Review**: Before Phase 1 implementation
- [ ] **Code Review**: After each phase
- [ ] **Integration Review**: After Phase 3
- [ ] **Final Review**: After Phase 4

---

## Appendix A: Cross-Reference Index

| Reference | Location | Description |
|-----------|----------|-------------|
| `Agent.get_system_message()` | `agent/agent.py:7742-8083` | System prompt construction |
| `PromptVersion` | `prompt_versioning/models.py:112-204` | Core version model |
| `PromptMetadata` | `prompt_versioning/models.py:21-46` | Metadata with `custom` field |
| `PromptManager` | `prompt_versioning/manager.py:24-605` | High-level API |
| `MLflowPromptStore` | `prompt_versioning/mlflow_backend.py:58-543` | Storage backend |
| `MemoryManager` | `memory/manager.py` | Memory integration |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Component** | Semantic part of a system prompt (role, instructions, etc.) |
| **Composition** | Assembling components into a complete prompt |
| **Blast Radius** | Scope of potential impact from a change |
| **Lineage** | Version history of a prompt |
| **Snapshot** | Named, immutable version for deployment |

---

*End of Specification*
