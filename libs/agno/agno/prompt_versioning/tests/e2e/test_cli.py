"""
End-to-end tests for CLI commands.

Tests cover all CLI commands with real execution.
Uses Typer's CliRunner for testing.
"""

import json
import os
import tempfile

import pytest
from typer.testing import CliRunner

from agno.prompt_versioning import cli
from agno.prompt_versioning.cli import app

runner = CliRunner()


@pytest.fixture
def cli_env():
    """Create temporary MLflow directory for CLI tests."""
    # Reset global manager to avoid state leakage between tests
    cli._manager = None

    with tempfile.TemporaryDirectory(prefix="cli_test_") as tmpdir:
        tracking_uri = os.path.join(tmpdir, "mlruns")
        yield {"tracking_uri": tracking_uri, "tmpdir": tmpdir}

    # Clean up after test
    cli._manager = None


class TestCreateCommand:
    """Tests for 'create' command."""

    def test_create_basic(self, cli_env):
        """Create prompt with minimum args."""
        result = runner.invoke(
            app,
            [
                "create",
                "test_prompt",
                "Hello {{name}}!",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Created prompt" in result.stdout
        assert "test_prompt" in result.stdout
        assert "v1" in result.stdout

    def test_create_with_options(self, cli_env):
        """Create prompt with all options."""
        result = runner.invoke(
            app,
            [
                "create",
                "full_prompt",
                "Content {{var}}",
                "-d",
                "Test description",
                "-a",
                "test-author",
                "-t",
                "tag1,tag2",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Created prompt" in result.stdout

    def test_create_shows_variables(self, cli_env):
        """Create shows extracted variables."""
        result = runner.invoke(
            app,
            [
                "create",
                "var_prompt",
                "{{a}} {{b}} {{c}}",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Variables:" in result.stdout


class TestEditCommand:
    """Tests for 'edit' command."""

    def test_edit_content(self, cli_env):
        """Edit prompt content."""
        # First create
        runner.invoke(
            app,
            ["create", "edit_test", "Original", "-u", cli_env["tracking_uri"]],
        )

        # Then edit
        result = runner.invoke(
            app,
            [
                "edit",
                "edit_test",
                "-c",
                "Modified content",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Updated prompt" in result.stdout
        assert "v2" in result.stdout

    def test_edit_nonexistent(self, cli_env):
        """Edit non-existent prompt fails."""
        result = runner.invoke(
            app,
            [
                "edit",
                "nonexistent",
                "-c",
                "New",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestSnapshotCommand:
    """Tests for 'snapshot' command."""

    def test_snapshot_basic(self, cli_env):
        """Create snapshot."""
        # Create prompt
        runner.invoke(
            app,
            ["create", "snap_test", "Content", "-u", cli_env["tracking_uri"]],
        )

        # Snapshot
        result = runner.invoke(
            app,
            [
                "snapshot",
                "snap_test",
                "prod-v1",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Created snapshot" in result.stdout
        assert "prod-v1" in result.stdout

    def test_snapshot_with_description(self, cli_env):
        """Snapshot with description."""
        runner.invoke(
            app,
            ["create", "snap_desc", "Content", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            [
                "snapshot",
                "snap_desc",
                "release",
                "-d",
                "Release notes",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0


class TestForkCommand:
    """Tests for 'fork' command."""

    def test_fork_basic(self, cli_env):
        """Fork prompt."""
        runner.invoke(
            app,
            ["create", "fork_source", "Content", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            [
                "fork",
                "fork_source",
                "fork_target",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Created fork" in result.stdout
        assert "fork_target" in result.stdout

    def test_fork_with_options(self, cli_env):
        """Fork with description and author."""
        runner.invoke(
            app,
            ["create", "fork_opts", "Content", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            [
                "fork",
                "fork_opts",
                "fork_opts_copy",
                "-d",
                "Fork description",
                "-a",
                "new-author",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0


class TestListCommand:
    """Tests for 'list' command."""

    def test_list_empty(self, cli_env):
        """List with no prompts."""
        result = runner.invoke(
            app,
            ["list", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0
        assert "No prompts found" in result.stdout

    def test_list_prompts(self, cli_env):
        """List existing prompts."""
        # Create some prompts
        runner.invoke(
            app,
            ["create", "alpha", "Content", "-u", cli_env["tracking_uri"]],
        )
        runner.invoke(
            app,
            ["create", "beta", "Content", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            ["list", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0
        assert "alpha" in result.stdout
        assert "beta" in result.stdout


class TestVersionsCommand:
    """Tests for 'versions' command."""

    def test_versions(self, cli_env):
        """List versions of a prompt."""
        # Create and edit
        runner.invoke(
            app,
            ["create", "ver_test", "v1", "-u", cli_env["tracking_uri"]],
        )
        runner.invoke(
            app,
            ["edit", "ver_test", "-c", "v2", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            ["versions", "ver_test", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0
        assert "v1" in result.stdout
        assert "v2" in result.stdout

    def test_versions_nonexistent(self, cli_env):
        """Versions for non-existent prompt."""
        result = runner.invoke(
            app,
            ["versions", "nonexistent", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 1


class TestShowCommand:
    """Tests for 'show' command."""

    def test_show_basic(self, cli_env):
        """Show prompt details."""
        runner.invoke(
            app,
            [
                "create",
                "show_test",
                "Hello {{name}}!",
                "-d",
                "Test description",
                "-t",
                "tag1,tag2",
                "-u",
                cli_env["tracking_uri"],
            ],
        )

        result = runner.invoke(
            app,
            ["show", "show_test", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0
        assert "show_test" in result.stdout
        assert "Hello {{name}}!" in result.stdout
        assert "name" in result.stdout  # Variables
        assert "Test description" in result.stdout

    def test_show_specific_version(self, cli_env):
        """Show specific version."""
        runner.invoke(
            app,
            ["create", "show_ver", "v1 content", "-u", cli_env["tracking_uri"]],
        )
        runner.invoke(
            app,
            ["edit", "show_ver", "-c", "v2 content", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            ["show", "show_ver", "-v", "1", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0
        assert "v1 content" in result.stdout


class TestRenderCommand:
    """Tests for 'render' command."""

    def test_render_basic(self, cli_env):
        """Render with variables."""
        runner.invoke(
            app,
            [
                "create",
                "render_test",
                "Hello {{name}}!",
                "-u",
                cli_env["tracking_uri"],
            ],
        )

        result = runner.invoke(
            app,
            [
                "render",
                "render_test",
                "-V",
                "name=Alice",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Hello Alice!" in result.stdout

    def test_render_multiple_vars(self, cli_env):
        """Render with multiple variables."""
        runner.invoke(
            app,
            [
                "create",
                "render_multi",
                "{{a}} {{b}} {{c}}",
                "-u",
                cli_env["tracking_uri"],
            ],
        )

        result = runner.invoke(
            app,
            [
                "render",
                "render_multi",
                "-V",
                "a=A",
                "-V",
                "b=B",
                "-V",
                "c=C",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "A B C" in result.stdout

    def test_render_from_snapshot(self, cli_env):
        """Render from snapshot."""
        runner.invoke(
            app,
            [
                "create",
                "render_snap",
                "Snapshot: {{x}}",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        runner.invoke(
            app,
            [
                "snapshot",
                "render_snap",
                "v1",
                "-u",
                cli_env["tracking_uri"],
            ],
        )

        result = runner.invoke(
            app,
            [
                "render",
                "render_snap",
                "-s",
                "v1",
                "-V",
                "x=value",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0
        assert "Snapshot: value" in result.stdout

    def test_render_missing_var(self, cli_env):
        """Render with missing variable fails."""
        runner.invoke(
            app,
            [
                "create",
                "render_missing",
                "{{a}} {{b}}",
                "-u",
                cli_env["tracking_uri"],
            ],
        )

        result = runner.invoke(
            app,
            [
                "render",
                "render_missing",
                "-V",
                "a=A",
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 1
        assert "Error" in result.stdout


class TestCompareCommand:
    """Tests for 'compare' command."""

    def test_compare_versions(self, cli_env):
        """Compare two versions."""
        runner.invoke(
            app,
            ["create", "compare_test", "Version 1", "-u", cli_env["tracking_uri"]],
        )
        runner.invoke(
            app,
            ["edit", "compare_test", "-c", "Version 2", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            ["compare", "compare_test", "1", "2", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0
        assert "Content changed" in result.stdout
        assert "Version 1" in result.stdout
        assert "Version 2" in result.stdout


class TestExportCommand:
    """Tests for 'export' command."""

    def test_export_stdout(self, cli_env):
        """Export to stdout."""
        runner.invoke(
            app,
            ["create", "export_test", "Content", "-u", cli_env["tracking_uri"]],
        )

        result = runner.invoke(
            app,
            ["export", "export_test", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0

        # Verify valid JSON
        data = json.loads(result.stdout)
        assert data["name"] == "export_test"
        assert len(data["versions"]) == 1

    def test_export_to_file(self, cli_env):
        """Export to file."""
        runner.invoke(
            app,
            ["create", "export_file", "Content", "-u", cli_env["tracking_uri"]],
        )

        output_file = os.path.join(cli_env["tmpdir"], "export.json")
        result = runner.invoke(
            app,
            [
                "export",
                "export_file",
                "-o",
                output_file,
                "-u",
                cli_env["tracking_uri"],
            ],
        )
        assert result.exit_code == 0

        # Verify file created
        assert os.path.exists(output_file)
        with open(output_file) as f:
            data = json.load(f)
        assert data["name"] == "export_file"


class TestDeleteCommand:
    """Tests for 'delete' command."""

    def test_delete_with_force(self, cli_env):
        """Delete with force flag."""
        result = runner.invoke(
            app,
            ["create", "delete_test", "Content", "-u", cli_env["tracking_uri"]],
        )
        # Extract prompt ID from output
        # Output like "ID: prompt_abc123"
        import re

        match = re.search(r"ID: (prompt_\w+)", result.stdout)
        assert match
        prompt_id = match.group(1)

        result = runner.invoke(
            app,
            ["delete", prompt_id, "-f", "-u", cli_env["tracking_uri"]],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.stdout


class TestCLIWorkflow:
    """Test complete CLI workflow."""

    def test_full_workflow(self, cli_env):
        """Complete workflow using CLI only."""
        uri = cli_env["tracking_uri"]

        # 1. Create
        result = runner.invoke(
            app,
            [
                "create",
                "workflow",
                "Hello {{name}}!",
                "-d",
                "Workflow test",
                "-t",
                "test",
                "-u",
                uri,
            ],
        )
        assert result.exit_code == 0

        # 2. Edit
        result = runner.invoke(
            app,
            ["edit", "workflow", "-c", "Hi {{name}}, welcome!", "-u", uri],
        )
        assert result.exit_code == 0

        # 3. Snapshot
        result = runner.invoke(
            app,
            ["snapshot", "workflow", "prod-v1", "-u", uri],
        )
        assert result.exit_code == 0

        # 4. Fork
        result = runner.invoke(
            app,
            ["fork", "workflow", "workflow_exp", "-u", uri],
        )
        assert result.exit_code == 0

        # 5. List
        result = runner.invoke(app, ["list", "-u", uri])
        assert "workflow" in result.stdout
        assert "workflow_exp" in result.stdout

        # 6. Versions
        result = runner.invoke(app, ["versions", "workflow", "-u", uri])
        assert "v1" in result.stdout
        assert "v2" in result.stdout
        assert "v3" in result.stdout  # snapshot

        # 7. Render
        result = runner.invoke(
            app,
            ["render", "workflow", "-s", "prod-v1", "-V", "name=Test", "-u", uri],
        )
        assert "Hi Test, welcome!" in result.stdout

        # 8. Export
        result = runner.invoke(app, ["export", "workflow", "-u", uri])
        data = json.loads(result.stdout)
        assert len(data["versions"]) == 3
        assert "prod-v1" in data["snapshots"]
