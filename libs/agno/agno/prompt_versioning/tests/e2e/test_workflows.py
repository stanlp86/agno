"""
End-to-end workflow tests.

These tests simulate complete user scenarios:
1. Development workflow: create → iterate → snapshot → deploy
2. Experimentation workflow: fork → experiment → merge back
3. Team collaboration workflow: multiple authors, reviews, releases
4. Production workflow: snapshots, rollback, audit trail
5. Migration workflow: export → import → verify
"""

import json
import tempfile

import pytest

from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.models import PromptStatus


class TestDevelopmentWorkflow:
    """
    Simulates a typical development workflow:
    1. Create initial prompt
    2. Iterate with multiple edits
    3. Test renders at each stage
    4. Create production snapshot
    5. Continue development
    6. Create new release
    """

    def test_full_development_cycle(self, manager: PromptManager, assertions):
        """Complete development cycle from creation to release."""
        # 1. Create initial prompt
        v1 = manager.create(
            name="customer_greeting",
            content="Hello {{customer_name}}!",
            description="Initial greeting prompt",
            author="dev-team",
            tags=["greeting", "customer"],
        )
        assertions.assert_valid_id(v1)
        assert v1.version == 1
        assert v1.status == PromptStatus.DRAFT

        # 2. First iteration - add company name
        v2 = manager.edit(
            v1.id,
            content="Hello {{customer_name}}, welcome to {{company}}!",
        )
        assert v2.version == 2
        assert v2.parent_id == v1.id
        assert v2.variables == {"customer_name", "company"}

        # 3. Second iteration - add personalization
        v3 = manager.edit(
            v2.id,
            content="Hello {{customer_name}}, welcome to {{company}}! "
            "We're excited to have you join us.",
        )
        assert v3.version == 3

        # 4. Test rendering
        rendered = manager.render(
            prompt_name="customer_greeting",
            customer_name="Alice",
            company="Acme Corp",
        )
        assert "Alice" in rendered
        assert "Acme Corp" in rendered

        # 5. Ready for production - create snapshot
        prod_v1 = manager.snapshot(
            v3.id,
            "prod-v1",
            description="First production release",
        )
        assert prod_v1.is_snapshot()
        assert prod_v1.snapshot_name == "prod-v1"

        # 6. Continue development
        v4 = manager.edit(
            v3.id,
            content="Hi {{customer_name}}! Welcome to {{company}}. "
            "Your journey starts here.",
        )
        assert v4.version == 5  # After snapshot

        # 7. Verify production snapshot unchanged
        loaded_prod = manager.get_snapshot("customer_greeting", "prod-v1")
        assert loaded_prod.content == v3.content

        # 8. New release
        prod_v2 = manager.snapshot(v4.id, "prod-v2")
        assert prod_v2.snapshot_name == "prod-v2"

        # 9. Verify full lineage
        lineage = manager.get_lineage("customer_greeting")
        assert len(lineage.versions) == 6  # v1, v2, v3, snap1, v4, snap2
        assert len(lineage.snapshots) == 2


class TestExperimentationWorkflow:
    """
    Simulates experimentation with forking:
    1. Have production prompt
    2. Fork for experiment A
    3. Fork for experiment B
    4. Iterate on experiments
    5. Choose winner
    6. Apply learnings to main prompt
    """

    def test_ab_testing_with_forks(self, manager: PromptManager):
        """A/B testing via forking."""
        # 1. Production prompt
        main = manager.create(
            name="email_subject",
            content="Your order {{order_id}} has shipped!",
            author="marketing",
            tags=["email", "notification"],
        )
        manager.snapshot(main.id, "baseline")

        # 2. Fork for experiment A - urgency
        exp_a_v1 = manager.fork(
            main.id,
            "email_subject_exp_a",
            description="Experiment A: Add urgency",
        )
        exp_a = manager.edit(
            exp_a_v1.id,
            content="🚀 Your order {{order_id}} is on its way!",
        )

        # 3. Fork for experiment B - personalization
        exp_b_v1 = manager.fork(
            main.id,
            "email_subject_exp_b",
            description="Experiment B: Personalization",
        )
        exp_b = manager.edit(
            exp_b_v1.id,
            content="{{customer_name}}, order {{order_id}} shipped!",
        )

        # 4. Verify forks are independent (check v1 for fork origin)
        assert exp_a.name != exp_b.name
        assert exp_a_v1.forked_from == main.id  # v1 has forked_from
        assert exp_b_v1.forked_from == main.id

        # 5. Both forks can be rendered
        render_a = manager.render(prompt_name="email_subject_exp_a", order_id="12345")
        render_b = manager.render(
            prompt_name="email_subject_exp_b",
            customer_name="Alice",
            order_id="12345",
        )
        assert "12345" in render_a
        assert "Alice" in render_b

        # 6. Experiment B wins - apply to main
        main_v2 = manager.edit(
            main.id,
            content="{{customer_name}}, order {{order_id}} shipped!",
        )
        manager.snapshot(main_v2.id, "v2-personalized")

        # 7. Verify all prompts coexist
        all_prompts = manager.list_prompts()
        assert "email_subject" in all_prompts
        assert "email_subject_exp_a" in all_prompts
        assert "email_subject_exp_b" in all_prompts


