"""
Integration tests for PromptManager.

Tests cover:
- Create workflow
- Edit workflow (version chains)
- Snapshot workflow
- Fork workflow
- Render operations
- Search and list operations
- Business rule enforcement

These tests use real MLflow with temporary directories.
"""

import pytest

from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.models import PromptStatus


class TestCreate:
    """Tests for prompt creation."""

    def test_create_minimal(self, manager: PromptManager):
        """Create with minimum required fields."""
        prompt = manager.create(name="minimal", content="Hello!")
        assert prompt.name == "minimal"
        assert prompt.content == "Hello!"
        assert prompt.version == 1
        assert prompt.status == PromptStatus.DRAFT

    def test_create_with_all_fields(self, manager: PromptManager):
        """Create with all optional fields."""
        prompt = manager.create(
            name="full",
            content="Hello {{name}}!",
            description="Full test prompt",
            author="test-author",
            tags=["test", "full"],
            model_compatibility=["gpt-4"],
            use_case="Testing",
            custom_metadata={"key": "value"},
        )
        assert prompt.metadata.description == "Full test prompt"
        assert prompt.metadata.author == "test-author"
        assert prompt.metadata.tags == ["test", "full"]
        assert prompt.metadata.model_compatibility == ["gpt-4"]
        assert prompt.metadata.use_case == "Testing"
        assert prompt.metadata.custom == {"key": "value"}

    def test_create_extracts_variables(self, manager: PromptManager):
        """Create extracts template variables."""
        prompt = manager.create(
            name="vars_test",
            content="{{a}} {{b}} {{c}}",
        )
        assert prompt.variables == {"a", "b", "c"}

    def test_create_persists(self, manager: PromptManager):
        """Created prompt can be retrieved."""
        prompt = manager.create(name="persist_test", content="Test")
        loaded = manager.get(prompt.id)
        assert loaded is not None
        assert loaded.id == prompt.id

    def test_create_second_version(self, manager: PromptManager):
        """Creating same name after exists creates v2."""
        manager.create(name="multi_create", content="v1")
        prompt2 = manager.create(name="multi_create", content="v2")
        assert prompt2.version == 2


class TestEdit:
    """Tests for prompt editing."""

    def test_edit_content(self, manager: PromptManager):
        """Edit creates new version with changed content."""
        v1 = manager.create(name="edit_content", content="Original")
        v2 = manager.edit(v1.id, content="Modified")

        assert v2.version == 2
        assert v2.content == "Modified"
        assert v2.parent_id == v1.id

    def test_edit_metadata(self, manager: PromptManager):
        """Edit metadata without changing content."""
        v1 = manager.create(
            name="edit_meta",
            content="Static",
            author="alice",
            tags=["original"],
        )
        v2 = manager.edit(v1.id, author="bob", tags=["updated"])

        assert v2.version == 2
        assert v2.content == "Static"  # Content unchanged
        assert v2.metadata.author == "bob"
        assert v2.metadata.tags == ["updated"]

    def test_edit_preserves_unset_fields(self, manager: PromptManager):
        """Edit preserves fields not explicitly changed."""
        v1 = manager.create(
            name="edit_preserve",
            content="Test",
            author="alice",
            description="Original desc",
            tags=["a", "b"],
        )
        v2 = manager.edit(v1.id, author="bob")  # Only change author

        assert v2.metadata.description == "Original desc"
        assert v2.metadata.tags == ["a", "b"]

    def test_edit_custom_metadata_merges(self, manager: PromptManager):
        """Custom metadata is merged, not replaced."""
        v1 = manager.create(
            name="edit_merge",
            content="Test",
            custom_metadata={"key1": "value1"},
        )
        v2 = manager.edit(v1.id, custom_metadata={"key2": "value2"})

        assert v2.metadata.custom == {"key1": "value1", "key2": "value2"}

    def test_edit_nonexistent_raises(self, manager: PromptManager):
        """Editing non-existent prompt raises error."""
        with pytest.raises(ValueError, match="not found"):
            manager.edit("nonexistent_id", content="New")

    def test_edit_chain(self, manager: PromptManager):
        """Multiple edits form proper chain."""
        v1 = manager.create(name="chain", content="v1")
        v2 = manager.edit(v1.id, content="v2")
        v3 = manager.edit(v2.id, content="v3")
        v4 = manager.edit(v3.id, content="v4")

        assert v4.version == 4
        assert v4.parent_id == v3.id
        assert v3.parent_id == v2.id
        assert v2.parent_id == v1.id


