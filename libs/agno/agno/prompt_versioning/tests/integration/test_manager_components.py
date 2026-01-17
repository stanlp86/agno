"""
Integration tests for PromptManager component methods.

Tests cover:
- create_system_prompt
- edit_component
- add_component
- remove_component
- reorder_components
- get_components
- search_system_prompts
- Component validation and composition

Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 4.1
"""

import pytest

from agno.prompt_versioning.models import (
    PromptComponentType,
    PromptStatus,
    SystemPromptComponent,
)
from agno.prompt_versioning.manager import PromptManager


class TestCreateSystemPrompt:
    """Tests for create_system_prompt method."""

    def test_create_with_single_component(self, manager):
        """Create system prompt with one component."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are a helpful assistant."
            )
        ]

        prompt = manager.create_system_prompt("single_comp", components)

        assert prompt.is_system_prompt()
        assert len(prompt.components) == 1
        assert prompt.components[0].type == PromptComponentType.ROLE

    def test_create_with_multiple_components(self, manager):
        """Create system prompt with multiple components."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are a helpful assistant.",
                order=20,
                xml_tag="your_role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="- Be helpful\n- Be concise",
                order=30,
                xml_tag="instructions"
            ),
        ]

        prompt = manager.create_system_prompt(
            "multi_comp",
            components,
            description="Multi-component prompt",
            author="test_author"
        )

        assert prompt.is_system_prompt()
        assert len(prompt.components) == 2
        assert prompt.metadata.description == "Multi-component prompt"
        assert prompt.metadata.author == "test_author"

    def test_create_composes_content(self, manager):
        """Created prompt has composed content."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are helpful.",
                order=10,
                xml_tag="your_role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Be concise.",
                order=20,
                xml_tag="instructions"
            ),
        ]

        prompt = manager.create_system_prompt("composed", components)

        # Content should have XML tags
        assert "<your_role>" in prompt.content
        assert "You are helpful." in prompt.content
        assert "<instructions>" in prompt.content
        assert "Be concise." in prompt.content

    def test_create_adds_system_prompt_tag(self, manager):
        """Created prompt has system_prompt tag."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role content"
            )
        ]

        prompt = manager.create_system_prompt("tagged", components)

        assert "system_prompt" in prompt.metadata.tags

    def test_create_adds_component_type_tags(self, manager):
        """Created prompt has component type tags."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions"
            ),
        ]

        prompt = manager.create_system_prompt("type_tagged", components)

        assert "component_role" in prompt.metadata.tags
        assert "component_instructions" in prompt.metadata.tags

    def test_create_with_custom_component(self, manager):
        """Create with CUSTOM component includes name in tag."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Guardrails content"
            )
        ]

        prompt = manager.create_system_prompt("custom_comp", components)

        assert "component_custom_guardrails" in prompt.metadata.tags

    def test_create_rejects_duplicate_types(self, manager):
        """Creating with duplicate non-CUSTOM types fails."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="First role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Second role"  # Duplicate
            ),
        ]

        with pytest.raises(ValueError) as exc_info:
            manager.create_system_prompt("duplicate", components)

        assert "Duplicate component" in str(exc_info.value)

    def test_create_allows_multiple_custom(self, manager):
        """Creating with multiple CUSTOM components is allowed."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Guardrails"
            ),
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="personality",
                content="Personality"
            ),
        ]

        prompt = manager.create_system_prompt("multi_custom", components)

        assert len(prompt.components) == 2

    def test_create_with_model_compatibility(self, manager):
        """Create with model compatibility metadata."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        prompt = manager.create_system_prompt(
            "model_compat",
            components,
            model_compatibility=["gpt-4", "claude-3"]
        )

        assert "gpt-4" in prompt.metadata.model_compatibility
        assert "claude-3" in prompt.metadata.model_compatibility


class TestEditComponent:
    """Tests for edit_component method."""

    @pytest.fixture
    def system_prompt(self, manager):
        """Create a system prompt for testing."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Original role",
                order=20
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Original instructions",
                order=30
            ),
        ]
        return manager.create_system_prompt("edit_test", components)

    def test_edit_component_creates_new_version(self, manager, system_prompt):
        """Editing creates a new version."""
        updated = manager.edit_component(
            system_prompt.id,
            PromptComponentType.ROLE,
            "Updated role content"
        )

        assert updated.version == system_prompt.version + 1
        assert updated.parent_id == system_prompt.id

    def test_edit_component_updates_content(self, manager, system_prompt):
        """Edited component has new content."""
        new_content = "Updated role content"
        updated = manager.edit_component(
            system_prompt.id,
            PromptComponentType.ROLE,
            new_content
        )

        role = updated.get_component(PromptComponentType.ROLE)
        assert role.content == new_content

    def test_edit_component_preserves_other_components(self, manager, system_prompt):
        """Other components are unchanged."""
        updated = manager.edit_component(
            system_prompt.id,
            PromptComponentType.ROLE,
            "New role"
        )

        inst = updated.get_component(PromptComponentType.INSTRUCTIONS)
        assert inst.content == "Original instructions"

    def test_edit_component_with_change_description(self, manager, system_prompt):
        """Change description is stored."""
        updated = manager.edit_component(
            system_prompt.id,
            PromptComponentType.ROLE,
            "New role",
            change_description="Updated role for premium support"
        )

        assert updated.change_description == "Updated role for premium support"

    def test_edit_custom_component_requires_name(self, manager):
        """Editing CUSTOM component requires name."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Original"
            )
        ]
        prompt = manager.create_system_prompt("custom_edit", components)

        # Without name - should fail
        with pytest.raises(ValueError):
            manager.edit_component(
                prompt.id,
                PromptComponentType.CUSTOM,
                "New content"
            )

        # With name - should succeed
        updated = manager.edit_component(
            prompt.id,
            PromptComponentType.CUSTOM,
            "Updated guardrails",
            component_name="guardrails"
        )

        custom = updated.get_component(PromptComponentType.CUSTOM, "guardrails")
        assert custom.content == "Updated guardrails"

    def test_edit_nonexistent_component_raises(self, manager, system_prompt):
        """Editing non-existent component raises error."""
        with pytest.raises(ValueError) as exc_info:
            manager.edit_component(
                system_prompt.id,
                PromptComponentType.MEMORIES,  # Not in prompt
                "New content"
            )

        assert "Component not found" in str(exc_info.value)

    def test_edit_traditional_prompt_raises(self, manager):
        """Editing component on traditional prompt raises error."""
        traditional = manager.create("traditional", "Hello {{name}}")

        with pytest.raises(ValueError) as exc_info:
            manager.edit_component(
                traditional.id,
                PromptComponentType.ROLE,
                "New role"
            )

        assert "Not a system prompt" in str(exc_info.value)


class TestAddComponent:
    """Tests for add_component method."""

    @pytest.fixture
    def system_prompt(self, manager):
        """Create a system prompt with one component."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role content"
            )
        ]
        return manager.create_system_prompt("add_test", components)

    def test_add_component_creates_new_version(self, manager, system_prompt):
        """Adding component creates new version."""
        new_comp = SystemPromptComponent(
            type=PromptComponentType.INSTRUCTIONS,
            content="New instructions"
        )

        updated = manager.add_component(system_prompt.id, new_comp)

        assert updated.version == system_prompt.version + 1

    def test_add_component_includes_new_component(self, manager, system_prompt):
        """New component is included in prompt."""
        new_comp = SystemPromptComponent(
            type=PromptComponentType.INSTRUCTIONS,
            content="New instructions"
        )

        updated = manager.add_component(system_prompt.id, new_comp)

        assert len(updated.components) == 2
        inst = updated.get_component(PromptComponentType.INSTRUCTIONS)
        assert inst is not None
        assert inst.content == "New instructions"

    def test_add_duplicate_type_raises(self, manager, system_prompt):
        """Adding duplicate non-CUSTOM type raises error."""
        duplicate = SystemPromptComponent(
            type=PromptComponentType.ROLE,  # Already exists
            content="Duplicate role"
        )

        with pytest.raises(ValueError) as exc_info:
            manager.add_component(system_prompt.id, duplicate)

        assert "already exists" in str(exc_info.value)

    def test_add_multiple_custom_allowed(self, manager, system_prompt):
        """Adding multiple CUSTOM components is allowed."""
        custom1 = SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="guardrails",
            content="Guardrails"
        )
        custom2 = SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="personality",
            content="Personality"
        )

        v2 = manager.add_component(system_prompt.id, custom1)
        v3 = manager.add_component(v2.id, custom2)

        customs = v3.get_components_by_type(PromptComponentType.CUSTOM)
        assert len(customs) == 2


