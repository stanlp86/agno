"""
Integration tests for MLflow component serialization.

Tests cover:
- Saving and loading prompts with components
- Component data integrity
- Change description persistence
- Mixed component types (including CUSTOM)

Cross-ref: SYSTEM_PROMPT_EDITOR_SPEC.md Section 5
"""

import pytest

from agno.prompt_versioning.models import (
    PromptComponentType,
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


class TestComponentSerialization:
    """Tests for saving and loading prompts with components."""

    def test_save_and_load_prompt_with_components(self, mlflow_store):
        """Components are preserved through save/load cycle."""
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

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="test_system_prompt",
            version=1,
            template=PromptTemplate(content="Composed content"),
            status=PromptStatus.DRAFT,
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded is not None
        assert loaded.is_system_prompt()
        assert len(loaded.components) == 2

    def test_component_content_preserved(self, mlflow_store):
        """Component content is exactly preserved."""
        content = "You are a helpful assistant.\n\nBe precise and thorough."
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content=content
            )
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="content_test",
            version=1,
            template=PromptTemplate(content=content),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded.components[0].content == content

    def test_component_order_preserved(self, mlflow_store):
        """Component order values are preserved."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content="Instructions",
                order=15  # Non-default order
            ),
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role",
                order=25  # Non-default order
            ),
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="order_test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        # Find by type
        role = next(c for c in loaded.components if c.type == PromptComponentType.ROLE)
        inst = next(c for c in loaded.components if c.type == PromptComponentType.INSTRUCTIONS)

        assert role.order == 25
        assert inst.order == 15

    def test_component_xml_tag_preserved(self, mlflow_store):
        """Component XML tags are preserved."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role content",
                xml_tag="custom_role_tag"
            )
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="xml_tag_test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded.components[0].xml_tag == "custom_role_tag"

    def test_component_enabled_preserved(self, mlflow_store):
        """Component enabled flag is preserved."""
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

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="enabled_test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        role = next(c for c in loaded.components if c.type == PromptComponentType.ROLE)
        inst = next(c for c in loaded.components if c.type == PromptComponentType.INSTRUCTIONS)

        assert role.enabled is True
        assert inst.enabled is False

    def test_component_metadata_preserved(self, mlflow_store):
        """Component metadata dict is preserved."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.MEMORIES,
                content="Memory content",
                metadata={
                    "source": "MemoryManager",
                    "strategy": "last_n",
                    "limit": 10,
                    "nested": {"key": "value"}
                }
            )
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="metadata_test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        meta = loaded.components[0].metadata
        assert meta["source"] == "MemoryManager"
        assert meta["strategy"] == "last_n"
        assert meta["limit"] == 10
        assert meta["nested"]["key"] == "value"

    def test_custom_component_name_preserved(self, mlflow_store):
        """CUSTOM component names are preserved."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="guardrails",
                content="Guardrails content"
            ),
            SystemPromptComponent(
                type=PromptComponentType.CUSTOM,
                name="personality",
                content="Personality content"
            ),
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="custom_name_test",
            version=1,
            template=PromptTemplate(content="Test"),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        customs = [c for c in loaded.components if c.type == PromptComponentType.CUSTOM]
        names = {c.name for c in customs}

        assert "guardrails" in names
        assert "personality" in names

    def test_change_description_preserved(self, mlflow_store):
        """Change description is preserved through save/load."""
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="change_desc_test",
            version=2,
            template=PromptTemplate(content="Updated content"),
            parent_id="prompt_v1",
            change_description="Updated role to be more helpful and concise",
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded.change_description == "Updated role to be more helpful and concise"

    def test_change_description_with_components(self, mlflow_store):
        """Change description works with component-based prompts."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Updated role content"
            )
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="change_desc_components",
            version=2,
            template=PromptTemplate(content="Updated"),
            parent_id="prompt_v1",
            change_description="Modified role component",
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded.is_system_prompt()
        assert loaded.change_description == "Modified role component"

    def test_prompt_without_components_backwards_compatible(self, mlflow_store):
        """Prompts without components still work."""
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="traditional_prompt",
            version=1,
            template=PromptTemplate(content="Hello {{name}}!"),
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded.components is None
        assert loaded.is_system_prompt() is False
        assert loaded.change_description is None


class TestComponentDataIntegrity:
    """Tests for component data integrity across operations."""

    def test_all_component_types_serialize(self, mlflow_store):
        """All component types can be serialized."""
        all_types = [
            PromptComponentType.DESCRIPTION,
            PromptComponentType.ROLE,
            PromptComponentType.INSTRUCTIONS,
            PromptComponentType.TOOL_INSTRUCTIONS,
            PromptComponentType.EXPECTED_OUTPUT,
            PromptComponentType.ADDITIONAL_INFO,
            PromptComponentType.ADDITIONAL_CONTEXT,
            PromptComponentType.MEMORIES,
            PromptComponentType.SESSION_SUMMARY,
            PromptComponentType.CULTURAL_KNOWLEDGE,
            PromptComponentType.SESSION_STATE,
        ]

        components = [
            SystemPromptComponent(
                type=ct,
                content=f"Content for {ct.value}"
            )
            for ct in all_types
        ]

        # Add a CUSTOM component
        components.append(SystemPromptComponent(
            type=PromptComponentType.CUSTOM,
            name="custom_component",
            content="Custom content"
        ))

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="all_types_test",
            version=1,
            template=PromptTemplate(content="All types"),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert len(loaded.components) == len(components)
        loaded_types = {c.type for c in loaded.components}
        expected_types = {c.type for c in components}
        assert loaded_types == expected_types

    def test_unicode_in_component_content(self, mlflow_store):
        """Unicode content in components is preserved."""
        unicode_content = "🤖 Role: 你好世界 Привет мир مرحبا"
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content=unicode_content
            )
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="unicode_test",
            version=1,
            template=PromptTemplate(content=unicode_content),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded.components[0].content == unicode_content

    def test_multiline_component_content(self, mlflow_store):
        """Multiline content in components is preserved."""
        multiline_content = """You are a helpful assistant.

