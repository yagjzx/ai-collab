"""Task lifecycle management: create, dispatch, verify, track."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workspace import WorkspaceManager


def _tasks_dir(project_dir: Path) -> Path:
    d = project_dir / ".ai-collab" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_task_id(project_dir: Path) -> str:
    """Generate the next T-NNN task ID."""
    tasks_dir = _tasks_dir(project_dir)
    existing = [d.name for d in tasks_dir.iterdir() if d.is_dir() and d.name.startswith("T")]
    nums = []
    for name in existing:
        m = re.match(r"T(\d+)", name)
        if m:
            nums.append(int(m.group(1)))
    next_num = max(nums, default=0) + 1
    return f"T{next_num:03d}"


def _load_template(name: str) -> str:
    """Load a task template from bundled configs."""
    # Try bundled path first (dev install)
    bundled = Path(__file__).parent.parent.parent / "configs" / "templates" / f"{name}.md"
    if bundled.exists():
        return bundled.read_text()
    # Try global config
    global_path = Path.home() / ".ai-collab" / "templates" / f"{name}.md"
    if global_path.exists():
        return global_path.read_text()
    raise FileNotFoundError(f"Template not found: {name}.md")


def create_task(project_dir: Path, title: str, goal: str = "") -> dict[str, Any]:
    """Create a new task with TASK.md and VERIFY.md from templates."""
    task_id = _next_task_id(project_dir)
    task_dir = _tasks_dir(project_dir) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    project_name = project_dir.name

    replacements = {
        "{task_id}": task_id,
        "{title}": title,
        "{project}": project_name,
        "{created}": now,
        "{goal}": goal or "(fill in)",
        "{read_first}": "CLAUDE.md",
    }

    for template_name in ("TASK", "VERIFY"):
        content = _load_template(template_name)
        for key, val in replacements.items():
            content = content.replace(key, val)
        (task_dir / f"{template_name}.md").write_text(content)

    # Write status file
    status = {
        "task_id": task_id,
        "title": title,
        "status": "created",
        "created": now,
        "executor": "",
        "verifier": "",
        "result": "",
    }
    import json
    (task_dir / "status.json").write_text(json.dumps(status, indent=2))

    return status


def dispatch_task(
    project_dir: Path,
    task_id: str,
    executor: str = "codex",
) -> str:
    """Send a task to the executor agent via tmux pane (interactive, non-blocking).

    For complex tasks, subprocess mode times out. Instead, we send the prompt
    to the agent's tmux pane so the user can watch execution in real-time.
    The agent writes results to TASK.md's Execution Report section.
    """
    import subprocess as sp

    task_dir = _tasks_dir(project_dir) / task_id
    if not task_dir.exists():
        raise FileNotFoundError(f"Task {task_id} not found")

    task_file = task_dir / "TASK.md"
    rel_path = task_file.relative_to(project_dir)

    mgr = WorkspaceManager()
    project_name = project_dir.name

    if not mgr.session_exists(project_name):
        return "[ERROR] No active workspace. Run: ai-collab start <project-dir>"

    tmux_session = mgr.session_name(project_name)

    # Find the executor's pane by scanning pane titles
    pane_target = _find_agent_pane(tmux_session, executor)
    if not pane_target:
        return f"[ERROR] No pane found for {executor} in {tmux_session}"

    prompt = (
        f"Read the file {rel_path} in the current directory. "
        f"Execute all instructions in that task file. "
        f"When done, update the Execution Report section in {rel_path} with: "
        f"summary of changes, files changed, commands run, and commit hash."
    )

    # Send via tmux send-keys (non-blocking, user sees execution in real-time)
    # Interactive CLI agents (codex, claude) need Enter to submit the prompt,
    # then another Enter to confirm/start execution.
    try:
        sp.run(
            ["tmux", "send-keys", "-t", pane_target, prompt, "Enter"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        import time
        time.sleep(1)
        # Send a second Enter to confirm/submit in interactive mode
        sp.run(
            ["tmux", "send-keys", "-t", pane_target, "", "Enter"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except sp.CalledProcessError as e:
        return f"[ERROR] tmux send-keys failed: {e.stderr}"

    _update_status(task_dir, status="executing", executor=executor)

    return f"[DISPATCHED to {executor} pane {pane_target}] Watch the pane for progress."


def verify_task(
    project_dir: Path,
    task_id: str,
    verifier: str = "gemini",
) -> str:
    """Send a task to the verifier agent via tmux pane."""
    import subprocess as sp

    task_dir = _tasks_dir(project_dir) / task_id
    if not task_dir.exists():
        raise FileNotFoundError(f"Task {task_id} not found")

    task_file = task_dir / "TASK.md"
    verify_file = task_dir / "VERIFY.md"
    task_rel = task_file.relative_to(project_dir)
    verify_rel = verify_file.relative_to(project_dir)

    mgr = WorkspaceManager()
    project_name = project_dir.name

    if not mgr.session_exists(project_name):
        return "[ERROR] No active workspace. Run: ai-collab start <project-dir>"

    tmux_session = mgr.session_name(project_name)
    pane_target = _find_agent_pane(tmux_session, verifier)
    if not pane_target:
        return f"[ERROR] No pane found for {verifier} in {tmux_session}"

    prompt = (
        f"Read these two files: {task_rel} and {verify_rel}. "
        f"Independently verify ALL acceptance criteria by running commands. "
        f"Do NOT trust summaries — run commands and read files yourself. "
        f"Update {verify_rel} with your verdict: PASS, FAIL, or PASS WITH NOTES."
    )

    try:
        sp.run(
            ["tmux", "send-keys", "-t", pane_target, prompt, "Enter"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        import time
        time.sleep(1)
        sp.run(
            ["tmux", "send-keys", "-t", pane_target, "", "Enter"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except sp.CalledProcessError as e:
        return f"[ERROR] tmux send-keys failed: {e.stderr}"

    _update_status(task_dir, status="verifying", verifier=verifier)

    return f"[DISPATCHED to {verifier} pane {pane_target}] Watch the pane for verification progress."


def _find_agent_pane(tmux_session: str, agent_name: str) -> str | None:
    """Find a tmux pane for the given agent.

    Matches by pane title (case-insensitive), falling back to role-based
    position convention: pane 1=primary, pane 2=reviewer, pane 3=inspiration.
    """
    import subprocess as sp

    # Known role → pane index mapping (default workflow convention)
    ROLE_PANE_MAP = {"claude": 1, "codex": 2, "gemini": 3}

    try:
        result = sp.run(
            ["tmux", "list-panes", "-t", tmux_session,
             "-F", "#{pane_id}\t#{pane_index}\t#{pane_title}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().splitlines()

        # First pass: match by title
        for line in lines:
            parts = line.split("\t", 2)
            if len(parts) >= 3 and agent_name.lower() in parts[2].lower():
                return parts[0]

        # Second pass: match by conventional pane index
        target_idx = ROLE_PANE_MAP.get(agent_name.lower())
        if target_idx is not None:
            for line in lines:
                parts = line.split("\t", 2)
                if len(parts) >= 2 and parts[1] == str(target_idx):
                    return parts[0]

    except (sp.TimeoutExpired, FileNotFoundError):
        pass
    return None


def list_tasks(project_dir: Path) -> list[dict[str, Any]]:
    """List all tasks for a project."""
    import json
    tasks_dir = _tasks_dir(project_dir)
    tasks = []
    for d in sorted(tasks_dir.iterdir()):
        status_file = d / "status.json"
        if status_file.exists():
            tasks.append(json.loads(status_file.read_text()))
    return tasks


def _update_status(task_dir: Path, **updates):
    """Update fields in status.json."""
    import json
    status_file = task_dir / "status.json"
    if status_file.exists():
        data = json.loads(status_file.read_text())
    else:
        data = {}
    data.update(updates)
    status_file.write_text(json.dumps(data, indent=2))
