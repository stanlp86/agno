"""
Unit tests for Pydantic models.

Tests cover:
- PromptMetadata: tag operations, serialization
- PromptVersion: creation, properties, validation
- PromptDiff: diff computation
- PromptLineage: version management
- PromptStatus: enum values
"""

import hashlib
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agno.prompt_versioning.models import (
    PromptDiff,
    PromptLineage,
    PromptMetadata,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
)
from agno.prompt_versioning.mlflow_backend import generate_prompt_id


class TestPromptMetadata:
    """Tests for PromptMetadata model."""

    def test_default_values(self):
        """Default metadata has empty/None values."""
        meta = PromptMetadata()
        assert meta.author is None
        assert meta.description is None
        assert meta.tags == []
        assert meta.model_compatibility == []
        assert meta.use_case is None
        assert meta.custom == {}

    def test_full_initialization(self):
        """All fields can be set."""
        meta = PromptMetadata(
            author="alice",
            description="Test prompt",
            tags=["a", "b"],
            model_compatibility=["gpt-4"],
            use_case="Testing",
            custom={"key": "value"},
        )
        assert meta.author == "alice"
        assert meta.description == "Test prompt"
        assert meta.tags == ["a", "b"]
        assert meta.model_compatibility == ["gpt-4"]
        assert meta.use_case == "Testing"
        assert meta.custom == {"key": "value"}

    def test_add_tag_new(self):
        """Add tag that doesn't exist."""
        meta = PromptMetadata(tags=["a"])
        meta.add_tag("b")
        assert "b" in meta.tags
        assert meta.tags == ["a", "b"]

    def test_add_tag_duplicate(self):
        """Adding existing tag is idempotent."""
        meta = PromptMetadata(tags=["a", "b"])
        meta.add_tag("a")
        assert meta.tags == ["a", "b"]

    def test_remove_tag_existing(self):
        """Remove existing tag."""
        meta = PromptMetadata(tags=["a", "b", "c"])
        meta.remove_tag("b")
        assert "b" not in meta.tags
        assert meta.tags == ["a", "c"]

    def test_remove_tag_nonexistent(self):
        """Removing non-existent tag is safe."""
        meta = PromptMetadata(tags=["a"])
        meta.remove_tag("z")  # No error
        assert meta.tags == ["a"]

    def test_model_dump(self):
        """Serialization to dict works."""
        meta = PromptMetadata(author="alice", tags=["test"])
        data = meta.model_dump()
        assert isinstance(data, dict)
        assert data["author"] == "alice"
        assert data["tags"] == ["test"]

    def test_model_copy(self):
        """Copying metadata creates copy (deep copy for independence)."""
        meta = PromptMetadata(author="alice", tags=["test"])
        copy = meta.model_copy(deep=True)
        copy.add_tag("new")
        assert "new" in copy.tags
        # deep=True required for nested mutable objects (lists)
        assert "new" not in meta.tags


class TestPromptStatus:
    """Tests for PromptStatus enum."""

    def test_status_values(self):
        """All expected status values exist."""
        assert PromptStatus.DRAFT.value == "draft"
        assert PromptStatus.ACTIVE.value == "active"
        assert PromptStatus.ARCHIVED.value == "archived"
        assert PromptStatus.SNAPSHOT.value == "snapshot"

    def test_status_from_string(self):
        """Can create status from string."""
        assert PromptStatus("draft") == PromptStatus.DRAFT
        assert PromptStatus("active") == PromptStatus.ACTIVE

    def test_invalid_status(self):
        """Invalid status string raises error."""
        with pytest.raises(ValueError):
            PromptStatus("invalid")


