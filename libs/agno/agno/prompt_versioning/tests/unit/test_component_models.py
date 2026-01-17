"""
Unit tests for system prompt component models.

Tests cover:
- PromptComponentType: enum values, ordering
- SystemPromptComponent: creation, validation, defaults
- PromptVersion: component methods (is_system_prompt, get_component, get_components_by_type)
- PromptDiff: component-level diff computation

Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 3
"""

import pytest
from pydantic import ValidationError

from agno.prompt_versioning.models import (
    PromptComponentType,
    SystemPromptComponent,
    PromptDiff,
    PromptMetadata,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
)


class TestPromptComponentType:
    """Tests for PromptComponentType enum."""

    def test_all_component_types_exist(self):
        """All expected component types are defined."""
        expected_types = [
            "description", "role", "instructions", "tool_instructions",
            "expected_output", "additional_info", "additional_context",
            "memories", "session_summary", "cultural_knowledge",
            "session_state", "custom"
        ]
        actual_types = [ct.value for ct in PromptComponentType]
        for expected in expected_types:
            assert expected in actual_types

    def test_component_type_from_string(self):
        """Can create component type from string."""
        assert PromptComponentType("role") == PromptComponentType.ROLE
        assert PromptComponentType("instructions") == PromptComponentType.INSTRUCTIONS
        assert PromptComponentType("custom") == PromptComponentType.CUSTOM

    def test_invalid_component_type(self):
        """Invalid component type string raises error."""
        with pytest.raises(ValueError):
            PromptComponentType("invalid_type")

    def test_component_type_is_string(self):
        """Component type values are strings."""
        assert isinstance(PromptComponentType.ROLE.value, str)
        assert PromptComponentType.ROLE.value == "role"