class TestSnapshot:
    """Tests for snapshot creation."""

    def test_snapshot_basic(self, manager: PromptManager):
        """Create basic snapshot."""
        v1 = manager.create(name="snap_basic", content="Test")
        snap = manager.snapshot(v1.id, "prod-v1")

        assert snap.status == PromptStatus.SNAPSHOT
        assert snap.snapshot_name == "prod-v1"
        assert snap.is_snapshot()

    def test_snapshot_with_description(self, manager: PromptManager):
        """Snapshot can have description."""
        v1 = manager.create(name="snap_desc", content="Test")
        snap = manager.snapshot(v1.id, "release", description="Release notes here")

        assert snap.metadata.description == "Release notes here"

    def test_snapshot_preserves_content(self, manager: PromptManager):
        """Snapshot has same content as source."""
        v1 = manager.create(name="snap_content", content="Important content")
        snap = manager.snapshot(v1.id, "frozen")

        assert snap.content == v1.content
        assert snap.content_hash == v1.content_hash

    def test_snapshot_creates_new_version(self, manager: PromptManager):
        """Snapshot increments version number."""
        v1 = manager.create(name="snap_version", content="Test")
        snap = manager.snapshot(v1.id, "v1")

        assert snap.version == 2
        assert snap.parent_id == v1.id

    def test_snapshot_duplicate_name_raises(self, manager: PromptManager):
        """Duplicate snapshot name raises error."""
        v1 = manager.create(name="snap_dup", content="Test")
        manager.snapshot(v1.id, "unique")

        v2 = manager.edit(v1.id, content="Updated")
        with pytest.raises(ValueError, match="already exists"):
            manager.snapshot(v2.id, "unique")

    def test_snapshot_nonexistent_raises(self, manager: PromptManager):
        """Snapshot of non-existent prompt raises error."""
        with pytest.raises(ValueError, match="not found"):
            manager.snapshot("nonexistent", "snap")

    def test_snapshot_retrievable(self, manager: PromptManager):
        """Snapshot can be retrieved by name."""
        v1 = manager.create(name="snap_retrieve", content="Test")
        snap = manager.snapshot(v1.id, "my-snapshot")

        loaded = manager.get_snapshot("snap_retrieve", "my-snapshot")
        assert loaded is not None
        assert loaded.id == snap.id