class TestPromptVersion:
    """Tests for PromptVersion model."""

    @pytest.fixture
    def basic_prompt(self):
        """Create basic prompt for testing."""
        return PromptVersion(
            id="prompt_abc123def456",
            name="test_prompt",
            version=1,
            template=PromptTemplate(content="Hello {{name}}!"),
        )

    def test_basic_creation(self, basic_prompt):
        """Basic prompt creation with required fields."""
        assert basic_prompt.id == "prompt_abc123def456"
        assert basic_prompt.name == "test_prompt"
        assert basic_prompt.version == 1
        assert basic_prompt.content == "Hello {{name}}!"

    def test_default_values(self, basic_prompt):
        """Default values are set correctly."""
        assert basic_prompt.status == PromptStatus.DRAFT
        assert basic_prompt.parent_id is None
        assert basic_prompt.forked_from is None
        assert basic_prompt.snapshot_name is None

    def test_content_property(self, basic_prompt):
        """Content property returns template content."""
        assert basic_prompt.content == basic_prompt.template.content

    def test_variables_property(self, basic_prompt):
        """Variables property returns template variables."""
        assert basic_prompt.variables == {"name"}

    def test_render_method(self, basic_prompt):
        """Render method delegates to template."""
        result = basic_prompt.render(name="Alice")
        assert result == "Hello Alice!"

    def test_content_hash_computed(self, basic_prompt):
        """Content hash is auto-computed."""
        expected = hashlib.sha256(basic_prompt.content.encode()).hexdigest()[:16]
        assert basic_prompt.content_hash == expected

    def test_content_hash_changes_with_content(self):
        """Different content produces different hash."""
        p1 = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="Hello"),
        )
        p2 = PromptVersion(
            id="p2",
            name="test",
            version=1,
            template=PromptTemplate(content="Goodbye"),
        )
        assert p1.content_hash != p2.content_hash

    def test_is_snapshot_false(self, basic_prompt):
        """Non-snapshot prompt returns False."""
        assert basic_prompt.is_snapshot() is False

    def test_is_snapshot_true(self):
        """Snapshot prompt returns True."""
        prompt = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="Test"),
            status=PromptStatus.SNAPSHOT,
            snapshot_name="prod-v1",
        )
        assert prompt.is_snapshot() is True

    def test_is_fork_false(self, basic_prompt):
        """Non-fork prompt returns False."""
        assert basic_prompt.is_fork() is False

    def test_is_fork_true(self):
        """Forked prompt returns True."""
        prompt = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="Test"),
            forked_from="original_id",
        )
        assert prompt.is_fork() is True

    def test_get_version_string(self, basic_prompt):
        """Version string format."""
        assert basic_prompt.get_version_string() == "v1"

    def test_get_full_name(self, basic_prompt):
        """Full name includes version."""
        assert basic_prompt.get_full_name() == "test_prompt:v1"

    def test_name_validation_valid(self):
        """Valid names pass validation."""
        valid_names = ["test", "test_prompt", "test-prompt", "test.prompt", "Test123"]
        for name in valid_names:
            prompt = PromptVersion(
                id="p1",
                name=name,
                version=1,
                template=PromptTemplate(content="Test"),
            )
            assert prompt.name == name

    def test_name_validation_invalid(self):
        """Invalid names fail validation."""
        invalid_names = ["test prompt", "test/prompt", "test@prompt", ""]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                PromptVersion(
                    id="p1",
                    name=name,
                    version=1,
                    template=PromptTemplate(content="Test"),
                )

    def test_version_must_be_positive(self):
        """Version must be >= 1."""
        with pytest.raises(ValidationError):
            PromptVersion(
                id="p1",
                name="test",
                version=0,
                template=PromptTemplate(content="Test"),
            )

    def test_timestamps_set(self):
        """Created and updated timestamps are set."""
        prompt = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="Test"),
        )
        assert prompt.created_at is not None
        assert prompt.updated_at is not None


class TestPromptDiff:
    """Tests for PromptDiff computation."""

    @pytest.fixture
    def prompt_v1(self):
        """First version of prompt."""
        return PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="Hello {{name}}!"),
            metadata=PromptMetadata(author="alice", tags=["greeting"]),
        )

    @pytest.fixture
    def prompt_v2_content_changed(self, prompt_v1):
        """Second version with content change."""
        return PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="Hi {{name}}, welcome to {{place}}!"),
            metadata=PromptMetadata(author="alice", tags=["greeting"]),
            parent_id=prompt_v1.id,
        )

    @pytest.fixture
    def prompt_v2_metadata_changed(self, prompt_v1):
        """Second version with metadata change only."""
        return PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="Hello {{name}}!"),
            metadata=PromptMetadata(author="bob", tags=["greeting", "welcome"]),
            parent_id=prompt_v1.id,
        )

    def test_content_changed(self, prompt_v1, prompt_v2_content_changed):
        """Detect content change."""
        diff = PromptDiff.compute(prompt_v1, prompt_v2_content_changed)
        assert diff.content_changed is True
        assert diff.old_content == "Hello {{name}}!"
        assert diff.new_content == "Hi {{name}}, welcome to {{place}}!"

    def test_content_unchanged(self, prompt_v1, prompt_v2_metadata_changed):
        """Detect no content change."""
        diff = PromptDiff.compute(prompt_v1, prompt_v2_metadata_changed)
        assert diff.content_changed is False
        assert diff.old_content is None
        assert diff.new_content is None

    def test_variables_added(self, prompt_v1, prompt_v2_content_changed):
        """Detect added variables."""
        diff = PromptDiff.compute(prompt_v1, prompt_v2_content_changed)
        assert "place" in diff.variables_added

    def test_variables_removed(self):
        """Detect removed variables."""
        p1 = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="{{a}} {{b}} {{c}}"),
        )
        p2 = PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="{{a}}"),
            parent_id="p1",
        )
        diff = PromptDiff.compute(p1, p2)
        assert diff.variables_removed == {"b", "c"}

    def test_metadata_changes(self, prompt_v1, prompt_v2_metadata_changed):
        """Detect metadata changes."""
        diff = PromptDiff.compute(prompt_v1, prompt_v2_metadata_changed)
        assert "author" in diff.metadata_changes
        assert diff.metadata_changes["author"]["old"] == "alice"
        assert diff.metadata_changes["author"]["new"] == "bob"
        assert "tags" in diff.metadata_changes

    def test_version_ids(self, prompt_v1, prompt_v2_content_changed):
        """Diff contains correct version IDs."""
        diff = PromptDiff.compute(prompt_v1, prompt_v2_content_changed)
        assert diff.from_version == "p1"
        assert diff.to_version == "p2"

    def test_identical_prompts(self, prompt_v1):
        """Diff of identical prompts shows no changes."""
        diff = PromptDiff.compute(prompt_v1, prompt_v1)
        assert diff.content_changed is False
        assert diff.variables_added == set()
        assert diff.variables_removed == set()
        assert diff.metadata_changes == {}


