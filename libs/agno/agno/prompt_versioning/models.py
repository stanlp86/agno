"""
Pydantic models for prompt versioning system.

This module provides the core data models for:
- PromptTemplate: Template with variable substitution
- PromptMetadata: Metadata for prompt versions
- PromptVersion: Versioned prompt with lineage tracking
- PromptDiff: Diff between prompt versions
- PromptLineage: Full lineage/history of a prompt
- PromptComponentType: Types of system prompt components
- SystemPromptComponent: Individual component of a system prompt

Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 3
"""

import re
import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator, model_validator


class PromptStatus(str, Enum):
    """Status of a prompt version."""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    SNAPSHOT = "snapshot"


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

    @model_validator(mode="after")
    def validate_custom_name(self) -> "SystemPromptComponent":
        """CUSTOM type requires a name."""
        if self.type == PromptComponentType.CUSTOM and not self.name:
            raise ValueError("CUSTOM components must have a name")
        return self

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


class PromptMetadata(BaseModel):
    """Metadata for a prompt version."""

    author: Optional[str] = Field(default=None, description="Author of the prompt")
    description: Optional[str] = Field(default=None, description="Description of the prompt")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    model_compatibility: List[str] = Field(
        default_factory=list,
        description="List of compatible model identifiers"
    )
    use_case: Optional[str] = Field(default=None, description="Intended use case")
    custom: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom metadata fields"
    )

    def add_tag(self, tag: str) -> None:
        """Add a tag if not already present."""
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: str) -> None:
        """Remove a tag if present."""
        if tag in self.tags:
            self.tags.remove(tag)


class PromptTemplate(BaseModel):
    """
    Template with variable substitution support.

    Supports {{variable}} syntax for placeholders.
    """

    content: str = Field(..., description="The prompt template content")
    variables: Set[str] = Field(
        default_factory=set,
        description="Extracted variable names"
    )

    @model_validator(mode="after")
    def extract_variables(self) -> "PromptTemplate":
        """Extract variables from template content."""
        pattern = r"\{\{(\w+)\}\}"
        found_vars = set(re.findall(pattern, self.content))
        object.__setattr__(self, 'variables', found_vars)
        return self

    def render(self, **kwargs: Any) -> str:
        """
        Render the template with provided variables.

        Args:
            **kwargs: Variable values to substitute

        Returns:
            Rendered string with variables replaced

        Raises:
            ValueError: If required variables are missing
        """
        missing = self.variables - set(kwargs.keys())
        if missing:
            raise ValueError(f"Missing required variables: {missing}")

        result = self.content
        for var, value in kwargs.items():
            result = result.replace(f"{{{{{var}}}}}", str(value))
        return result

    def partial_render(self, **kwargs: Any) -> "PromptTemplate":
        """
        Partially render template, leaving unset variables as placeholders.

        Args:
            **kwargs: Variable values to substitute

        Returns:
            New PromptTemplate with some variables filled in
        """
        result = self.content
        for var, value in kwargs.items():
            if var in self.variables:
                result = result.replace(f"{{{{{var}}}}}", str(value))
        return PromptTemplate(content=result)

    def validate_variables(self, required: Set[str]) -> bool:
        """Check if template has all required variables."""
        return required.issubset(self.variables)