class TestFork:
    """Tests for forking prompts."""

    def test_fork_basic(self, manager: PromptManager):
        """Fork creates new prompt at v1."""
        original = manager.create(name="fork_source", content="Original content")
        forked = manager.fork(original.id, "fork_target")

        assert forked.name == "fork_target"
        assert forked.version == 1
        assert forked.content == original.content
        assert forked.forked_from == original.id
        assert forked.is_fork()

    def test_fork_adds_tag(self, manager: PromptManager):
        """Fork automatically adds 'forked' tag."""
        original = manager.create(name="fork_tag_source", content="Test")
        forked = manager.fork(original.id, "fork_tag_target")

        assert "forked" in forked.metadata.tags

    def test_fork_with_metadata(self, manager: PromptManager):
        """Fork can override description and author."""
        original = manager.create(
            name="fork_meta_source",
            content="Test",
            author="alice",
            description="Original",
        )
        forked = manager.fork(
            original.id,
            "fork_meta_target",
            description="Forked for experimentation",
            author="bob",
        )

        assert forked.metadata.description == "Forked for experimentation"
        assert forked.metadata.author == "bob"

    def test_fork_duplicate_name_raises(self, manager: PromptManager):
        """Fork to existing name raises error."""
        manager.create(name="existing_prompt", content="Test")
        original = manager.create(name="fork_dup_source", content="Test")

        with pytest.raises(ValueError, match="already exists"):
            manager.fork(original.id, "existing_prompt")

    def test_fork_nonexistent_raises(self, manager: PromptManager):
        """Fork of non-existent prompt raises error."""
        with pytest.raises(ValueError, match="not found"):
            manager.fork("nonexistent", "new_name")

    def test_fork_independent_lineage(self, manager: PromptManager):
        """Forked prompt has independent version history."""
        original = manager.create(name="fork_indep_source", content="Test")
        forked = manager.fork(original.id, "fork_indep_target")

        # Edit both
        manager.edit(original.id, content="Original v2")
        manager.edit(forked.id, content="Forked v2")

        orig_versions = manager.list_versions("fork_indep_source")
        fork_versions = manager.list_versions("fork_indep_target")

        assert len(orig_versions) == 2
        assert len(fork_versions) == 2


class TestRender:
    """Tests for rendering prompts."""

    def test_render_by_name(self, manager: PromptManager):
        """Render prompt by name."""
        manager.create(name="render_name", content="Hello {{name}}!")
        result = manager.render(prompt_name="render_name", name="Alice")
        assert result == "Hello Alice!"

    def test_render_by_id(self, manager: PromptManager):
        """Render prompt by ID."""
        prompt = manager.create(name="render_id", content="Hi {{name}}!")
        result = manager.render(prompt_id=prompt.id, name="Bob")
        assert result == "Hi Bob!"

    def test_render_by_version(self, manager: PromptManager):
        """Render specific version."""
        v1 = manager.create(name="render_ver", content="Version 1: {{x}}")
        manager.edit(v1.id, content="Version 2: {{x}}")

        result = manager.render(prompt_name="render_ver", version=1, x="test")
        assert result == "Version 1: test"

    def test_render_by_snapshot(self, manager: PromptManager):
        """Render by snapshot name."""
        v1 = manager.create(name="render_snap", content="Snapshot: {{val}}")
        manager.snapshot(v1.id, "frozen")

        result = manager.render(
            prompt_name="render_snap",
            snapshot_name="frozen",
            val="value",
        )
        assert result == "Snapshot: value"

    def test_render_missing_variable_raises(self, manager: PromptManager):
        """Render with missing variables raises error."""
        manager.create(name="render_missing", content="{{a}} {{b}}")
        with pytest.raises(ValueError, match="Missing"):
            manager.render(prompt_name="render_missing", a="A")

    def test_render_nonexistent_raises(self, manager: PromptManager):
        """Render non-existent prompt raises error."""
        with pytest.raises(ValueError, match="not found"):
            manager.render(prompt_name="nonexistent")


class TestStatusOperations:
    """Tests for status change operations."""

    def test_activate(self, manager: PromptManager):
        """Activate creates new ACTIVE version."""
        v1 = manager.create(name="activate_test", content="Test")
        v2 = manager.activate(v1.id)

        assert v2.status == PromptStatus.ACTIVE
        assert v2.version == 2

    def test_archive(self, manager: PromptManager):
        """Archive creates new ARCHIVED version."""
        v1 = manager.create(name="archive_test", content="Test")
        v2 = manager.archive(v1.id)

        assert v2.status == PromptStatus.ARCHIVED
        assert v2.version == 2


