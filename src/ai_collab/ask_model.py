"""ask-model CLI — backward-compatible entry point.

Usage:
    ask-model gemini "Review this code"
    ask-model codex "Write unit tests"
    echo "context" | ask-model gemini "Review this"

This is a thin wrapper around ai-collab's Messenger, providing the same
interface as the old ask-model shell script but with proper project isolation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import load_agent_configs, get_default_agent, ensure_global_config
from .messenger import Messenger
from .workspace import WorkspaceManager


PROVIDERS = {"gemini", "codex", "claude"}


def main():
    if len(sys.argv) < 3:
        print("Usage: ask-model <gemini|codex|claude> \"prompt\"", file=sys.stderr)
        sys.exit(1)

    provider = sys.argv[1].lower()
    prompt = " ".join(sys.argv[2:])

    if provider not in PROVIDERS:
        print(f"ERROR: Unknown provider '{provider}'. Use: {', '.join(sorted(PROVIDERS))}", file=sys.stderr)
        sys.exit(1)

    # Read stdin if piped
    stdin_text = ""
    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read()
    if stdin_text.strip():
        prompt = f"{prompt}\n\n---\n{stdin_text}\n---"

    ensure_global_config()

    # Detect project from cwd
    project_dir = Path.cwd()
    agents = load_agent_configs(project_dir)

    # Ensure target agent has a config
    if provider not in agents:
        agents[provider] = get_default_agent(provider)

    # Find active tmux session for this project
    mgr = WorkspaceManager()
    project_name = project_dir.name
    tmux_session = mgr.session_name(project_name) if mgr.session_exists(project_name) else None

    messenger = Messenger(
        project_dir=project_dir,
        session_id=f"askmodel_{project_name}",
        agents=agents,
        tmux_session=tmux_session,
    )

    response = messenger.send(
        from_agent="user",
        to_agent=provider,
        content=prompt,
        message_type="query",
    )

    content = response.payload.get("content", "")
    print(content)


if __name__ == "__main__":
    main()