class PromptVersion(BaseModel):
    """
    A versioned prompt with full tracking information.

    Supports both traditional prompts and component-based system prompts.
    Component-based prompts have a non-empty `components` list.

    Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 3.3
    """

    id: str = Field(..., description="Unique identifier for this version")
    name: str = Field(..., description="Human-readable name")
    version: int = Field(default=1, ge=1, description="Version number")
    template: PromptTemplate = Field(..., description="The prompt template")
    status: PromptStatus = Field(default=PromptStatus.DRAFT, description="Current status")
    metadata: PromptMetadata = Field(
        default_factory=PromptMetadata,
        description="Associated metadata"
    )

    # Lineage tracking
    parent_id: Optional[str] = Field(
        default=None,
        description="ID of parent version (for edits/forks)"
    )
    forked_from: Optional[str] = Field(
        default=None,
        description="ID of the prompt this was forked from"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )

    # Snapshot info
    snapshot_name: Optional[str] = Field(
        default=None,
        description="Name of snapshot if this is a snapshot"
    )

    # Content hash for integrity
    content_hash: str = Field(default="", description="SHA256 hash of content")

    # Component-based system prompts (NEW)
    components: Optional[List[SystemPromptComponent]] = Field(
        default=None,
        description="Optional list of components for system prompts. "
                    "If present, template.content is the composed result."
    )

    # Change tracking for traceability (NEW)
    change_description: Optional[str] = Field(
        default=None,
        description="Description of changes from parent version"
    )

    @model_validator(mode="after")
    def compute_hash(self) -> "PromptVersion":
        """Compute content hash."""
        content = self.template.content
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
        object.__setattr__(self, 'content_hash', hash_value)
        return self

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate prompt name format."""
        if not re.match(r"^[\w\-\.]+$", v):
            raise ValueError(
                "Name must contain only alphanumeric characters, "
                "underscores, hyphens, and dots"
            )
        return v

    @property
    def content(self) -> str:
        """Get the raw template content."""
        return self.template.content

    @property
    def variables(self) -> Set[str]:
        """Get template variables."""
        return self.template.variables

    def render(self, **kwargs: Any) -> str:
        """Render the prompt template."""
        return self.template.render(**kwargs)

    def is_snapshot(self) -> bool:
        """Check if this version is a snapshot."""
        return self.status == PromptStatus.SNAPSHOT

    def is_fork(self) -> bool:
        """Check if this version is a fork."""
        return self.forked_from is not None

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

    def get_version_string(self) -> str:
        """Get version as string (e.g., 'v1', 'v2')."""
        return f"v{self.version}"

    def get_full_name(self) -> str:
        """Get full name with version (e.g., 'my_prompt:v1')."""
        return f"{self.name}:{self.get_version_string()}"


class PromptDiff(BaseModel):
    """
    Represents differences between two prompt versions.

    Supports both traditional prompts and component-based system prompts.

    Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 3.4
    """

    from_version: str = Field(..., description="Source version ID")
    to_version: str = Field(..., description="Target version ID")
    content_changed: bool = Field(default=False, description="Whether content changed")
    old_content: Optional[str] = Field(default=None, description="Previous content")
    new_content: Optional[str] = Field(default=None, description="New content")
    metadata_changes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Changed metadata fields"
    )
    variables_added: Set[str] = Field(
        default_factory=set,
        description="New variables"
    )
    variables_removed: Set[str] = Field(
        default_factory=set,
        description="Removed variables"
    )

    # Component-level diff fields (NEW)
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

    # Change description from the newer version (NEW)
    change_description: Optional[str] = Field(
        default=None,
        description="Change description from the to_version"
    )

    @classmethod
    def compute(cls, from_prompt: PromptVersion, to_prompt: PromptVersion) -> "PromptDiff":
        """
        Compute diff between two prompt versions.

        Args:
            from_prompt: The older/source prompt version
            to_prompt: The newer/target prompt version

        Returns:
            PromptDiff with all changes
        """
        old_vars = from_prompt.variables
        new_vars = to_prompt.variables

        content_changed = from_prompt.content != to_prompt.content

        # Compute metadata changes
        old_meta = from_prompt.metadata.model_dump()
        new_meta = to_prompt.metadata.model_dump()
        meta_changes = {}
        for key in set(old_meta.keys()) | set(new_meta.keys()):
            if old_meta.get(key) != new_meta.get(key):
                meta_changes[key] = {
                    "old": old_meta.get(key),
                    "new": new_meta.get(key)
                }

        # Compute component-level diff
        components_added: List[Dict[str, Any]] = []
        components_removed: List[Dict[str, Any]] = []
        components_changed: Dict[str, Dict[str, str]] = {}

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
            content_changed=content_changed,
            old_content=from_prompt.content if content_changed else None,
            new_content=to_prompt.content if content_changed else None,
            metadata_changes=meta_changes,
            variables_added=new_vars - old_vars,
            variables_removed=old_vars - new_vars,
            components_added=components_added,
            components_removed=components_removed,
            components_changed=components_changed,
            change_description=to_prompt.change_description,
        )


class PromptLineage(BaseModel):
    """
    Tracks the full lineage/history of a prompt.
    """

    root_id: str = Field(..., description="ID of the original prompt")
    name: str = Field(..., description="Prompt name")
    versions: List[PromptVersion] = Field(
        default_factory=list,
        description="All versions in order"
    )
    forks: List[str] = Field(
        default_factory=list,
        description="IDs of prompts forked from this lineage"
    )
    snapshots: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of snapshot names to version IDs"
    )

    def get_version(self, version: int) -> Optional[PromptVersion]:
        """Get a specific version."""
        for v in self.versions:
            if v.version == version:
                return v
        return None

    def get_latest(self) -> Optional[PromptVersion]:
        """Get the latest version."""
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version)

    def get_snapshot(self, name: str) -> Optional[PromptVersion]:
        """Get a snapshot by name."""
        version_id = self.snapshots.get(name)
        if version_id:
            for v in self.versions:
                if v.id == version_id:
                    return v
        return None

    def add_version(self, prompt: PromptVersion) -> None:
        """Add a new version to the lineage."""
        self.versions.append(prompt)
        if prompt.snapshot_name:
            self.snapshots[prompt.snapshot_name] = prompt.id

    def get_history(self) -> List[Dict[str, Any]]:
        """Get a summary history of all versions."""
        return [
            {
                "version": v.version,
                "id": v.id,
                "status": v.status.value,
                "snapshot_name": v.snapshot_name,
                "created_at": v.created_at.isoformat(),
                "content_hash": v.content_hash,
            }
            for v in sorted(self.versions, key=lambda x: x.version)
        ]
