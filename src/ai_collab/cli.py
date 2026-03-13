"""CLI entry point for ai-collab."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import load_agent_configs, load_workflow_config, ensure_global_config
from .workspace import WorkspaceManager

console = Console()


@click.group()
@click.version_option(__version__)
def main():
    """AI-Collab: Terminal-native multi-AI-model collaboration workstation."""
    pass


@main.command()
@click.argument("project_dir", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--workflow", "-w", default="default", help="Workflow to use")
def start(project_dir: str, workflow: str):
    """Start a collaboration workspace for a project."""
    ensure_global_config()
    project_path = Path(project_dir).resolve()
    project_name = project_path.name

    agents = load_agent_configs(project_path)
    wf = load_workflow_config(workflow, project_path)

    console.print(f"[bold green]Starting workspace:[/] {project_name}")
    console.print(f"[dim]Workflow:[/] {wf.name} ({wf.description})")
    console.print(f"[dim]Agents:[/] {', '.join(agents.keys()) if agents else 'using defaults'}")

    mgr = WorkspaceManager()

    if mgr.session_exists(project_name):
        console.print(f"[yellow]Session already exists, attaching...[/]")
        mgr.attach(project_name)
        return

    mgr.create(project_path, wf, agents)
    mgr.attach(project_name)


@main.command()
def ls():
    """List running workspaces."""
    mgr = WorkspaceManager()
    sessions = mgr.list_sessions()

    if not sessions:
        console.print("[dim]No active workspaces.[/]")
        return

    table = Table(title="Active Workspaces")
    table.add_column("Name", style="cyan")
    table.add_column("Project", style="green")
    table.add_column("Agents", style="yellow")
    table.add_column("Created", style="dim")

    for s in sessions:
        table.add_row(s["name"], s["project"], s["agents"], s["created"])

    console.print(table)


@main.command()
@click.argument("project_name", required=False)
@click.option("--all", "stop_all", is_flag=True, help="Stop all workspaces")
def stop(project_name: str | None, stop_all: bool):
    """Stop a workspace (or all workspaces)."""
    mgr = WorkspaceManager()

    if stop_all:
        sessions = mgr.list_sessions()
        for s in sessions:
            mgr.stop(s["project"])
            console.print(f"[red]Stopped:[/] {s['project']}")
        return

    if not project_name:
        console.print("[red]Specify a project name or use --all[/]")
        return

    mgr.stop(project_name)
    console.print(f"[red]Stopped:[/] {project_name}")


@main.command()
@click.argument("project_name")
def attach(project_name: str):
    """Re-attach to a running workspace."""
    mgr = WorkspaceManager()
    if not mgr.session_exists(project_name):
        console.print(f"[red]No workspace found for:[/] {project_name}")
        return
    mgr.attach(project_name)


@main.command()
@click.argument("project_name", required=False)
def status(project_name: str | None):
    """Show detailed status of a workspace."""
    mgr = WorkspaceManager()

    if not project_name:
        # Show all
        sessions = mgr.list_sessions()
        if not sessions:
            console.print("[dim]No active workspaces.[/]")
            return
        for s in sessions:
            _print_status(mgr, s["name"])
        return

    if not mgr.session_exists(project_name):
        console.print(f"[red]No workspace found for:[/] {project_name}")
        return
    _print_status(mgr, project_name)


def _print_status(mgr: WorkspaceManager, name: str):
    """Print detailed status for a workspace."""
    info = mgr.get_status(name)
    console.print(f"\n[bold cyan]{name}[/]")
    for agent_name, agent_info in info.get("agents", {}).items():
        status_color = "green" if agent_info["alive"] else "red"
        console.print(f"  [{status_color}]●[/] {agent_name}: {agent_info.get('title', 'unknown')}")


@main.command()
@click.argument("project_dir", default=".", type=click.Path(exists=True, file_okay=False))
def init(project_dir: str):
    """Initialize AI-Collab config for a project."""
    ensure_global_config()
    project_path = Path(project_dir).resolve()
    config_dir = project_path / ".ai-collab"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "sessions").mkdir(exist_ok=True)

    console.print(f"[green]Initialized .ai-collab/ in {project_path.name}[/]")
