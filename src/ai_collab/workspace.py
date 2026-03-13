"""Workspace lifecycle management via tmux."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AgentConfig, AgentStatus, WorkflowConfig, SessionState, AgentState

SESSION_PREFIX = "aic-"


class WorkspaceManager:
    """Manages workspace sessions backed by tmux."""

    def session_name(self, project_name: str) -> str:
        return f"{SESSION_PREFIX}{project_name}"

    def session_exists(self, project_name: str) -> bool:
        name = self.session_name(project_name)
        result = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True,
        )
        return result.returncode == 0

    def create(
        self,
        project_dir: Path,
        workflow: WorkflowConfig,
        agents: dict[str, AgentConfig],
    ) -> SessionState:
        """Create a new workspace with tmux layout and start agents."""
        project_name = project_dir.name
        session = self.session_name(project_name)
        workdir = str(project_dir)

        # Resolve which agents are needed from workflow roles
        role_agents = []
        primary_role = None
        for role in workflow.roles:
            agent_cfg = agents.get(role.agent)
            if agent_cfg is None:
                agent_cfg = _default_agent(role.agent)
            role_agents.append((role, agent_cfg))
            if role.is_primary:
                primary_role = role

        if not role_agents:
            raise RuntimeError("Workflow has no roles defined")

        primaries = [r for r, _ in role_agents if r.is_primary]
        if len(primaries) > 1:
            raise RuntimeError(f"Workflow has {len(primaries)} primary roles, expected at most 1")

        # Create tmux session with first (primary) pane
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-c", workdir, "-x", "220", "-y", "50"],
            check=True,
        )

        # Split layout: primary on left (60%), others stacked on right (40%)
        non_primary = [(r, a) for r, a in role_agents if not r.is_primary]

        if non_primary:
            # Create right pane
            subprocess.run(
                ["tmux", "split-window", "-h", "-t", f"{session}:1", "-l", "40%", "-c", workdir],
                check=True,
            )
            # Stack additional agents vertically on the right
            for i in range(1, len(non_primary)):
                target_pane = i + 1  # panes are 1-indexed after primary
                pct = str(int(100 / (len(non_primary) - i + 1))) + "%"
                subprocess.run(
                    ["tmux", "split-window", "-v", "-t", f"{session}:1.{target_pane}", "-l", pct, "-c", workdir],
                    check=True,
                )

        # Set pane titles and start agents
        pane_idx = 1
        state = SessionState(
            session_id=f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            project_name=project_name,
            project_dir=project_dir,
            tmux_session=session,
            workflow=workflow.name,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Primary agent gets pane 1
        if primary_role:
            primary_agent = agents.get(primary_role.agent, _default_agent(primary_role.agent))
            _setup_pane(session, pane_idx, primary_role, primary_agent, workdir)
            state.agents[primary_role.agent] = AgentState(
                name=primary_role.agent,
                role=primary_role.role,
                status=AgentStatus.RUNNING,
                log_path=str(self._log_path(project_dir, primary_role.agent)),
            )
            pane_idx += 1

        # Non-primary agents get subsequent panes
        for role, agent_cfg in non_primary:
            _setup_pane(session, pane_idx, role, agent_cfg, workdir)
            state.agents[role.agent] = AgentState(
                name=role.agent,
                role=role.role,
                status=AgentStatus.RUNNING,
                log_path=str(self._log_path(project_dir, role.agent)),
            )
            pane_idx += 1

        # Enable pane borders with titles
        subprocess.run(["tmux", "set", "-t", session, "pane-border-status", "top"], check=True)
        subprocess.run(
            ["tmux", "set", "-t", session, "pane-border-format", " #{pane_title} "],
            check=True,
        )

        # Focus on primary pane
        subprocess.run(["tmux", "select-pane", "-t", f"{session}:1.1"], check=True)

        # Save session state
        self._save_state(project_dir, state)

        return state

    def attach(self, project_name: str):
        """Attach or switch to an existing session."""
        name = self.session_name(project_name)
        if os.environ.get("TMUX"):
            os.execvp("tmux", ["tmux", "switch-client", "-t", name])
        else:
            os.execvp("tmux", ["tmux", "attach", "-t", name])

    def stop(self, project_name: str):
        """Kill a workspace session."""
        name = self.session_name(project_name)
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)

    def list_sessions(self) -> list[dict[str, str]]:
        """List all ai-collab sessions."""
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}\t#{session_created}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        sessions = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            name = parts[0]
            if not name.startswith(SESSION_PREFIX):
                continue
            project = name[len(SESSION_PREFIX):]
            created = ""
            if len(parts) > 1:
                try:
                    created = datetime.fromtimestamp(int(parts[1])).strftime("%m-%d %H:%M")
                except (ValueError, OSError):
                    created = parts[1]

            # Count agents (panes)
            panes_result = subprocess.run(
                ["tmux", "list-panes", "-t", name, "-F", "#{pane_title}"],
                capture_output=True,
                text=True,
            )
            agent_names = panes_result.stdout.strip().replace("\n", ", ") if panes_result.returncode == 0 else "?"

            sessions.append({
                "name": name,
                "project": project,
                "agents": agent_names,
                "created": created,
            })
        return sessions

    def get_status(self, project_name: str) -> dict[str, Any]:
        """Get detailed status of a workspace."""
        name = self.session_name(project_name)
        result = subprocess.run(
            ["tmux", "list-panes", "-t", name, "-F", "#{pane_id}\t#{pane_title}\t#{pane_pid}\t#{pane_dead}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {"agents": {}}

        agents = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            pane_id, title, pid, dead = parts
            agents[title] = {
                "pane_id": pane_id,
                "title": title,
                "pid": int(pid) if pid.isdigit() else 0,
                "alive": dead == "0",
            }
        return {"agents": agents}

    def _log_path(self, project_dir: Path, agent_name: str) -> Path:
        log_dir = project_dir / ".ai-collab" / "sessions" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{agent_name}.log"

    def _save_state(self, project_dir: Path, state: SessionState):
        state_dir = project_dir / ".ai-collab" / "sessions"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"
        state_file.write_text(state.model_dump_json(indent=2))


def _setup_pane(session: str, pane_idx: int, role, agent_cfg: AgentConfig, workdir: str):
    """Configure a tmux pane: set title and launch the agent."""
    pane = f"{session}:1.{pane_idx}"
    title = f"{agent_cfg.display_name} ({role.role})"
    subprocess.run(["tmux", "select-pane", "-t", pane, "-T", title], check=True)

    # Build launch command
    launch_cmd = f"cd {workdir} && {agent_cfg.binary}"
    if agent_cfg.launch_args:
        launch_cmd += " " + " ".join(agent_cfg.launch_args)

    subprocess.run(["tmux", "send-keys", "-t", pane, launch_cmd, "Enter"], check=True)


def _default_agent(name: str) -> AgentConfig:
    """Return a sensible default agent config for known agents."""
    defaults = {
        "claude": AgentConfig(
            name="claude",
            display_name="Claude Code",
            binary="claude",
            healthcheck="claude --version",
        ),
        "codex": AgentConfig(
            name="codex",
            display_name="Codex CLI",
            binary="codex",
            communication_mode="tmux-keys",
            output_capture="terminal",
            healthcheck="codex --version",
        ),
        "gemini": AgentConfig(
            name="gemini",
            display_name="Gemini CLI",
            binary="gemini",
            launch_args=[],
            communication_mode="subprocess",
            healthcheck="gemini --version",
        ),
    }
    if name in defaults:
        return defaults[name]
    return AgentConfig(name=name, display_name=name, binary=name)