Your responsibilities include:
- Answering questions
- Providing explanations
- Helping with tasks

Remember to:
1. Be concise
2. Be accurate
3. Be helpful"""

        components = [
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content=multiline_content
            )
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="multiline_test",
            version=1,
            template=PromptTemplate(content=multiline_content),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert loaded.components[0].content == multiline_content

    def test_components_with_template_variables(self, mlflow_store):
        """Template variables in component content are preserved."""
        content = "Hello {{user_name}}, your task is {{task}}."
        components = [
            SystemPromptComponent(
                type=PromptComponentType.INSTRUCTIONS,
                content=content
            )
        ]

        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="variable_test",
            version=1,
            template=PromptTemplate(content=content),
            components=components,
        )

        mlflow_store.save(prompt)
        loaded = mlflow_store.load(prompt.id)

        assert "{{user_name}}" in loaded.components[0].content
        assert "{{task}}" in loaded.components[0].content


class TestComponentSearch:
    """Tests for searching prompts with components."""

    def test_search_finds_system_prompts(self, mlflow_store):
        """Search returns prompts with components."""
        # Create a system prompt
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role content"
            )
        ]
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="searchable_system_prompt",
            version=1,
            template=PromptTemplate(content="Content"),
            metadata=PromptMetadata(tags=["system_prompt", "searchable"]),
            components=components,
        )
        mlflow_store.save(prompt)

        # Search by tag
        results = mlflow_store.search(tags=["system_prompt"])

        assert len(results) >= 1
        found = next((r for r in results if r.id == prompt.id), None)
        assert found is not None
        assert found.is_system_prompt()

    def test_load_by_name_preserves_components(self, mlflow_store):
        """load_by_name preserves components."""
        components = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role"
            )
        ]
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="load_by_name_test",
            version=1,
            template=PromptTemplate(content="Content"),
            components=components,
        )
        mlflow_store.save(prompt)

        loaded = mlflow_store.load_by_name("load_by_name_test")

        assert loaded is not None
        assert loaded.is_system_prompt()
        assert len(loaded.components) == 1

    def test_list_versions_preserves_components(self, mlflow_store):
        """list_versions preserves components for each version."""
        # Create v1
        components_v1 = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role v1"
            )
        ]
        v1 = PromptVersion(
            id=generate_prompt_id(),
            name="version_list_test",
            version=1,
            template=PromptTemplate(content="v1"),
            components=components_v1,
        )
        mlflow_store.save(v1)

        # Create v2 with updated component
        components_v2 = [
            SystemPromptComponent(
                type=PromptComponentType.ROLE,
                content="Role v2"
            )
        ]
        v2 = PromptVersion(
            id=generate_prompt_id(),
            name="version_list_test",
            version=2,
            template=PromptTemplate(content="v2"),
            parent_id=v1.id,
            components=components_v2,
            change_description="Updated role",
        )
        mlflow_store.save(v2)

        versions = mlflow_store.list_versions("version_list_test")

        assert len(versions) == 2
        v1_loaded = next(v for v in versions if v.version == 1)
        v2_loaded = next(v for v in versions if v.version == 2)

        assert v1_loaded.components[0].content == "Role v1"
        assert v2_loaded.components[0].content == "Role v2"
        assert v2_loaded.change_description == "Updated role"
