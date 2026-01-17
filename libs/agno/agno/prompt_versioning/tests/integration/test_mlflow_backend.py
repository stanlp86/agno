"""
Integration tests for MLflowPromptStore.

Tests cover:
- Experiment creation and retrieval
- Run creation (save)
- Artifact storage and retrieval
- Search and query operations
- Deletion
- Edge cases with real MLflow

These tests use real MLflow with temporary directories.
"""

import pytest

from agno.prompt_versioning.models import (
    PromptMetadata,
    PromptStatus,
    PromptTemplate,
    PromptVersion,
)
from agno.prompt_versioning.mlflow_backend import (
    MLflowPromptStore,
    generate_prompt_id,
)


class TestExperimentManagement:
    """Tests for MLflow experiment operations."""

    def test_experiment_created_on_first_save(self, mlflow_store: MLflowPromptStore):
        """Experiment is created when first prompt is saved."""
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="new_experiment_test",
            version=1,
            template=PromptTemplate(content="Test"),
        )
        mlflow_store.save(prompt)

        # Verify experiment exists
        exp_name = f"{mlflow_store.config.experiment_prefix}/new_experiment_test"
        exp = mlflow_store.client.get_experiment_by_name(exp_name)
        assert exp is not None

    def test_experiment_reused_on_subsequent_saves(self, mlflow_store: MLflowPromptStore):
        """Same experiment is reused for same prompt name."""
        prompt1 = PromptVersion(
            id=generate_prompt_id(),
            name="reuse_test",
            version=1,
            template=PromptTemplate(content="v1"),
        )
        prompt2 = PromptVersion(
            id=generate_prompt_id(),
            name="reuse_test",
            version=2,
            template=PromptTemplate(content="v2"),
            parent_id=prompt1.id,
        )

        mlflow_store.save(prompt1)
        mlflow_store.save(prompt2)

        # Both should be in same experiment
        versions = mlflow_store.list_versions("reuse_test")
        assert len(versions) == 2

    def test_different_names_different_experiments(self, mlflow_store: MLflowPromptStore):
        """Different prompt names create different experiments."""
        p1 = PromptVersion(
            id=generate_prompt_id(),
            name="prompt_a",
            version=1,
            template=PromptTemplate(content="A"),
        )
        p2 = PromptVersion(
            id=generate_prompt_id(),
            name="prompt_b",
            version=1,
            template=PromptTemplate(content="B"),
        )

        mlflow_store.save(p1)
        mlflow_store.save(p2)

        prompts = mlflow_store.list_prompts()
        assert "prompt_a" in prompts
        assert "prompt_b" in prompts


class TestSaveAndLoad:
    """Tests for saving and loading prompts."""

    def test_save_returns_run_id(self, mlflow_store: MLflowPromptStore):
        """Save returns MLflow run ID."""
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="save_test",
            version=1,
            template=PromptTemplate(content="Test"),
        )
        run_id = mlflow_store.save(prompt)
        assert run_id is not None
        assert len(run_id) == 32  # MLflow run IDs are 32 hex chars

    def test_load_by_id(self, mlflow_store: MLflowPromptStore):
        """Load prompt by ID."""
        original = PromptVersion(
            id=generate_prompt_id(),
            name="load_test",
            version=1,
            template=PromptTemplate(content="Hello {{name}}!"),
            metadata=PromptMetadata(author="test", tags=["a", "b"]),
        )
        mlflow_store.save(original)

        loaded = mlflow_store.load(original.id)
        assert loaded is not None
        assert loaded.id == original.id
        assert loaded.name == original.name
        assert loaded.version == original.version
        assert loaded.content == original.content
        assert loaded.metadata.author == original.metadata.author
        assert loaded.metadata.tags == original.metadata.tags

    def test_load_nonexistent_returns_none(self, mlflow_store: MLflowPromptStore):
        """Loading non-existent ID returns None."""
        loaded = mlflow_store.load("nonexistent_id")
        assert loaded is None

    def test_load_by_name_latest(self, mlflow_store: MLflowPromptStore):
        """Load latest version by name."""
        for i in range(1, 4):
            prompt = PromptVersion(
                id=generate_prompt_id(),
                name="latest_test",
                version=i,
                template=PromptTemplate(content=f"v{i}"),
            )
            mlflow_store.save(prompt)

        loaded = mlflow_store.load_by_name("latest_test")
        assert loaded is not None
        assert loaded.version == 3

    def test_load_by_name_specific_version(self, mlflow_store: MLflowPromptStore):
        """Load specific version by name."""
        for i in range(1, 4):
            prompt = PromptVersion(
                id=generate_prompt_id(),
                name="version_test",
                version=i,
                template=PromptTemplate(content=f"v{i}"),
            )
            mlflow_store.save(prompt)

        loaded = mlflow_store.load_by_name("version_test", version=2)
        assert loaded is not None
        assert loaded.version == 2
        assert loaded.content == "v2"

    def test_load_by_name_nonexistent(self, mlflow_store: MLflowPromptStore):
        """Load non-existent name returns None."""
        loaded = mlflow_store.load_by_name("nonexistent")
        assert loaded is None

    def test_load_snapshot(self, mlflow_store: MLflowPromptStore):
        """Load prompt by snapshot name."""
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="snapshot_load_test",
            version=1,
            template=PromptTemplate(content="Snapshot content"),
            status=PromptStatus.SNAPSHOT,
            snapshot_name="prod-v1",
        )
        mlflow_store.save(prompt)

        loaded = mlflow_store.load_snapshot("snapshot_load_test", "prod-v1")
        assert loaded is not None
        assert loaded.snapshot_name == "prod-v1"

    def test_load_snapshot_nonexistent(self, mlflow_store: MLflowPromptStore):
        """Load non-existent snapshot returns None."""
        loaded = mlflow_store.load_snapshot("any", "nonexistent")
        assert loaded is None