class TestPromptLineage:
    """Tests for PromptLineage tracking."""

    @pytest.fixture
    def sample_lineage(self):
        """Create sample lineage with multiple versions."""
        v1 = PromptVersion(
            id="p1",
            name="test",
            version=1,
            template=PromptTemplate(content="v1"),
        )
        v2 = PromptVersion(
            id="p2",
            name="test",
            version=2,
            template=PromptTemplate(content="v2"),
            parent_id="p1",
        )
        v3 = PromptVersion(
            id="p3",
            name="test",
            version=3,
            template=PromptTemplate(content="v3"),
            parent_id="p2",
            status=PromptStatus.SNAPSHOT,
            snapshot_name="prod-v1",
        )
        return PromptLineage(
            root_id="p1",
            name="test",
            versions=[v1, v2, v3],
            snapshots={"prod-v1": "p3"},
        )

    def test_get_version_exists(self, sample_lineage):
        """Get existing version by number."""
        v2 = sample_lineage.get_version(2)
        assert v2 is not None
        assert v2.id == "p2"

    def test_get_version_not_exists(self, sample_lineage):
        """Get non-existent version returns None."""
        v99 = sample_lineage.get_version(99)
        assert v99 is None

    def test_get_latest(self, sample_lineage):
        """Get latest version."""
        latest = sample_lineage.get_latest()
        assert latest is not None
        assert latest.version == 3

    def test_get_latest_empty(self):
        """Get latest from empty lineage."""
        lineage = PromptLineage(root_id="p1", name="test", versions=[])
        assert lineage.get_latest() is None

    def test_get_snapshot(self, sample_lineage):
        """Get snapshot by name."""
        snap = sample_lineage.get_snapshot("prod-v1")
        assert snap is not None
        assert snap.id == "p3"

    def test_get_snapshot_not_exists(self, sample_lineage):
        """Get non-existent snapshot."""
        snap = sample_lineage.get_snapshot("nonexistent")
        assert snap is None

    def test_add_version(self, sample_lineage):
        """Add new version to lineage."""
        v4 = PromptVersion(
            id="p4",
            name="test",
            version=4,
            template=PromptTemplate(content="v4"),
            parent_id="p3",
        )
        sample_lineage.add_version(v4)
        assert len(sample_lineage.versions) == 4
        assert sample_lineage.get_version(4) is not None

    def test_add_version_with_snapshot(self, sample_lineage):
        """Adding snapshot version updates snapshots dict."""
        v4 = PromptVersion(
            id="p4",
            name="test",
            version=4,
            template=PromptTemplate(content="v4"),
            status=PromptStatus.SNAPSHOT,
            snapshot_name="prod-v2",
        )
        sample_lineage.add_version(v4)
        assert "prod-v2" in sample_lineage.snapshots
        assert sample_lineage.snapshots["prod-v2"] == "p4"

    def test_get_history(self, sample_lineage):
        """Get history summary."""
        history = sample_lineage.get_history()
        assert len(history) == 3
        assert history[0]["version"] == 1
        assert history[2]["version"] == 3
        assert history[2]["snapshot_name"] == "prod-v1"


class TestGeneratePromptId:
    """Tests for prompt ID generation."""

    def test_format(self):
        """ID has correct format."""
        id1 = generate_prompt_id()
        assert id1.startswith("prompt_")
        assert len(id1) == 19  # "prompt_" (7) + 12 hex chars

    def test_uniqueness(self):
        """Generated IDs are unique."""
        ids = [generate_prompt_id() for _ in range(100)]
        assert len(ids) == len(set(ids))

    def test_valid_hex(self):
        """ID suffix is valid hex."""
        id1 = generate_prompt_id()
        suffix = id1[7:]  # Remove "prompt_"
        int(suffix, 16)  # Should not raise
