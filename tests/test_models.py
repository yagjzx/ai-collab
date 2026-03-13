"""Tests for data models."""

from ai_collab.models import AgentConfig, Message, WorkflowConfig, RoleAssignment, CommunicationMode


def test_agent_config_defaults():
    agent = AgentConfig(name="test", display_name="Test", binary="test-bin")
    assert agent.launch_args == []
    assert agent.communication_mode == CommunicationMode.SUBPROCESS
    assert agent.timeout == 120


def test_message_creation():
    msg = Message(
        id="msg_001",
        timestamp="2026-03-13T00:00:00Z",
        session_id="sess_001",
        from_agent="claude",
        from_role="designer",
        to_agent="codex",
        to_role="reviewer",
        type="review_request",
        payload={"content": "test"},
    )
    assert msg.from_agent == "claude"
    assert msg.to_role == "reviewer"
    assert msg.metadata == {}


def test_workflow_config_with_roles():
    wf = WorkflowConfig(
        name="test",
        roles=[
            RoleAssignment(role="designer", agent="claude", is_primary=True),
            RoleAssignment(role="reviewer", agent="codex"),
        ],
    )
    assert len(wf.roles) == 2
    primary = [r for r in wf.roles if r.is_primary]
    assert len(primary) == 1
