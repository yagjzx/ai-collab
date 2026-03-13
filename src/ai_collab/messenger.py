"""Inter-agent communication module."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AgentConfig, CommunicationMode, Message

logger = logging.getLogger(__name__)


class MessengerError(Exception):
    """Raised when a message send fails."""


class Messenger:
    """Handles sending messages between agents in a workspace.

    Each Messenger is scoped to a project directory and session, storing
    all message logs under <project_dir>/.ai-collab/sessions/messages/.
    """

    def __init__(
        self,
        project_dir: Path,
        session_id: str,
        agents: dict[str, AgentConfig] | None = None,
        tmux_session: str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.session_id = session_id
        self.agents: dict[str, AgentConfig] = agents or {}
        self.tmux_session = tmux_session

        # Ensure message log directory exists
        self.messages_dir = (
            self.project_dir / ".ai-collab" / "sessions" / "messages"
        )
        self.messages_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        message_type: str = "query",
        *,
        from_role: str = "",
        to_role: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Send a message from one agent to another.

        Creates a Message, routes it through the appropriate backend based
        on the target agent's CommunicationMode, logs the exchange, and
        returns a response Message.
        """
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        outgoing = Message(
            id=msg_id,
            timestamp=now,
            session_id=self.session_id,
            from_agent=from_agent,
            from_role=from_role,
            to_agent=to_agent,
            to_role=to_role,
            type=message_type,
            payload={"content": content},
            metadata=metadata or {},
        )
        self.log_message(outgoing)

        # Resolve target agent config
        agent_cfg = self.agents.get(to_agent)
        if agent_cfg is None:
            agent_cfg = AgentConfig(
                name=to_agent, display_name=to_agent, binary=to_agent
            )

        # Route to the right backend
        try:
            response_text = self._dispatch(agent_cfg, content)
        except Exception as exc:
            logger.error("Failed to send message %s to %s: %s", msg_id, to_agent, exc)
            response_text = f"[ERROR] {exc}"

        # Build response message
        resp_id = f"msg_{uuid.uuid4().hex[:12]}"
        response = Message(
            id=resp_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=self.session_id,
            from_agent=to_agent,
            from_role=to_role,
            to_agent=from_agent,
            to_role=from_role,
            type="response",
            payload={"content": response_text},
            metadata={"in_reply_to": msg_id},
        )
        self.log_message(response)

        return response

    def log_message(self, message: Message) -> Path:
        """Persist a message to disk as JSON.

        Returns the path to the written file.
        """
        path = self.messages_dir / f"{message.id}.json"
        path.write_text(message.model_dump_json(indent=2))
        return path

    # ------------------------------------------------------------------
    # Backend dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, agent_cfg: AgentConfig, content: str) -> str:
        mode = CommunicationMode(agent_cfg.communication_mode)
        if mode == CommunicationMode.SUBPROCESS:
            return self._send_subprocess(agent_cfg, content)
        elif mode == CommunicationMode.TMUX_KEYS:
            return self._send_tmux_keys(agent_cfg, content)
        elif mode == CommunicationMode.STDIN:
            return self._send_stdin(agent_cfg, content)
        else:
            raise MessengerError(f"Unsupported communication mode: {mode}")

    def _send_subprocess(self, agent_cfg: AgentConfig, content: str) -> str:
        """Run the agent binary as a subprocess, pass content via args, capture stdout."""
        cmd = [agent_cfg.binary] + list(agent_cfg.launch_args)
        # Append the prompt content using the agent's prompt flag
        if agent_cfg.prompt_flag:
            cmd.extend([agent_cfg.prompt_flag, content])
        else:
            cmd.append(content)

        logger.debug("SUBPROCESS exec: %s", " ".join(shlex.quote(c) for c in cmd))

        # Inherit all env vars (API keys etc.) from the parent process
        env = os.environ.copy()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=agent_cfg.timeout,
                cwd=str(self.project_dir),
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise MessengerError(
                f"Subprocess timed out after {agent_cfg.timeout}s for agent {agent_cfg.name}"
            )
        except FileNotFoundError:
            raise MessengerError(
                f"Binary not found: {agent_cfg.binary}"
            )

        if result.returncode != 0 and result.stderr:
            logger.warning(
                "Agent %s exited %d: %s",
                agent_cfg.name,
                result.returncode,
                result.stderr.strip(),
            )

        output = result.stdout.strip()
        # Strip Gemini CLI YOLO mode warning lines
        if agent_cfg.name == "gemini":
            output = "\n".join(
                l for l in output.splitlines() if "YOLO mode" not in l
            ).strip()
        return output

    def _send_tmux_keys(self, agent_cfg: AgentConfig, content: str) -> str:
        """Send text to the agent's tmux pane via send-keys."""
        if not self.tmux_session:
            raise MessengerError(
                "tmux_session is required for TMUX_KEYS communication mode"
            )

        # Find the pane for this agent. Convention: pane title contains agent name.
        pane_target = self._resolve_pane(agent_cfg.name)

        # Escape content for tmux send-keys (replace newlines with Enter keypresses)
        lines = content.split("\n")
        try:
            for line in lines:
                args = ["tmux", "send-keys", "-t", pane_target, line, "Enter"]
                subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
        except subprocess.CalledProcessError as exc:
            raise MessengerError(
                f"tmux send-keys failed for agent {agent_cfg.name}: {exc.stderr}"
            )
        except subprocess.TimeoutExpired:
            raise MessengerError(
                f"tmux send-keys timed out for agent {agent_cfg.name}"
            )

        # For tmux-keys mode we cannot directly capture output;
        # return an ack so the caller knows the keys were sent.
        return f"[SENT via tmux-keys to {agent_cfg.name}]"

    def _send_stdin(self, agent_cfg: AgentConfig, content: str) -> str:
        """Stub for STDIN communication mode (write to a file the agent reads).

        This is a placeholder for future implementation.
        """
        inbox_dir = (
            self.project_dir
            / ".ai-collab"
            / "sessions"
            / "inbox"
            / agent_cfg.name
        )
        inbox_dir.mkdir(parents=True, exist_ok=True)
        inbox_file = inbox_dir / f"{uuid.uuid4().hex[:8]}.txt"
        inbox_file.write_text(content)
        logger.info("STDIN stub: wrote to %s", inbox_file)
        return f"[QUEUED via stdin to {agent_cfg.name}: {inbox_file.name}]"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_pane(self, agent_name: str) -> str:
        """Resolve a tmux pane target string for the given agent.

        Falls back to session:1.1 if the agent pane cannot be found.
        """
        if not self.tmux_session:
            return f"{agent_name}:1.1"

        try:
            result = subprocess.run(
                [
                    "tmux",
                    "list-panes",
                    "-t",
                    self.tmux_session,
                    "-F",
                    "#{pane_id}\t#{pane_title}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.split("\t", 1)
                    if len(parts) == 2 and agent_name.lower() in parts[1].lower():
                        return parts[0]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback
        return f"{self.tmux_session}:1.1"