class TestDataIntegrity:
    """Tests for data integrity across save/load cycles."""

    def test_all_fields_preserved(self, mlflow_store: MLflowPromptStore):
        """All prompt fields are preserved after save/load."""
        original = PromptVersion(
            id=generate_prompt_id(),
            name="integrity_test",
            version=5,
            template=PromptTemplate(content="Hello {{name}} from {{place}}!"),
            status=PromptStatus.ACTIVE,
            metadata=PromptMetadata(
                author="alice",
                description="Test prompt for integrity",
                tags=["test", "integrity"],
                model_compatibility=["gpt-4", "claude-3"],
                use_case="Testing",
                custom={"key": "value"},
            ),
            parent_id="parent_123",
            forked_from="fork_source_456",
            snapshot_name="test-snapshot",
        )
        mlflow_store.save(original)

        loaded = mlflow_store.load(original.id)
        assert loaded.id == original.id
        assert loaded.name == original.name
        assert loaded.version == original.version
        assert loaded.content == original.content
        assert loaded.status == original.status
        assert loaded.metadata.author == original.metadata.author
        assert loaded.metadata.description == original.metadata.description
        assert loaded.metadata.tags == original.metadata.tags
        assert loaded.metadata.model_compatibility == original.metadata.model_compatibility
        assert loaded.metadata.use_case == original.metadata.use_case
        assert loaded.metadata.custom == original.metadata.custom
        assert loaded.parent_id == original.parent_id
        assert loaded.forked_from == original.forked_from
        assert loaded.snapshot_name == original.snapshot_name

    def test_content_hash_preserved(self, mlflow_store: MLflowPromptStore):
        """Content hash is preserved after save/load."""
        original = PromptVersion(
            id=generate_prompt_id(),
            name="hash_test",
            version=1,
            template=PromptTemplate(content="Test content for hashing"),
        )
        mlflow_store.save(original)

        loaded = mlflow_store.load(original.id)
        assert loaded.content_hash == original.content_hash

    def test_timestamps_preserved(self, mlflow_store: MLflowPromptStore):
        """Timestamps are preserved after save/load."""
        original = PromptVersion(
            id=generate_prompt_id(),
            name="timestamp_test",
            version=1,
            template=PromptTemplate(content="Test"),
        )
        mlflow_store.save(original)

        loaded = mlflow_store.load(original.id)
        # Compare ISO format strings (MLflow stores as strings)
        assert loaded.created_at.isoformat()[:19] == original.created_at.isoformat()[:19]

    def test_unicode_content_preserved(self, mlflow_store: MLflowPromptStore):
        """Unicode content is preserved."""
        original = PromptVersion(
            id=generate_prompt_id(),
            name="unicode_test",
            version=1,
            template=PromptTemplate(content="こんにちは {{name}}! 你好! مرحبا!"),
        )
        mlflow_store.save(original)

        loaded = mlflow_store.load(original.id)
        assert loaded.content == original.content