class TestRemoveComponent:
    """Tests for remove_component method."""

    @pytest.fixture
    def system_prompt(self, manager):
        """Create a system prompt with multiple components."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions"
            ),
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Guardrails"
            ),
        ]
        return manager.create_system_prompt("remove_test", components)

    def test_remove_component_creates_new_version(self, manager, system_prompt):
        """Removing creates new version."""
        updated = manager.remove_component(
            system_prompt.id,
            PromptComponentType.INSTRUCTIONS
        )

        assert updated.version == system_prompt.version + 1

    def test_remove_component_excludes_component(self, manager, system_prompt):
        """Removed component is not in new version."""
        updated = manager.remove_component(
            system_prompt.id,
            PromptComponentType.INSTRUCTIONS
        )

        assert len(updated.components) == 2
        inst = updated.get_component(PromptComponentType.INSTRUCTIONS)
        assert inst is None

    def test_remove_custom_requires_name(self, manager, system_prompt):
        """Removing CUSTOM requires name."""
        # Without name - doesn't find it
        with pytest.raises(ValueError):
            manager.remove_component(
                system_prompt.id,
                PromptComponentType.CUSTOM
            )

        # With name - succeeds
        updated = manager.remove_component(
            system_prompt.id,
            PromptComponentType.CUSTOM,
            component_name="guardrails"
        )

        custom = updated.get_component(PromptComponentType.CUSTOM, "guardrails")
        assert custom is None

    def test_remove_nonexistent_raises(self, manager, system_prompt):
        """Removing non-existent component raises error."""
        with pytest.raises(ValueError) as exc_info:
            manager.remove_component(
                system_prompt.id,
                PromptComponentType.MEMORIES  # Not in prompt
            )

        assert "Component not found" in str(exc_info.value)


class TestReorderComponents:
    """Tests for reorder_components method."""

    @pytest.fixture
    def system_prompt(self, manager):
        """Create a system prompt with ordered components."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role",
                order=20
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions",
                order=30
            ),
        ]
        return manager.create_system_prompt("reorder_test", components)

    def test_reorder_creates_new_version(self, manager, system_prompt):
        """Reordering creates new version."""
        updated = manager.reorder_components(
            system_prompt.id,
            {PromptComponentType.INSTRUCTIONS: 15}
        )

        assert updated.version == system_prompt.version + 1

    def test_reorder_changes_component_order(self, manager, system_prompt):
        """Reordering changes component order values."""
        updated = manager.reorder_components(
            system_prompt.id,
            {PromptComponentType.INSTRUCTIONS: 15}  # Before role now
        )

        components = manager.get_components(updated.id)
        # Instructions should come first now
        assert components[0].type == PromptComponentType.INSTRUCTIONS
        assert components[0].order == 15
        assert components[1].type == PromptComponentType.ROLE
        assert components[1].order == 20

    def test_reorder_affects_composed_content(self, manager, system_prompt):
        """Reordering changes composed content order."""
        # Original order: role (20), instructions (30)
        original = manager.get(system_prompt.id)
        role_pos_original = original.content.find("Role")
        inst_pos_original = original.content.find("Instructions")
        assert role_pos_original < inst_pos_original

        # Reorder: instructions (15), role (20)
        updated = manager.reorder_components(
            system_prompt.id,
            {PromptComponentType.INSTRUCTIONS: 15}
        )

        role_pos_new = updated.content.find("Role")
        inst_pos_new = updated.content.find("Instructions")
        assert inst_pos_new < role_pos_new


