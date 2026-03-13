"""Tests for the inter-agent messenger module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_collab.models import AgentConfig, CommunicationMode, Message
from ai_collab.messenger import Messenger, MessengerError


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project directory."""
    return tmp_path / "test-project"


@pytest.fixture
def messenger(tmp_project):
    """Create a Messenger with two agents configured."""
    agents = {
        "gemini": AgentConfig(
            name="gemini",
            display_name="Gemini CLI",
            binary="gemini",
            launch_args=["--yolo", "-o", "text"],
            communication_mode=CommunicationMode.SUBPROCESS,
            timeout=30,
        ),
        "codex": AgentConfig(
            name="codex",
            display_name="Codex CLI",
            binary="codex",
            communication_mode=CommunicationMode.TMUX_KEYS,
            timeout=60,
        ),
    }
    return Messenger(
        project_dir=tmp_project,
        session_id="sess_test001",
        agents=agents,
        tmux_session="aic-test",
    )


# ------------------------------------------------------------------
# Test 1: Message creation and serialization
# ------------------------------------------------------------------

def test_message_creation_and_serialization():
    """Message round-trips through JSON correctly."""
    msg = Message(
        id="msg_abc123",
        timestamp="2026-03-13T12:00:00+00:00",
        session_id="sess_001",
        from_agent="claude",
        from_role="designer",
        to_agent="codex",
        to_role="reviewer",
        type="review_request",
        payload={"content": "Please review this plan."},
        metadata={"tag": "plan_v1"},
    )

    dumped = json.loads(msg.model_dump_json())
    assert dumped["id"] == "msg_abc123"
    assert dumped["from_agent"] == "claude"
    assert dumped["payload"]["content"] == "Please review this plan."
    assert dumped["metadata"]["tag"] == "plan_v1"

    # Reconstruct from JSON
    restored = Message.model_validate(dumped)
    assert restored == msg


# ------------------------------------------------------------------
# Test 2: log_message writes to disk
# ------------------------------------------------------------------

def test_log_message_writes_to_disk(messenger):
    """log_message persists a Message as a JSON file."""
    msg = Message(
        id="msg_disk001",
        timestamp="2026-03-13T12:00:00+00:00",
        session_id="sess_test001",
        from_agent="claude",
        from_role="designer",
        to_agent="gemini",
        to_role="inspiration",
        type="query",
        payload={"content": "Give me ideas."},
    )

    path = messenger.log_message(msg)

    assert path.exists()
    assert path.name == "msg_disk001.json"

    data = json.loads(path.read_text())
    assert data["id"] == "msg_disk001"
    assert data["payload"]["content"] == "Give me ideas."
    assert data["from_agent"] == "claude"


# ------------------------------------------------------------------
# Test 3: Subprocess backend (mocked)
# ------------------------------------------------------------------

@patch("ai_collab.messenger.subprocess.run")
def test_send_subprocess_backend(mock_run, messenger):
    """send() routes to subprocess and captures stdout."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Here is my review: LGTM\n",
        stderr="",
    )

    response = messenger.send(
        from_agent="claude",
        to_agent="gemini",
        content="Review this code",
        message_type="review_request",
        from_role="designer",
        to_role="inspiration",
    )

    assert response.from_agent == "gemini"
    assert response.to_agent == "claude"
    assert response.type == "response"
    assert "LGTM" in response.payload["content"]

    # Verify subprocess was called with the right command
    call_args = mock_run.call_args_list[0]
    cmd = call_args[0][0]
    assert cmd[0] == "gemini"
    assert "--yolo" in cmd
    assert "-p" in cmd
    assert "Review this code" in cmd


# ------------------------------------------------------------------
# Test 4: Tmux-keys backend (mocked)
# ------------------------------------------------------------------

@patch("ai_collab.messenger.subprocess.run")
def test_send_tmux_keys_backend(mock_run, messenger):
    """send() routes to tmux send-keys for TMUX_KEYS agents."""
    # First call: _resolve_pane does tmux list-panes
    pane_list_result = MagicMock(
        returncode=0,
        stdout="%1\tCodEx CLI (reviewer)",
    )
    # Second call: tmux send-keys
    send_keys_result = MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = [pane_list_result, send_keys_result]

    response = messenger.send(
        from_agent="claude",
        to_agent="codex",
        content="Check this",
        message_type="query",
    )

    assert response.from_agent == "codex"
    assert "[SENT via tmux-keys" in response.payload["content"]

    # The second subprocess call should be tmux send-keys
    second_call = mock_run.call_args_list[1]
    cmd = second_call[0][0]
    assert cmd[0] == "tmux"
    assert cmd[1] == "send-keys"


# ------------------------------------------------------------------
# Test 5: Timeout produces MessengerError, not a crash
# ------------------------------------------------------------------

@patch("ai_collab.messenger.subprocess.run")
def test_subprocess_timeout_does_not_crash(mock_run, messenger):
    """A subprocess timeout is caught and returned as an error message."""
    import subprocess as sp
    mock_run.side_effect = sp.TimeoutExpired(cmd=["gemini"], timeout=30)

    response = messenger.send(
        from_agent="claude",
        to_agent="gemini",
        content="Slow question",
    )

    # Should not raise; instead the response payload contains the error
    assert "[ERROR]" in response.payload["content"]
    assert "timed out" in response.payload["content"].lower()


# ------------------------------------------------------------------
# Test 6: STDIN stub writes inbox file
# ------------------------------------------------------------------

def test_stdin_stub_writes_inbox(tmp_path):
    """STDIN mode writes content to an inbox file."""
    agents = {
        "future_agent": AgentConfig(
            name="future_agent",
            display_name="Future",
            binary="future",
            communication_mode=CommunicationMode.STDIN,
        ),
    }
    m = Messenger(
        project_dir=tmp_path / "proj",
        session_id="sess_stdin",
        agents=agents,
    )

    response = m.send(
        from_agent="claude",
        to_agent="future_agent",
        content="Hello from stdin",
    )

    assert "[QUEUED via stdin" in response.payload["content"]

    inbox_dir = tmp_path / "proj" / ".ai-collab" / "sessions" / "inbox" / "future_agent"
    files = list(inbox_dir.glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text() == "Hello from stdin"