class TestListAndSearch:
    """Tests for list and search operations."""

    @pytest.fixture(autouse=True)
    def setup_data(self, manager: PromptManager):
        """Create test data."""
        self.prompts = {
            "alpha": manager.create(
                name="alpha",
                content="Alpha content",
                author="alice",
                tags=["group1"],
            ),
            "beta": manager.create(
                name="beta",
                content="Beta content",
                author="bob",
                tags=["group1", "special"],
            ),
            "gamma": manager.create(
                name="gamma",
                content="Gamma content",
                author="alice",
                tags=["group2"],
            ),
        }

    def test_list_prompts(self, manager: PromptManager):
        """List all prompt names."""
        names = manager.list_prompts()
        assert set(names) == {"alpha", "beta", "gamma"}

    def test_list_versions(self, manager: PromptManager):
        """List versions for a prompt."""
        manager.edit(self.prompts["alpha"].id, content="v2")
        versions = manager.list_versions("alpha")
        assert len(versions) == 2

    def test_list_snapshots(self, manager: PromptManager):
        """List snapshots."""
        manager.snapshot(self.prompts["alpha"].id, "snap1")
        manager.snapshot(self.prompts["alpha"].id, "snap2")

        snapshots = manager.list_snapshots("alpha")
        snap_names = [s[0] for s in snapshots]
        assert "snap1" in snap_names
        assert "snap2" in snap_names

    def test_search_by_tags(self, manager: PromptManager):
        """Search by tags."""
        results = manager.search(tags=["group1"])
        names = [r.name for r in results]
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" not in names

    def test_search_by_author(self, manager: PromptManager):
        """Search by author."""
        results = manager.search(author="alice")
        names = [r.name for r in results]
        assert "alpha" in names
        assert "gamma" in names
        assert "beta" not in names


class TestLineageAndDiff:
    """Tests for lineage and diff operations."""

    def test_get_lineage(self, manager: PromptManager):
        """Get full lineage."""
        v1 = manager.create(name="lineage", content="v1")
        v2 = manager.edit(v1.id, content="v2")
        manager.snapshot(v2.id, "snap")

        lineage = manager.get_lineage("lineage")
        assert lineage.name == "lineage"
        assert len(lineage.versions) == 3
        assert "snap" in lineage.snapshots

    def test_compare(self, manager: PromptManager):
        """Compare two versions."""
        v1 = manager.create(name="compare", content="{{a}}")
        v2 = manager.edit(v1.id, content="{{a}} {{b}}")

        diff = manager.compare(v1.id, v2.id)
        assert diff.content_changed
        assert "b" in diff.variables_added

    def test_export_lineage(self, manager: PromptManager):
        """Export lineage to dict."""
        v1 = manager.create(name="export", content="Test")
        manager.snapshot(v1.id, "v1")

        data = manager.export_lineage("export")
        assert data["name"] == "export"
        assert len(data["versions"]) == 2
        assert "v1" in data["snapshots"]


class TestDelete:
    """Tests for deletion."""

    def test_delete_existing(self, manager: PromptManager):
        """Delete existing prompt."""
        prompt = manager.create(name="delete_test", content="Test")
        result = manager.delete(prompt.id)

        assert result is True
        assert manager.get(prompt.id) is None

    def test_delete_nonexistent(self, manager: PromptManager):
        """Delete non-existent returns False."""
        result = manager.delete("nonexistent")
        assert result is False


class TestDuplicate:
    """Tests for duplicate operation."""

    def test_duplicate_with_name(self, manager: PromptManager):
        """Duplicate with new name."""
        original = manager.create(name="dup_source", content="Test")
        copy = manager.duplicate(original.id, "dup_target")

        assert copy.name == "dup_target"
        assert copy.content == original.content
        assert copy.forked_from == original.id

    def test_duplicate_auto_name(self, manager: PromptManager):
        """Duplicate with auto-generated name."""
        original = manager.create(name="auto_dup", content="Test")
        copy = manager.duplicate(original.id)

        assert copy.name == "auto_dup_copy"