class TestGetComponents:
    """Tests for get_components method."""

    def test_get_components_returns_sorted(self, manager):
        """Components are returned sorted by order."""
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
        prompt = manager.create_system_prompt("sorted_test", components)

        result = manager.get_components(prompt.id)

        assert result[0].type == PromptComponentType.ROLE
        assert result[1].type == PromptComponentType.INSTRUCTIONS

    def test_get_components_nonexistent_raises(self, manager):
        """Getting components from non-existent prompt raises."""
        with pytest.raises(ValueError):
            manager.get_components("nonexistent_id")

    def test_get_components_traditional_raises(self, manager):
        """Getting components from traditional prompt raises."""
        traditional = manager.create("traditional", "Hello")

        with pytest.raises(ValueError) as exc_info:
            manager.get_components(traditional.id)

        assert "Not a system prompt" in str(exc_info.value)


class TestSearchSystemPrompts:
    """Tests for search_system_prompts method."""

    @pytest.fixture
    def sample_prompts(self, manager):
        """Create sample system prompts for searching."""
        # Create with role component
        manager.create_system_prompt(
            "support_agent",
            [
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Support role"
                )
            ],
            author="alice",
            tags=["support"],
            model_compatibility=["gpt-4"]
        )

        # Create with role and instructions
        manager.create_system_prompt(
            "sales_agent",
            [
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Sales role"
                ),
                SystemPromptComponent(
                    type=PromptComponentType.INSTRUCTIONS,
                    content="Sales instructions"
                ),
            ],
            author="bob",
            tags=["sales"],
            model_compatibility=["claude-3"]
        )

        # Create traditional prompt (not a system prompt)
        manager.create(
            "traditional_prompt",
            "Hello {{name}}",
            author="alice"
        )

    def test_search_finds_system_prompts(self, manager, sample_prompts):
        """Search returns only system prompts."""
        results = manager.search_system_prompts()

        assert len(results) >= 2
        for r in results:
            assert r.is_system_prompt()

    def test_search_by_component_type(self, manager, sample_prompts):
        """Search by component type."""
        results = manager.search_system_prompts(
            component_types=[PromptComponentType.INSTRUCTIONS]
        )

        assert any(r.name == "sales_agent" for r in results)
        # support_agent doesn't have instructions
        assert not any(r.name == "support_agent" for r in results)

    def test_search_by_author(self, manager, sample_prompts):
        """Search by author."""
        results = manager.search_system_prompts(author="alice")

        assert any(r.name == "support_agent" for r in results)
        assert not any(r.name == "sales_agent" for r in results)

    def test_search_by_tags(self, manager, sample_prompts):
        """Search by additional tags."""
        results = manager.search_system_prompts(tags=["support"])

        assert any(r.name == "support_agent" for r in results)

    def test_search_by_model_compatibility(self, manager, sample_prompts):
        """Search by model compatibility."""
        results = manager.search_system_prompts(
            model_compatibility=["gpt-4"]
        )

        assert any(r.name == "support_agent" for r in results)
        assert not any(r.name == "sales_agent" for r in results)


class TestComponentComposition:
    """Tests for component composition logic."""

    def test_disabled_components_excluded(self, manager):
        """Disabled components are not in composed content."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Enabled role",
                enabled=True
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Disabled instructions",
                enabled=False
            ),
        ]

        prompt = manager.create_system_prompt("disabled_test", components)

        assert "Enabled role" in prompt.content
        assert "Disabled instructions" not in prompt.content

    def test_xml_tags_included_in_composition(self, manager):
        """XML tags are included in composed content."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role content",
                xml_tag="your_role"
            )
        ]

        prompt = manager.create_system_prompt("xml_test", components)

        assert "<your_role>" in prompt.content
        assert "Role content" in prompt.content
        assert "</your_role>" in prompt.content

    def test_components_ordered_by_order_value(self, manager):
        """Components are ordered by order value in composition."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Second",
                order=20
            ),
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="First",
                order=10
            ),
        ]

        prompt = manager.create_system_prompt("order_test", components)

        first_pos = prompt.content.find("First")
        second_pos = prompt.content.find("Second")
        assert first_pos < second_pos
