"""
End-to-end tests for SystemPromptEditor.

Tests cover:
- Full workflow from creation to deployment
- Agent extraction and application
- Preview and export functionality
- Component iteration workflows

Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 13
"""

import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional

import pytest

from agno.prompt_versioning.models import (
    PromptComponentType,
    SystemPromptComponent,
)
from agno.prompt_versioning.system_prompt_editor import SystemPromptEditor


# Mock Agent class for testing without importing full agno
@dataclass
class MockAgent:
    """Mock Agent for testing."""
    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    instructions: Optional[List[str]] = None
    expected_output: Optional[str] = None
    additional_context: Optional[str] = None
    system_message: Optional[str] = None


@pytest.fixture(scope="function")
def editor():
    """Create SystemPromptEditor with temp directory."""
    with tempfile.TemporaryDirectory(prefix="editor_test_") as tmpdir:
        tracking_uri = os.path.join(tmpdir, "mlruns")
        yield SystemPromptEditor(tracking_uri=tracking_uri)


class TestBasicWorkflow:
    """Tests for basic create-edit-snapshot workflow."""

    def test_create_edit_snapshot_workflow(self, editor):
        """Full workflow: create, edit, snapshot."""
        # Create initial prompt
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

        v1 = editor.create(
            name="support_agent",
            components=components,
            description="Support agent prompt",
            author="test_user"
        )

        assert v1.version == 1
        assert v1.is_system_prompt()
        assert len(v1.components) == 2

        # Edit role component
        v2 = editor.edit_component(
            v1.id,
            PromptComponentType.ROLE,
            "You are an expert support specialist with deep product knowledge.",
            change_description="Enhanced role description"
        )

        assert v2.version == 2
        assert v2.parent_id == v1.id
        assert v2.change_description == "Enhanced role description"

        # Verify role updated, instructions unchanged
        role = v2.get_component(PromptComponentType.ROLE)
        inst = v2.get_component(PromptComponentType.INSTRUCTIONS)
        assert "expert support specialist" in role.content
        assert inst.content == "- Be helpful\n- Be concise"

        # Create production snapshot
        snapshot = editor.snapshot(
            v2.id,
            "production-v1",
            description="First production release"
        )

        assert snapshot.snapshot_name == "production-v1"

    def test_component_iteration_workflow(self, editor):
        """Iterate on components: add, edit, remove."""
        # Start with role only
        v1 = editor.create(
            "iteration_test",
            [
                SystemPromptComponent(
                    type=PromptComponentType.ROLE,
                    content="Role content"
                )
            ]
        )

        # Add instructions
        v2 = editor.add_component(
            v1.id,
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions content"
            ),
            change_description="Added instructions"
        )

        assert len(v2.components) == 2

        # Add guardrails (custom component)
        v3 = editor.add_component(
            v2.id,
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Guardrails content"
            ),
            change_description="Added safety guardrails"
        )

        assert len(v3.components) == 3

        # Edit guardrails
        v4 = editor.edit_component(
            v3.id,
            PromptComponentType.CUSTOM,
            "Updated guardrails content",
            component_name="guardrails"
        )

        guardrails = v4.get_component(PromptComponentType.CUSTOM, "guardrails")
        assert guardrails.content == "Updated guardrails content"

        # Remove instructions
        v5 = editor.remove_component(
            v4.id,
            PromptComponentType.INSTRUCTIONS
        )

        assert len(v5.components) == 2
        assert v5.get_component(PromptComponentType.INSTRUCTIONS) is None


