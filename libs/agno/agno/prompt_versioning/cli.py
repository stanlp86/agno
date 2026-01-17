"""
CLI for prompt versioning operations.

Usage:
    python -m agno.prompt_versioning.cli create my_prompt "Hello, {{name}}!"
    python -m agno.prompt_versioning.cli edit my_prompt --content "Hi {{name}}!"
    python -m agno.prompt_versioning.cli snapshot my_prompt production-v1
    python -m agno.prompt_versioning.cli fork my_prompt my_prompt_v2
    python -m agno.prompt_versioning.cli list
    python -m agno.prompt_versioning.cli versions my_prompt
    python -m agno.prompt_versioning.cli render my_prompt --var name=Alice
"""

import json
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from agno.prompt_versioning.manager import PromptManager
from agno.prompt_versioning.models import PromptStatus

app = typer.Typer(
    name="prompt-versioning",
    help="MLflow-backed prompt versioning CLI",
)
console = Console()

# Default manager - can be overridden
_manager: Optional[PromptManager] = None


def get_manager(tracking_uri: str = "mlruns") -> PromptManager:
    """Get or create the prompt manager."""
    global _manager
    if _manager is None:
        _manager = PromptManager(tracking_uri=tracking_uri)
    return _manager


@app.command()
def create(
    name: str = typer.Argument(..., help="Prompt name"),
    content: str = typer.Argument(..., help="Prompt content"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    author: Optional[str] = typer.Option(None, "--author", "-a"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Create a new prompt."""
    manager = get_manager(tracking_uri)
    tag_list = tags.split(",") if tags else None

    prompt = manager.create(
        name=name,
        content=content,
        description=description,
        author=author,
        tags=tag_list,
    )

    console.print(f"[green]Created prompt:[/green] {prompt.name} (v{prompt.version})")
    console.print(f"[dim]ID: {prompt.id}[/dim]")
    if prompt.variables:
        console.print(f"[dim]Variables: {', '.join(prompt.variables)}[/dim]")


@app.command()
def edit(
    name: str = typer.Argument(..., help="Prompt name"),
    content: Optional[str] = typer.Option(None, "--content", "-c"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    author: Optional[str] = typer.Option(None, "--author", "-a"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    version: Optional[int] = typer.Option(None, "--version", "-v", help="Version to edit (latest if not specified)"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Edit a prompt (creates new version)."""
    manager = get_manager(tracking_uri)

    prompt = manager.get_by_name(name, version)
    if prompt is None:
        console.print(f"[red]Prompt not found: {name}[/red]")
        raise typer.Exit(1)

    tag_list = tags.split(",") if tags else None

    updated = manager.edit(
        prompt.id,
        content=content,
        description=description,
        author=author,
        tags=tag_list,
    )

    console.print(f"[green]Updated prompt:[/green] {updated.name} (v{updated.version})")
    console.print(f"[dim]ID: {updated.id}[/dim]")
    console.print(f"[dim]Previous: v{prompt.version} ({prompt.id})[/dim]")


@app.command()
def snapshot(
    name: str = typer.Argument(..., help="Prompt name"),
    snapshot_name: str = typer.Argument(..., help="Snapshot name"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    version: Optional[int] = typer.Option(None, "--version", "-v", help="Version to snapshot (latest if not specified)"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Create a named snapshot of a prompt."""
    manager = get_manager(tracking_uri)

    prompt = manager.get_by_name(name, version)
    if prompt is None:
        console.print(f"[red]Prompt not found: {name}[/red]")
        raise typer.Exit(1)

    snap = manager.snapshot(prompt.id, snapshot_name, description)

    console.print(f"[green]Created snapshot:[/green] {snap.name}@{snapshot_name}")
    console.print(f"[dim]ID: {snap.id}[/dim]")
    console.print(f"[dim]From: v{prompt.version} ({prompt.id})[/dim]")


@app.command()
def fork(
    name: str = typer.Argument(..., help="Source prompt name"),
    new_name: str = typer.Argument(..., help="New prompt name"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    author: Optional[str] = typer.Option(None, "--author", "-a"),
    version: Optional[int] = typer.Option(None, "--version", "-v", help="Version to fork (latest if not specified)"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Fork a prompt to create a new independent prompt."""
    manager = get_manager(tracking_uri)

    prompt = manager.get_by_name(name, version)
    if prompt is None:
        console.print(f"[red]Prompt not found: {name}[/red]")
        raise typer.Exit(1)

    forked = manager.fork(prompt.id, new_name, description, author)

    console.print(f"[green]Created fork:[/green] {forked.name} (v{forked.version})")
    console.print(f"[dim]ID: {forked.id}[/dim]")
    console.print(f"[dim]Forked from: {name} v{prompt.version} ({prompt.id})[/dim]")


@app.command("list")
def list_prompts(
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """List all prompts."""
    manager = get_manager(tracking_uri)
    prompts = manager.list_prompts()

    if not prompts:
        console.print("[dim]No prompts found[/dim]")
        return

    table = Table(title="Prompts")
    table.add_column("Name", style="cyan")
    table.add_column("Latest Version", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Snapshots", style="magenta")

    for name in prompts:
        latest = manager.get_by_name(name)
        snapshots = manager.list_snapshots(name)
        snapshot_names = [s[0] for s in snapshots]

        if latest:
            table.add_row(
                name,
                f"v{latest.version}",
                latest.status.value,
                ", ".join(snapshot_names) or "-",
            )

    console.print(table)


@app.command()
def versions(
    name: str = typer.Argument(..., help="Prompt name"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """List all versions of a prompt."""
    manager = get_manager(tracking_uri)
    vers = manager.list_versions(name)

    if not vers:
        console.print(f"[red]No versions found for: {name}[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Versions of '{name}'")
    table.add_column("Version", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Status", style="yellow")
    table.add_column("Snapshot", style="magenta")
    table.add_column("Created", style="green")
    table.add_column("Hash", style="dim")

    for v in vers:
        table.add_row(
            f"v{v.version}",
            v.id[:12] + "...",
            v.status.value,
            v.snapshot_name or "-",
            v.created_at.strftime("%Y-%m-%d %H:%M"),
            v.content_hash[:8],
        )

    console.print(table)


@app.command()
def show(
    name: str = typer.Argument(..., help="Prompt name"),
    version: Optional[int] = typer.Option(None, "--version", "-v"),
    snapshot_name: Optional[str] = typer.Option(None, "--snapshot", "-s"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Show prompt details."""
    manager = get_manager(tracking_uri)

    if snapshot_name:
        prompt = manager.get_snapshot(name, snapshot_name)
    else:
        prompt = manager.get_by_name(name, version)

    if prompt is None:
        console.print(f"[red]Prompt not found: {name}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]{prompt.name}[/bold cyan] v{prompt.version}")
    console.print(f"[dim]ID: {prompt.id}[/dim]")
    console.print(f"[dim]Status: {prompt.status.value}[/dim]")
    if prompt.snapshot_name:
        console.print(f"[dim]Snapshot: {prompt.snapshot_name}[/dim]")
    if prompt.forked_from:
        console.print(f"[dim]Forked from: {prompt.forked_from}[/dim]")

    console.print("\n[bold]Content:[/bold]")
    console.print(prompt.content)

    if prompt.variables:
        console.print(f"\n[bold]Variables:[/bold] {', '.join(prompt.variables)}")

    if prompt.metadata.description:
        console.print(f"\n[bold]Description:[/bold] {prompt.metadata.description}")

    if prompt.metadata.tags:
        console.print(f"[bold]Tags:[/bold] {', '.join(prompt.metadata.tags)}")


@app.command()
def render(
    name: str = typer.Argument(..., help="Prompt name"),
    var: List[str] = typer.Option([], "--var", "-V", help="Variable in key=value format"),
    version: Optional[int] = typer.Option(None, "--version", "-v"),
    snapshot_name: Optional[str] = typer.Option(None, "--snapshot", "-s"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Render a prompt with variables."""
    manager = get_manager(tracking_uri)

    # Parse variables
    variables = {}
    for v in var:
        if "=" not in v:
            console.print(f"[red]Invalid variable format: {v} (use key=value)[/red]")
            raise typer.Exit(1)
        key, value = v.split("=", 1)
        variables[key] = value

    try:
        result = manager.render(
            name=name,
            version=version,
            snapshot_name=snapshot_name,
            **variables,
        )
        console.print(result)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def compare(
    name: str = typer.Argument(..., help="Prompt name"),
    v1: int = typer.Argument(..., help="First version number"),
    v2: int = typer.Argument(..., help="Second version number"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Compare two versions of a prompt."""
    manager = get_manager(tracking_uri)

    p1 = manager.get_by_name(name, v1)
    p2 = manager.get_by_name(name, v2)

    if p1 is None:
        console.print(f"[red]Version {v1} not found[/red]")
        raise typer.Exit(1)
    if p2 is None:
        console.print(f"[red]Version {v2} not found[/red]")
        raise typer.Exit(1)

    diff = manager.compare(p1.id, p2.id)

    console.print(f"[bold]Comparing {name}: v{v1} → v{v2}[/bold]\n")

    if diff.content_changed:
        console.print("[yellow]Content changed:[/yellow]")
        console.print(f"[red]- {diff.old_content}[/red]")
        console.print(f"[green]+ {diff.new_content}[/green]")
    else:
        console.print("[dim]Content unchanged[/dim]")

    if diff.variables_added:
        console.print(f"\n[green]Variables added: {', '.join(diff.variables_added)}[/green]")
    if diff.variables_removed:
        console.print(f"[red]Variables removed: {', '.join(diff.variables_removed)}[/red]")

    if diff.metadata_changes:
        console.print("\n[yellow]Metadata changes:[/yellow]")
        for key, changes in diff.metadata_changes.items():
            console.print(f"  {key}: {changes['old']} → {changes['new']}")


@app.command()
def export(
    name: str = typer.Argument(..., help="Prompt name"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file (stdout if not specified)"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Export prompt lineage to JSON."""
    manager = get_manager(tracking_uri)

    try:
        data = manager.export_lineage(name)
        json_str = json.dumps(data, indent=2)

        if output:
            with open(output, "w") as f:
                f.write(json_str)
            console.print(f"[green]Exported to: {output}[/green]")
        else:
            console.print(json_str)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def delete(
    prompt_id: str = typer.Argument(..., help="Prompt ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    tracking_uri: str = typer.Option("mlruns", "--tracking-uri", "-u"),
):
    """Delete a prompt version."""
    manager = get_manager(tracking_uri)

    prompt = manager.get(prompt_id)
    if prompt is None:
        console.print(f"[red]Prompt not found: {prompt_id}[/red]")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(
            f"Delete {prompt.name} v{prompt.version} ({prompt_id})?"
        )
        if not confirm:
            raise typer.Abort()

    if manager.delete(prompt_id):
        console.print(f"[green]Deleted: {prompt_id}[/green]")
    else:
        console.print(f"[red]Failed to delete: {prompt_id}[/red]")


def main():
    """Main entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