class TestListOperations:
    """Tests for listing prompts and versions."""

    def test_list_prompts_empty(self, mlflow_store: MLflowPromptStore):
        """List prompts when none exist."""
        prompts = mlflow_store.list_prompts()
        assert prompts == []

    def test_list_prompts(self, mlflow_store: MLflowPromptStore):
        """List all prompt names."""
        names = ["alpha", "beta", "gamma"]
        for name in names:
            prompt = PromptVersion(
                id=generate_prompt_id(),
                name=name,
                version=1,
                template=PromptTemplate(content=f"{name} content"),
            )
            mlflow_store.save(prompt)

        listed = mlflow_store.list_prompts()
        assert set(listed) == set(names)

    def test_list_versions(self, mlflow_store: MLflowPromptStore):
        """List all versions of a prompt."""
        ids = []
        for i in range(1, 5):
            prompt = PromptVersion(
                id=generate_prompt_id(),
                name="versioned_prompt",
                version=i,
                template=PromptTemplate(content=f"Version {i}"),
            )
            ids.append(prompt.id)
            mlflow_store.save(prompt)

        versions = mlflow_store.list_versions("versioned_prompt")
        assert len(versions) == 4
        version_nums = [v.version for v in versions]
        assert sorted(version_nums) == [1, 2, 3, 4]

    def test_list_versions_nonexistent(self, mlflow_store: MLflowPromptStore):
        """List versions for non-existent prompt."""
        versions = mlflow_store.list_versions("nonexistent")
        assert versions == []

    def test_list_snapshots(self, mlflow_store: MLflowPromptStore):
        """List snapshots for a prompt."""
        # Create regular version
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="snapshot_list_test",
            version=1,
            template=PromptTemplate(content="Base"),
        )
        mlflow_store.save(prompt)

        # Create snapshots
        for i, snap_name in enumerate(["prod-v1", "staging", "release-1.0"], start=2):
            snap = PromptVersion(
                id=generate_prompt_id(),
                name="snapshot_list_test",
                version=i,
                template=PromptTemplate(content=f"Snapshot {i}"),
                status=PromptStatus.SNAPSHOT,
                snapshot_name=snap_name,
            )
            mlflow_store.save(snap)

        snapshots = mlflow_store.list_snapshots("snapshot_list_test")
        snap_names = [s[0] for s in snapshots]
        assert "prod-v1" in snap_names
        assert "staging" in snap_names
        assert "release-1.0" in snap_names