class TestTeamCollaborationWorkflow:
    """
    Simulates team collaboration:
    1. Alice creates initial prompt
    2. Bob reviews and suggests changes
    3. Carol approves for staging
    4. Dave creates production release
    5. Full audit trail maintained
    """

    def test_team_handoff(self, manager: PromptManager):
        """Multi-person workflow with handoffs."""
        # 1. Alice creates
        v1 = manager.create(
            name="support_response",
            content="Thank you for contacting support. "
            "Your ticket {{ticket_id}} has been received.",
            author="alice",
            description="Initial support response template",
            tags=["support", "response"],
        )

        # 2. Bob reviews and edits
        v2 = manager.edit(
            v1.id,
            content="Hi {{customer_name}},\n\n"
            "Thank you for contacting support. "
            "Your ticket #{{ticket_id}} has been received.\n\n"
            "We'll respond within 24 hours.\n\nBest,\nSupport Team",
            author="bob",
            description="Added customer name, formatting, SLA",
        )

        # 3. Carol approves for staging
        staging = manager.snapshot(
            v2.id,
            "staging-review",
            description="Approved by Carol for staging",
        )

        # 4. After testing, Dave releases to production
        # Small tweak first
        v3 = manager.edit(
            v2.id,
            content="Hi {{customer_name}},\n\n"
            "Thank you for reaching out! "
            "Your ticket #{{ticket_id}} has been received.\n\n"
            "We'll respond within 24 hours.\n\nBest,\nThe Support Team",
            author="dave",
        )
        prod = manager.snapshot(
            v3.id,
            "prod-v1",
            description="Production release by Dave",
        )

        # 5. Verify audit trail via lineage
        lineage = manager.get_lineage("support_response")

        # Check we can trace who did what
        authors = set()
        for version in lineage.versions:
            if version.metadata.author:
                authors.add(version.metadata.author)

        assert "alice" in authors
        assert "bob" in authors
        assert "dave" in authors

        # Verify snapshots
        assert "staging-review" in lineage.snapshots
        assert "prod-v1" in lineage.snapshots


class TestProductionWorkflow:
    """
    Simulates production operations:
    1. Multiple versioned releases
    2. Rollback capability
    3. Render from specific snapshot
    4. Audit and compliance
    """

    def test_release_and_rollback(self, manager: PromptManager):
        """Release management with rollback."""
        # Setup: Create and release multiple versions
        prompt = manager.create(
            name="checkout_message",
            content="Complete your purchase of {{item}}.",
            author="ecommerce-team",
        )

        # Release 1.0
        manager.snapshot(prompt.id, "release-1.0")

        # Development and Release 1.1
        v2 = manager.edit(
            prompt.id,
            content="Complete your purchase of {{item}}. "
            "Free shipping on orders over $50!",
        )
        manager.snapshot(v2.id, "release-1.1")

        # Development and Release 1.2 (has a bug!)
        v3 = manager.edit(
            v2.id,
            content="Complete your purchase of {{item}}. "
            "Free shipping on orders over ${{threshold}}!",  # Added variable
        )
        manager.snapshot(v3.id, "release-1.2")

        # PRODUCTION ISSUE: release-1.2 requires new variable
        # Rollback to 1.1
        release_1_1 = manager.get_snapshot("checkout_message", "release-1.1")
        release_1_2 = manager.get_snapshot("checkout_message", "release-1.2")

        # Render works with 1.1
        result_1_1 = manager.render(
            prompt_name="checkout_message",
            snapshot_name="release-1.1",
            item="Widget",
        )
        assert "Widget" in result_1_1
        assert "$50" in result_1_1

        # Render fails with 1.2 if threshold missing
        with pytest.raises(ValueError, match="Missing"):
            manager.render(
                prompt_name="checkout_message",
                snapshot_name="release-1.2",
                item="Widget",
            )

        # Compare to understand what changed
        diff = manager.compare(release_1_1.id, release_1_2.id)
        assert "threshold" in diff.variables_added