class TestAgentIntegration:
    """Tests for Agent extraction and application."""

    def test_create_from_agent(self, editor):
        """Extract components from mock Agent."""
        agent = MockAgent(
            name="support_agent",
            description="A customer support agent",
            role="You are a helpful support specialist",
            instructions=["Be helpful", "Be concise", "Be accurate"],
            expected_output="A helpful response to the customer query"
        )

        prompt = editor.create_from_agent(
            "extracted_prompt",
            agent,
            author="test_user"
        )

        assert prompt.is_system_prompt()

        # Check components extracted
        desc = prompt.get_component(PromptComponentType.DESCRIPTION)
        assert desc is not None
        assert desc.content == "A customer support agent"

        role = prompt.get_component(PromptComponentType.ROLE)
        assert role is not None
        assert "helpful support specialist" in role.content

        inst = prompt.get_component(PromptComponentType.INSTRUCTIONS)
        assert inst is not None
        assert "- Be helpful" in inst.content

        output = prompt.get_component(PromptComponentType.EXPECTED_OUTPUT)
        assert output is not None

    def test_apply_to_agent_individual_attributes(self, editor):
        """Apply prompt to agent by setting individual attributes."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are an expert analyst."
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="- Analyze data\n- Provide insights"
            ),
        ]

        prompt = editor.create("apply_test", components)

        agent = MockAgent()
        editor.apply_to_agent(prompt.id, agent, override_system_message=False)

        assert agent.role == "You are an expert analyst."
        assert agent.instructions == ["Analyze data", "Provide insights"]

    def test_apply_to_agent_override_system_message(self, editor):
        """Apply prompt by setting system_message directly."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role content",
                xml_tag="your_role"
            ),
        ]

        prompt = editor.create("override_test", components)

        agent = MockAgent()
        editor.apply_to_agent(prompt.id, agent, override_system_message=True)

        assert agent.system_message is not None
        assert "<your_role>" in agent.system_message
        assert "Role content" in agent.system_message

    def test_get_agent_compatible_versions(self, editor):
        """Get prompts compatible with specific model."""
        # Create prompts with different model compatibility
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        editor.create(
            "gpt4_prompt",
            components,
            model_compatibility=["gpt-4"]
        )

        editor.create(
            "claude_prompt",
            components,
            model_compatibility=["claude-3-opus"]
        )

        editor.create(
            "both_prompt",
            components,
            model_compatibility=["gpt-4", "claude-3-opus"]
        )

        # Search for gpt-4 compatible
        gpt4_results = editor.get_agent_compatible_versions("gpt-4")

        names = [r.name for r in gpt4_results]
        assert "gpt4_prompt" in names
        assert "both_prompt" in names
        assert "claude_prompt" not in names


class TestPreviewAndExport:
    """Tests for preview and export functionality."""

    def test_preview_component(self, editor):
        """Preview single component."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are helpful.",
                xml_tag="your_role"
            ),
        ]

        prompt = editor.create("preview_test", components)

        # With XML tag
        with_tag = editor.preview_component(
            prompt.id,
            PromptComponentType.ROLE,
            include_xml_tag=True
        )
        assert "<your_role>" in with_tag
        assert "You are helpful." in with_tag
        assert "</your_role>" in with_tag

        # Without XML tag
        without_tag = editor.preview_component(
            prompt.id,
            PromptComponentType.ROLE,
            include_xml_tag=False
        )
        assert "<your_role>" not in without_tag
        assert "You are helpful." in without_tag

    def test_preview_components_dict(self, editor):
        """Preview all components as dictionary."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role content",
                order=20
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions content",
                order=30
            ),
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Guardrails content",
                order=25
            ),
        ]

        prompt = editor.create("preview_dict_test", components)

        previews = editor.preview_components(prompt.id)

        assert "role" in previews
        assert "instructions" in previews
        assert "custom:guardrails" in previews
        assert "Role content" in previews["role"]

    def test_preview_components_filter(self, editor):
        """Preview only specific component types."""
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

        prompt = editor.create("filter_test", components)

        previews = editor.preview_components(
            prompt.id,
            include_only=[PromptComponentType.ROLE]
        )

        assert "role" in previews
        assert "instructions" not in previews

    def test_export_as_markdown(self, editor):
        """Export prompt as markdown."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="You are a helpful assistant.",
                order=20,
                xml_tag="your_role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Be concise.",
                order=30,
                xml_tag="instructions"
            ),
        ]

        v1 = editor.create(
            "export_test",
            components,
            description="Test prompt",
            author="test_author"
        )

        v2 = editor.edit_component(
            v1.id,
            PromptComponentType.ROLE,
            "Updated role",
            change_description="Updated role content"
        )

        md = editor.export_as_markdown(
            v2.id,
            include_metadata=True,
            include_history=True
        )

        # Check sections present
        assert "# System Prompt: export_test" in md
        assert "## Metadata" in md
        assert "## Latest Changes" in md
        assert "## Components" in md
        assert "## Version History" in md

        # Check content
        assert "test_author" in md
        assert "Updated role content" in md
        assert "### Role" in md


class TestCompareAndDiff:
    """Tests for version comparison."""

    def test_compare_versions(self, editor):
        """Compare two versions."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Original role"
            )
        ]

        v1 = editor.create("compare_test", components)

        v2 = editor.edit_component(
            v1.id,
            PromptComponentType.ROLE,
            "Updated role",
            change_description="Updated role content"
        )

        diff = editor.compare(v1.id, v2.id)

        assert diff.content_changed
        assert diff.change_description == "Updated role content"
        assert "role" in diff.components_changed
        assert diff.components_changed["role"]["old"] == "Original role"
        assert diff.components_changed["role"]["new"] == "Updated role"