class TestSearch:
    """Tests for search functionality."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, mlflow_store: MLflowPromptStore):
        """Create test data for search tests."""
        prompts = [
            ("greeting_formal", "draft", "alice", ["greeting", "formal"]),
            ("greeting_casual", "active", "alice", ["greeting", "casual"]),
            ("summary_short", "active", "bob", ["nlp", "summary"]),
            ("summary_long", "archived", "bob", ["nlp", "summary"]),
            ("analysis_sentiment", "draft", "carol", ["nlp", "analysis"]),
        ]

        for name, status, author, tags in prompts:
            prompt = PromptVersion(
                id=generate_prompt_id(),
                name=name,
                version=1,
                template=PromptTemplate(content=f"{name} content"),
                status=PromptStatus(status),
                metadata=PromptMetadata(author=author, tags=tags),
            )
            mlflow_store.save(prompt)

    def test_search_by_status(self, mlflow_store: MLflowPromptStore):
        """Search by status."""
        results = mlflow_store.search(status=PromptStatus.ACTIVE)
        names = [r.name for r in results]
        assert "greeting_casual" in names
        assert "summary_short" in names
        assert "greeting_formal" not in names

    def test_search_by_author(self, mlflow_store: MLflowPromptStore):
        """Search by author."""
        results = mlflow_store.search(author="bob")
        names = [r.name for r in results]
        assert "summary_short" in names
        assert "summary_long" in names
        assert "greeting_formal" not in names

    def test_search_by_tags(self, mlflow_store: MLflowPromptStore):
        """Search by tags."""
        results = mlflow_store.search(tags=["nlp"])
        names = [r.name for r in results]
        assert "summary_short" in names
        assert "summary_long" in names
        assert "analysis_sentiment" in names
        assert "greeting_formal" not in names

    def test_search_by_multiple_tags(self, mlflow_store: MLflowPromptStore):
        """Search requiring multiple tags."""
        results = mlflow_store.search(tags=["nlp", "summary"])
        names = [r.name for r in results]
        assert "summary_short" in names
        assert "summary_long" in names
        assert "analysis_sentiment" not in names

    def test_search_by_name_pattern(self, mlflow_store: MLflowPromptStore):
        """Search by name pattern."""
        results = mlflow_store.search(name_pattern="greeting")
        names = [r.name for r in results]
        assert "greeting_formal" in names
        assert "greeting_casual" in names
        assert "summary_short" not in names

    def test_search_combined_filters(self, mlflow_store: MLflowPromptStore):
        """Search with multiple filters."""
        results = mlflow_store.search(
            status=PromptStatus.ACTIVE,
            author="alice",
        )
        names = [r.name for r in results]
        assert "greeting_casual" in names
        assert len(names) == 1

    def test_search_no_results(self, mlflow_store: MLflowPromptStore):
        """Search with no matching results."""
        results = mlflow_store.search(author="nonexistent")
        assert results == []


class TestDelete:
    """Tests for deletion."""

    def test_delete_existing(self, mlflow_store: MLflowPromptStore):
        """Delete existing prompt."""
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="delete_test",
            version=1,
            template=PromptTemplate(content="To be deleted"),
        )
        mlflow_store.save(prompt)

        # Verify exists
        assert mlflow_store.load(prompt.id) is not None

        # Delete
        result = mlflow_store.delete(prompt.id)
        assert result is True

        # Verify gone
        assert mlflow_store.load(prompt.id) is None

    def test_delete_nonexistent(self, mlflow_store: MLflowPromptStore):
        """Delete non-existent prompt returns False."""
        result = mlflow_store.delete("nonexistent_id")
        assert result is False


class TestVersioning:
    """Tests for version number management."""

    def test_get_next_version_new_prompt(self, mlflow_store: MLflowPromptStore):
        """Next version for new prompt is 1."""
        next_ver = mlflow_store.get_next_version("brand_new_prompt")
        assert next_ver == 1

    def test_get_next_version_existing(self, mlflow_store: MLflowPromptStore):
        """Next version increments from latest."""
        for i in range(1, 4):
            prompt = PromptVersion(
                id=generate_prompt_id(),
                name="version_counter",
                version=i,
                template=PromptTemplate(content=f"v{i}"),
            )
            mlflow_store.save(prompt)

        next_ver = mlflow_store.get_next_version("version_counter")
        assert next_ver == 4


class TestLineage:
    """Tests for lineage tracking."""

    def test_get_lineage(self, mlflow_store: MLflowPromptStore):
        """Get full lineage for a prompt."""
        parent_id = None
        for i in range(1, 4):
            prompt = PromptVersion(
                id=generate_prompt_id(),
                name="lineage_test",
                version=i,
                template=PromptTemplate(content=f"v{i}"),
                parent_id=parent_id,
            )
            mlflow_store.save(prompt)
            parent_id = prompt.id

        lineage = mlflow_store.get_lineage("lineage_test")
        assert lineage.name == "lineage_test"
        assert len(lineage.versions) == 3

    def test_get_lineage_nonexistent(self, mlflow_store: MLflowPromptStore):
        """Get lineage for non-existent prompt raises error."""
        with pytest.raises(ValueError):
            mlflow_store.get_lineage("nonexistent")


class TestCompare:
    """Tests for version comparison."""

    def test_compare_versions(self, mlflow_store: MLflowPromptStore):
        """Compare two versions."""
        p1 = PromptVersion(
            id=generate_prompt_id(),
            name="compare_test",
            version=1,
            template=PromptTemplate(content="Hello {{name}}!"),
        )
        p2 = PromptVersion(
            id=generate_prompt_id(),
            name="compare_test",
            version=2,
            template=PromptTemplate(content="Hi {{name}}, welcome to {{place}}!"),
            parent_id=p1.id,
        )
        mlflow_store.save(p1)
        mlflow_store.save(p2)

        diff = mlflow_store.compare(p1.id, p2.id)
        assert diff.content_changed is True
        assert "place" in diff.variables_added

    def test_compare_nonexistent(self, mlflow_store: MLflowPromptStore):
        """Compare with non-existent ID raises error."""
        prompt = PromptVersion(
            id=generate_prompt_id(),
            name="compare_error_test",
            version=1,
            template=PromptTemplate(content="Test"),
        )
        mlflow_store.save(prompt)

        with pytest.raises(ValueError):
            mlflow_store.compare(prompt.id, "nonexistent")