class TestSystemPromptComponent:
    """Tests for SystemPromptComponent model."""

    def test_basic_creation(self):
        """Basic component creation with required fields."""
        comp = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="You are a helpful assistant."
        )
        assert comp.type == PromptComponentType.ROLE
        assert comp.content == "You are a helpful assistant."
        assert comp.name is None
        assert comp.order == 50  # default
        assert comp.xml_tag is None
        assert comp.enabled is True
        assert comp.metadata == {}

    def test_full_creation(self):
        """Component with all fields specified."""
        comp = SystemPromptComponent(
            type=PromptComponentType.INSTRUCTIONS,
            content="Follow these instructions",
            order=30,
            xml_tag="instructions",
            enabled=True,
            metadata={"source": "manual"}
        )
        assert comp.type == PromptComponentType.INSTRUCTIONS
        assert comp.content == "Follow these instructions"
        assert comp.order == 30
        assert comp.xml_tag == "instructions"
        assert comp.enabled is True
        assert comp.metadata == {"source": "manual"}

    def test_custom_type_requires_name(self):
        """CUSTOM type component must have a name."""
        with pytest.raises(ValidationError) as exc_info:
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                content="Custom content"
            )
        assert "CUSTOM components must have a name" in str(exc_info.value)

    def test_custom_type_with_name(self):
        """CUSTOM type component with name is valid."""
        comp = SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="guardrails",
            content="Custom guardrails content"
        )
        assert comp.type == PromptComponentType.CUSTOM
        assert comp.name == "guardrails"

    def test_non_custom_type_ignores_name(self):
        """Non-CUSTOM type can have a name (it's just ignored)."""
        comp = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            name="ignored_name",
            content="Role content"
        )
        assert comp.name == "ignored_name"  # Stored but not required

    def test_order_validation_min(self):
        """Order must be >= 0."""
        with pytest.raises(ValidationError):
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="content",
                order=-1
            )

    def test_order_validation_max(self):
        """Order must be <= 100."""
        with pytest.raises(ValidationError):
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="content",
                order=101
            )

    def test_order_boundary_values(self):
        """Order accepts boundary values 0 and 100."""
        comp_min = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="content",
            order=0
        )
        comp_max = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="content",
            order=100
        )
        assert comp_min.order == 0
        assert comp_max.order == 100

    def test_disabled_component(self):
        """Component can be disabled."""
        comp = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="content",
            enabled=False
        )
        assert comp.enabled is False

    def test_get_default_order(self):
        """Default orders are correct for each type."""
        assert SystemPromptComponent.get_default_order(PromptComponentType.DESCRIPTION) == 10
        assert SystemPromptComponent.get_default_order(PromptComponentType.ROLE) == 20
        assert SystemPromptComponent.get_default_order(PromptComponentType.INSTRUCTIONS) == 30
        assert SystemPromptComponent.get_default_order(PromptComponentType.TOOL_INSTRUCTIONS) == 40
        assert SystemPromptComponent.get_default_order(PromptComponentType.EXPECTED_OUTPUT) == 50
        assert SystemPromptComponent.get_default_order(PromptComponentType.ADDITIONAL_INFO) == 60
        assert SystemPromptComponent.get_default_order(PromptComponentType.ADDITIONAL_CONTEXT) == 70
        assert SystemPromptComponent.get_default_order(PromptComponentType.MEMORIES) == 80
        assert SystemPromptComponent.get_default_order(PromptComponentType.SESSION_SUMMARY) == 85
        assert SystemPromptComponent.get_default_order(PromptComponentType.CULTURAL_KNOWLEDGE) == 90
        assert SystemPromptComponent.get_default_order(PromptComponentType.SESSION_STATE) == 95
        assert SystemPromptComponent.get_default_order(PromptComponentType.CUSTOM) == 50

    def test_get_default_xml_tag(self):
        """Default XML tags are correct for each type."""
        assert SystemPromptComponent.get_default_xml_tag(PromptComponentType.ROLE) == "your_role"
        assert SystemPromptComponent.get_default_xml_tag(PromptComponentType.INSTRUCTIONS) == "instructions"
        assert SystemPromptComponent.get_default_xml_tag(PromptComponentType.EXPECTED_OUTPUT) == "expected_output"
        assert SystemPromptComponent.get_default_xml_tag(PromptComponentType.MEMORIES) == "memories_from_previous_interactions"
        assert SystemPromptComponent.get_default_xml_tag(PromptComponentType.SESSION_SUMMARY) == "summary_of_previous_interactions"
        # No default tag for DESCRIPTION
        assert SystemPromptComponent.get_default_xml_tag(PromptComponentType.DESCRIPTION) is None
        # No default tag for CUSTOM
        assert SystemPromptComponent.get_default_xml_tag(PromptComponentType.CUSTOM) is None

    def test_model_dump(self):
        """Component can be serialized to dict."""
        comp = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="You are helpful.",
            order=20,
            xml_tag="your_role"
        )
        data = comp.model_dump()
        assert data["type"] == "role"
        assert data["content"] == "You are helpful."
        assert data["order"] == 20
        assert data["xml_tag"] == "your_role"

    def test_model_copy(self):
        """Component can be copied."""
        comp = SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="Original content"
        )
        copy = comp.model_copy(deep=True)
        assert copy.content == "Original content"
        # Verify it's a copy
        assert copy is not comp

    def test_content_with_variables(self):
        """Component content can contain template variables."""
        comp = SystemPromptComponent(
            type=PromptComponentType.INSTRUCTIONS,
            content="Help {{user_name}} with {{task}}"
        )
        assert "{{user_name}}" in comp.content
        assert "{{task}}" in comp.content