class TestForkWorkflow:
    """Tests for fork workflow."""

    def test_fork_and_diverge(self, editor):
        """Fork prompt and make divergent changes."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Base role",
                order=20
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Base instructions",
                order=30
            ),
        ]

        main = editor.create("main_prompt", components, author="main_author")

        # Fork for experiment
        fork = editor.fork(
            main.id,
            "experiment_a",
            description="Experimental variant A"
        )

        assert fork.version == 1
        assert fork.is_fork()

        # Modify fork
        fork_v2 = editor.edit_component(
            fork.id,
            PromptComponentType.ROLE,
            "Experimental role",
            change_description="Testing new role"
        )

        # Verify main unchanged
        main_reloaded = editor.get_by_name("main_prompt")
        main_role = main_reloaded.get_component(PromptComponentType.ROLE)
        assert main_role.content == "Base role"

        # Verify fork changed
        fork_role = fork_v2.get_component(PromptComponentType.ROLE)
        assert fork_role.content == "Experimental role"


class TestReorderWorkflow:
    """Tests for component reordering."""

    def test_reorder_changes_composition(self, editor):
        """Reordering changes composed output order."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="ROLE_CONTENT",
                order=20
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="INSTRUCTIONS_CONTENT",
                order=30
            ),
        ]

        v1 = editor.create("reorder_test", components)

        # Original order: role first, instructions second
        composed_v1 = editor.compose(v1.id)
        role_pos_v1 = composed_v1.find("ROLE_CONTENT")
        inst_pos_v1 = composed_v1.find("INSTRUCTIONS_CONTENT")
        assert role_pos_v1 < inst_pos_v1

        # Reorder: instructions before role
        v2 = editor.reorder_components(
            v1.id,
            {
                PromptComponentType.INSTRUCTIONS: 15,
                PromptComponentType.ROLE: 25,
            }
        )

        composed_v2 = editor.compose(v2.id)
        role_pos_v2 = composed_v2.find("ROLE_CONTENT")
        inst_pos_v2 = composed_v2.find("INSTRUCTIONS_CONTENT")
        assert inst_pos_v2 < role_pos_v2


class TestSearchAndFilter:
    """Tests for search and filtering."""

    def test_search_by_multiple_criteria(self, editor):
        """Search with multiple criteria."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        editor.create(
            "alice_support",
            components,
            author="alice",
            tags=["support"],
            model_compatibility=["gpt-4"]
        )

        editor.create(
            "alice_sales",
            components,
            author="alice",
            tags=["sales"],
            model_compatibility=["gpt-4"]
        )

        editor.create(
            "bob_support",
            components,
            author="bob",
            tags=["support"],
            model_compatibility=["claude-3"]
        )

        # Search alice + support
        results = editor.search(
            author="alice",
            tags=["support"]
        )

        names = [r.name for r in results]
        assert "alice_support" in names
        assert "alice_sales" not in names
        assert "bob_support" not in names

    def test_search_by_component_type(self, editor):
        """Search by component types present."""
        role_only = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        role_and_inst = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            ),
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions"
            ),
        ]

        editor.create("role_only_prompt", role_only)
        editor.create("role_and_inst_prompt", role_and_inst)

        # Search for prompts with instructions
        results = editor.search(
            component_types=[PromptComponentType.INSTRUCTIONS]
        )

        names = [r.name for r in results]
        assert "role_and_inst_prompt" in names
        # role_only_prompt doesn't have instructions component


class TestErrorHandling:
    """Tests for error handling."""

    def test_preview_nonexistent_prompt(self, editor):
        """Previewing non-existent prompt raises error."""
        with pytest.raises(ValueError) as exc_info:
            editor.preview_component(
                "nonexistent_id",
                PromptComponentType.ROLE
            )

        assert "Prompt not found" in str(exc_info.value)

    def test_preview_nonexistent_component(self, editor):
        """Previewing non-existent component raises error."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]

        prompt = editor.create("error_test", components)

        with pytest.raises(ValueError) as exc_info:
            editor.preview_component(
                prompt.id,
                PromptComponentType.INSTRUCTIONS  # Not in prompt
            )

        assert "Component not found" in str(exc_info.value)

    def test_apply_to_agent_nonexistent_prompt(self, editor):
        """Applying non-existent prompt raises error."""
        agent = MockAgent()

        with pytest.raises(ValueError) as exc_info:
            editor.apply_to_agent("nonexistent_id", agent)

        assert "Prompt not found" in str(exc_info.value)

    def test_export_nonexistent_prompt(self, editor):
        """Exporting non-existent prompt raises error."""
        with pytest.raises(ValueError) as exc_info:
            editor.export_as_markdown("nonexistent_id")

        assert "Prompt not found" in str(exc_info.value)