class TestMigrationWorkflow:
    """
    Simulates migration/backup:
    1. Export full lineage
    2. Verify export completeness
    3. Create new manager (simulating new environment)
    4. Reconstruct from export
    5. Verify integrity
    """

    def test_export_and_verify(self, manager: PromptManager):
        """Export lineage and verify completeness."""
        # Setup: Create rich history
        v1 = manager.create(
            name="migration_test",
            content="Version 1: {{x}}",
            author="original-author",
            tags=["important", "test"],
            custom_metadata={"env": "production"},
        )
        v2 = manager.edit(v1.id, content="Version 2: {{x}} {{y}}")
        snap = manager.snapshot(v2.id, "backup-point")
        v3 = manager.edit(v2.id, content="Version 3: {{x}} {{y}} {{z}}")

        # Export
        export_data = manager.export_lineage("migration_test")

        # Verify export structure
        assert export_data["name"] == "migration_test"
        assert export_data["root_id"] == v1.id
        assert len(export_data["versions"]) == 4  # v1, v2, snap, v3
        assert "backup-point" in export_data["snapshots"]

        # Verify version data
        v1_export = next(v for v in export_data["versions"] if v["version"] == 1)
        assert v1_export["content"] == "Version 1: {{x}}"
        assert v1_export["metadata"]["author"] == "original-author"
        assert v1_export["metadata"]["tags"] == ["important", "test"]

        # Save to file (simulating backup)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(export_data, f, indent=2)
            backup_file = f.name

        # Load and verify
        with open(backup_file, "r") as f:
            restored_data = json.load(f)

        assert restored_data == export_data


class TestComplexScenarios:
    """Tests for complex edge cases and scenarios."""

    def test_deep_edit_chain(self, manager: PromptManager, assertions):
        """Very long edit chain maintains integrity."""
        prompt = manager.create(name="deep_chain", content="v1")

        prev_id = prompt.id
        for i in range(2, 21):  # Create 20 versions
            prompt = manager.edit(prev_id, content=f"v{i}")
            assert prompt.version == i
            assert prompt.parent_id == prev_id
            prev_id = prompt.id

        # Verify chain integrity
        versions = manager.list_versions("deep_chain")
        assert len(versions) == 20
        assertions.assert_lineage_chain(sorted(versions, key=lambda x: x.version))

    def test_multiple_snapshots_same_content(self, manager: PromptManager):
        """Multiple snapshots can have same content."""
        v1 = manager.create(name="multi_snap", content="Stable content")

        snap1 = manager.snapshot(v1.id, "prod")
        snap2 = manager.snapshot(v1.id, "staging")
        snap3 = manager.snapshot(v1.id, "qa")

        # All snapshots exist
        assert manager.get_snapshot("multi_snap", "prod") is not None
        assert manager.get_snapshot("multi_snap", "staging") is not None
        assert manager.get_snapshot("multi_snap", "qa") is not None

        # All have same content hash
        assert snap1.content_hash == snap2.content_hash == snap3.content_hash

    def test_fork_then_snapshot(self, manager: PromptManager):
        """Fork, develop, and snapshot the fork."""
        original = manager.create(name="fork_snap_orig", content="Original")
        forked = manager.fork(original.id, "fork_snap_fork")

        # Develop fork
        v2 = manager.edit(forked.id, content="Forked v2")
        v3 = manager.edit(v2.id, content="Forked v3")

        # Snapshot fork
        snap = manager.snapshot(v3.id, "fork-release")

        # Verify
        assert snap.is_snapshot()
        loaded = manager.get_snapshot("fork_snap_fork", "fork-release")
        assert loaded is not None
        assert loaded.content == "Forked v3"

    def test_search_across_many_prompts(self, manager: PromptManager):
        """Search works efficiently across many prompts."""
        # Create many prompts
        for i in range(20):
            tags = ["batch"]
            if i % 2 == 0:
                tags.append("even")
            if i % 5 == 0:
                tags.append("five")

            manager.create(
                name=f"batch_prompt_{i}",
                content=f"Content {i}",
                tags=tags,
                author="batch-author" if i < 10 else "other-author",
            )

        # Search tests
        all_batch = manager.search(tags=["batch"])
        assert len(all_batch) == 20

        evens = manager.search(tags=["even"])
        assert len(evens) == 10

        fives = manager.search(tags=["five"])
        assert len(fives) == 4  # 0, 5, 10, 15

        by_author = manager.search(author="batch-author")
        assert len(by_author) == 10

    def test_render_preserves_formatting(self, manager: PromptManager):
        """Render preserves newlines, tabs, special chars."""
        content = """Dear {{name}},

\tThank you for your inquiry.

Key points:
- Item 1
- Item 2

Special chars: @#$%^&*()

Best regards,
{{sender}}"""

        manager.create(name="formatting_test", content=content)
        result = manager.render(
            prompt_name="formatting_test",
            name="Alice",
            sender="Bob",
        )

        assert "Dear Alice," in result
        assert "\t" in result  # Tab preserved
        assert "- Item 1" in result
        assert "@#$%^&*()" in result
        assert "Bob" in result