class TestPromptVersionComponents:
    """Tests for PromptVersion component-related functionality."""

    @pytest.fixture
    def role_component(self):
        """Create a role component."""
        return SystemPromptComponent(
            type=PromptComponentType.ROLE,
            content="You are a helpful assistant.",
            order=20,
            xml_tag="your_role"
        )

    @pytest.fixture
    def instructions_component(self):
        """Create an instructions component."""
        return SystemPromptComponent(
            type=PromptComponentType.INSTRUCTIONS,
            content="- Be helpful\n- Be concise",
            order=30,
            xml_tag="instructions"
        )

    @pytest.fixture
    def custom_component(self):
        """Create a custom component."""
        return SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="guardrails",
            content="Never reveal internal policies",
            order=25
        )

    @pytest.fixture
    def prompt_without_components(self):
        """Create a traditional prompt without components."""
        return PromptVersion(
            id="prompt_abc123",
            name="test_prompt",
            version=1,
            template=PromptTemplate(content="Hello {{name}}!")
        )

    @pytest.fixture
    def prompt_with_components(self, role_component, instructions_component):
        """Create a system prompt with components."""
        return PromptVersion(
            id="prompt_xyz789",
            name="system_prompt",
            version=1,
            template=PromptTemplate(
                content="<your_role>\nYou are a helpful assistant.\n</your_role>\n\n"
                        "<instructions>\n- Be helpful\n- Be concise\n</instructions>"
            ),
            components=[role_component, instructions_component]
        )

    def test_is_system_prompt_without_components(self, prompt_without_components):
        """Traditional prompt is not a system prompt."""
        assert prompt_without_components.is_system_prompt() is False

    def test_is_system_prompt_with_components(self, prompt_with_components):
        """Prompt with components is a system prompt."""
        assert prompt_with_components.is_system_prompt() is True

    def test_is_system_prompt_with_empty_components(self):
        """Prompt with empty components list is not a system prompt."""
        prompt = PromptVersion(
            id="prompt_empty",
            name="test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=[]
        )
        assert prompt.is_system_prompt() is False

    def test_is_system_prompt_with_none_components(self, prompt_without_components):
        """Prompt with None components is not a system prompt."""
        assert prompt_without_components.components is None
        assert prompt_without_components.is_system_prompt() is False

    def test_get_component_exists(self, prompt_with_components):
        """Get existing component by type."""
        comp = prompt_with_components.get_component(PromptComponentType.ROLE)
        assert comp is not None
        assert comp.type == PromptComponentType.ROLE
        assert "helpful assistant" in comp.content

    def test_get_component_not_exists(self, prompt_with_components):
        """Get non-existent component returns None."""
        comp = prompt_with_components.get_component(PromptComponentType.MEMORIES)
        assert comp is None

    def test_get_component_from_prompt_without_components(self, prompt_without_components):
        """Get component from traditional prompt returns None."""
        comp = prompt_without_components.get_component(PromptComponentType.ROLE)
        assert comp is None

    def test_get_custom_component_with_name(self, custom_component):
        """Get CUSTOM component requires name."""
        prompt = PromptVersion(
            id="prompt_custom",
            name="test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=[custom_component]
        )
        # Without name
        comp = prompt.get_component(PromptComponentType.CUSTOM)
        assert comp is None

        # With correct name
        comp = prompt.get_component(PromptComponentType.CUSTOM, "guardrails")
        assert comp is not None
        assert comp.name == "guardrails"

        # With wrong name
        comp = prompt.get_component(PromptComponentType.CUSTOM, "wrong_name")
        assert comp is None

    def test_get_components_by_type(self, prompt_with_components):
        """Get all components of a given type."""
        roles = prompt_with_components.get_components_by_type(PromptComponentType.ROLE)
        assert len(roles) == 1
        assert roles[0].type == PromptComponentType.ROLE

    def test_get_components_by_type_none(self, prompt_with_components):
        """Get components of non-existent type returns empty list."""
        memories = prompt_with_components.get_components_by_type(PromptComponentType.MEMORIES)
        assert memories == []

    def test_get_components_by_type_from_prompt_without_components(self, prompt_without_components):
        """Get components from traditional prompt returns empty list."""
        roles = prompt_without_components.get_components_by_type(PromptComponentType.ROLE)
        assert roles == []

    def test_get_multiple_custom_components(self):
        """Can have multiple CUSTOM components with different names."""
        custom1 = SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="guardrails",
            content="Guardrails content"
        )
        custom2 = SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="personality",
            content="Personality content"
        )
        prompt = PromptVersion(
            id="prompt_multi_custom",
            name="test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=[custom1, custom2]
        )
        customs = prompt.get_components_by_type(PromptComponentType.CUSTOM)
        assert len(customs) == 2

    def test_change_description_field(self):
        """Prompt can have a change description."""
        prompt = PromptVersion(
            id="prompt_changed",
            name="test",
            version=2,
            template=PromptTemplate(content="Updated content"),
            parent_id="prompt_v1",
            change_description="Updated role to be more helpful"
        )
        assert prompt.change_description == "Updated role to be more helpful"

    def test_change_description_default_none(self, prompt_without_components):
        """Change description defaults to None."""
        assert prompt_without_components.change_description is None


