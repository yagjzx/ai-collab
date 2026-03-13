"""CLI entry point for ai-collab."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import load_agent_configs, load_workflow_config, ensure_global_config
from .workspace import WorkspaceManager
from .messenger import Messenger
from . import task_manager

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
            _print_status(mgr, s["project"])
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


@main.command()
@click.argument("agent_name")
@click.argument("prompt", nargs=-1, required=True)
@click.option("--project", "-p", default=".", type=click.Path(exists=True, file_okay=False),
              help="Project directory (for context and log isolation)")
def send(agent_name: str, prompt: tuple[str, ...], project: str):
    """Send a message to an agent (replaces ask-model).

    Examples:

        ai-collab send gemini "Review this code"

        echo "diff" | ai-collab send codex "Review this diff"

        ai-collab send gemini "Check CLAUDE.md" -p ~/workspace/clawforce
    """
    import sys as _sys

    ensure_global_config()
    project_path = Path(project).resolve()
    agents = load_agent_configs(project_path)

    full_prompt = " ".join(prompt)

    # Read stdin if piped
    if not _sys.stdin.isatty():
        stdin_text = _sys.stdin.read()
        if stdin_text.strip():
            full_prompt = f"{full_prompt}\n\n---\n{stdin_text}\n---"

    # Find the active session for this project (for tmux-keys routing)
    mgr = WorkspaceManager()
    project_name = project_path.name
    tmux_session = mgr.session_name(project_name) if mgr.session_exists(project_name) else None

    messenger = Messenger(
        project_dir=project_path,
        session_id=f"cli_{project_name}",
        agents=agents,
        tmux_session=tmux_session,
    )

    console.print(f"[dim]Sending to {agent_name}...[/]")
    response = messenger.send(
        from_agent="user",
        to_agent=agent_name,
        content=full_prompt,
        message_type="query",
    )

    # Print the response
    content = response.payload.get("content", "")
    if content.startswith("[ERROR]"):
        console.print(f"[red]{content}[/]")
    elif content.startswith("[SENT via tmux"):
        console.print(f"[yellow]{content}[/]")
    else:
        console.print(content)


# ── Task subcommand group ──────────────────────────────────────────

@main.group()
def task():
    """Manage structured tasks (create → dispatch → verify)."""
    pass


@task.command("create")
@click.argument("title")
@click.option("--goal", "-g", default="", help="One-sentence goal")
@click.option("--project", "-p", default=".", type=click.Path(exists=True, file_okay=False))
def task_create(title: str, goal: str, project: str):
    """Create a new task from templates."""
    project_path = Path(project).resolve()
    status = task_manager.create_task(project_path, title, goal)
    task_id = status["task_id"]
    task_dir = project_path / ".ai-collab" / "tasks" / task_id

    console.print(f"[bold green]Created {task_id}:[/] {title}")
    console.print(f"  [dim]TASK.md:[/]   {task_dir / 'TASK.md'}")
    console.print(f"  [dim]VERIFY.md:[/] {task_dir / 'VERIFY.md'}")
    console.print(f"\n[yellow]Edit TASK.md to fill in details, then run:[/]")
    console.print(f"  ai-collab task dispatch {task_id}")


@task.command("dispatch")
@click.argument("task_id")
@click.option("--executor", "-e", default="codex", help="Agent to execute")
@click.option("--project", "-p", default=".", type=click.Path(exists=True, file_okay=False))
def task_dispatch(task_id: str, executor: str, project: str):
    """Dispatch a task to the executor agent."""
    project_path = Path(project).resolve()
    console.print(f"[dim]Dispatching {task_id} to {executor}...[/]")
    result = task_manager.dispatch_task(project_path, task_id, executor)

    if result.startswith("[ERROR]"):
        console.print(f"[red]{result}[/]")
    else:
        console.print(f"[green]Executor response:[/]")
        console.print(result)
        console.print(f"\n[yellow]When ready, verify with:[/]")
        console.print(f"  ai-collab task verify {task_id}")


@task.command("verify")
@click.argument("task_id")
@click.option("--verifier", "-v", default="gemini", help="Agent to verify")
@click.option("--project", "-p", default=".", type=click.Path(exists=True, file_okay=False))
def task_verify(task_id: str, verifier: str, project: str):
    """Send a task to the verifier for independent verification."""
    project_path = Path(project).resolve()
    console.print(f"[dim]Sending {task_id} to {verifier} for verification...[/]")
    result = task_manager.verify_task(project_path, task_id, verifier)

    if result.startswith("[ERROR]"):
        console.print(f"[red]{result}[/]")
    else:
        console.print(f"[green]Verifier response:[/]")
        console.print(result)


@task.command("ls")
@click.option("--project", "-p", default=".", type=click.Path(exists=True, file_okay=False))
def task_ls(project: str):
    """List all tasks for a project."""
    project_path = Path(project).resolve()
    tasks = task_manager.list_tasks(project_path)

    if not tasks:
        console.print("[dim]No tasks found.[/]")
        return

    table = Table(title=f"Tasks: {project_path.name}")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Result", style="green")
    table.add_column("Created", style="dim")

    for t in tasks:
        table.add_row(
            t.get("task_id", "?"),
            t.get("title", "?"),
            t.get("status", "?"),
            t.get("result", ""),
            t.get("created", "?"),
        )

    console.print(table)