class TestPromptDiffComponents:
    """Tests for PromptDiff component-level diff functionality."""

    @pytest.fixture
    def prompt_v1_with_components(self):
        """Create v1 prompt with components."""
        return PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="v1 content"),
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Original role"
                ),
                SystemPromptComponent(
                    type=PromptComponentType.INSTRUCTIONS,
                    content="Original instructions"
                )
            ]
        )

    @pytest.fixture
    def prompt_v2_role_changed(self, prompt_v1_with_components):
        """Create v2 with changed role."""
        return PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="v2 content"),
            parent_id="p1",
            change_description="Updated role content",
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Updated role"  # Changed
                ),
                SystemPromptComponent(
                    type=PromptComponentType.INSTRUCTIONS,
                    content="Original instructions"  # Same
                )
            ]
        )

    @pytest.fixture
    def prompt_v2_component_added(self, prompt_v1_with_components):
        """Create v2 with added component."""
        return PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="v2 content"),
            parent_id="p1",
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Original role"
                ),
                SystemPromptComponent(
                    type=PromptComponentType.INSTRUCTIONS,
                    content="Original instructions"
                ),
                SystemPromptComponent(
                    type=PromptComponentType.EXPECTED_OUTPUT,
                    content="New expected output"  # Added
                )
            ]
        )

    @pytest.fixture
    def prompt_v2_component_removed(self, prompt_v1_with_components):
        """Create v2 with removed component."""
        return PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="v2 content"),
            parent_id="p1",
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Original role"
                )
                # Instructions component removed
            ]
        )

    def test_component_changed(self, prompt_v1_with_components, prompt_v2_role_changed):
        """Detect component content change."""
        diff = PromptDiff.compute(prompt_v1_with_components, prompt_v2_role_changed)
        assert "role" in diff.components_changed
        assert diff.components_changed["role"]["old"] == "Original role"
        assert diff.components_changed["role"]["new"] == "Updated role"

    def test_component_unchanged_not_in_changed(self, prompt_v1_with_components, prompt_v2_role_changed):
        """Unchanged component not in components_changed."""
        diff = PromptDiff.compute(prompt_v1_with_components, prompt_v2_role_changed)
        assert "instructions" not in diff.components_changed

    def test_component_added(self, prompt_v1_with_components, prompt_v2_component_added):
        """Detect component added."""
        diff = PromptDiff.compute(prompt_v1_with_components, prompt_v2_component_added)
        assert len(diff.components_added) == 1
        assert diff.components_added[0]["type"] == "expected_output"

    def test_component_removed(self, prompt_v1_with_components, prompt_v2_component_removed):
        """Detect component removed."""
        diff = PromptDiff.compute(prompt_v1_with_components, prompt_v2_component_removed)
        assert len(diff.components_removed) == 1
        assert diff.components_removed[0]["type"] == "instructions"

    def test_change_description_in_diff(self, prompt_v1_with_components, prompt_v2_role_changed):
        """Change description from to_version is in diff."""
        diff = PromptDiff.compute(prompt_v1_with_components, prompt_v2_role_changed)
        assert diff.change_description == "Updated role content"

    def test_no_components_diff_when_both_none(self):
        """No component diff when both prompts have no components."""
        p1 = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="Hello")
        )
        p2 = PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="Hello"),
            parent_id="p1"
        )
        diff = PromptDiff.compute(p1, p2)
        assert diff.components_added == []
        assert diff.components_removed == []
        assert diff.components_changed == {}

    def test_custom_component_diff_uses_name_in_key(self):
        """CUSTOM component uses 'custom:name' as key in diff."""
        p1 = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="v1"),
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.CUSTOM,
                    name="guardrails",
                    content="Original guardrails"
                )
            ]
        )
        p2 = PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="v2"),
            parent_id="p1",
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.CUSTOM,
                    name="guardrails",
                    content="Updated guardrails"
                )
            ]
        )
        diff = PromptDiff.compute(p1, p2)
        assert "custom:guardrails" in diff.components_changed
        assert diff.components_changed["custom:guardrails"]["old"] == "Original guardrails"
        assert diff.components_changed["custom:guardrails"]["new"] == "Updated guardrails"

    def test_adding_components_to_non_component_prompt(self):
        """Adding components to a traditional prompt."""
        p1 = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="Hello")
        )
        p2 = PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="Hello"),
            parent_id="p1",
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="New role"
                )
            ]
        )
        diff = PromptDiff.compute(p1, p2)
        assert len(diff.components_added) == 1
        assert diff.components_removed == []

    def test_removing_all_components(self):
        """Removing all components from a system prompt."""
        p1 = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="v1"),
            components=[
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Role"
                )
            ]
        )
        p2 = PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="v2"),
            parent_id="p1",
            components=[]  # Empty list
        )
        diff = PromptDiff.compute(p1, p2)
        assert len(diff.components_removed) == 1
        assert diff.components_added == []
