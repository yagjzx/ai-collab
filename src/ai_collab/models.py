"""Core data models for AI-Collab."""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CommunicationMode(str, enum.Enum):
    SUBPROCESS = "subprocess"
    TMUX_KEYS = "tmux-keys"
    STDIN = "stdin"


class AgentConfig(BaseModel):
    """Configuration for a single AI agent."""

    name: str
    display_name: str
    binary: str
    launch_args: list[str] = Field(default_factory=list)
    healthcheck: str = ""
    communication_mode: CommunicationMode = CommunicationMode.SUBPROCESS
    prompt_flag: str = "-p"  # CLI flag before the prompt content ("" = positional arg)
    input_format: str = "text"
    output_capture: str = "stdout"
    timeout: int = 120
    auto_restart: bool = False


class RoleAssignment(BaseModel):
    """Maps a role to an agent within a workflow."""

    role: str
    agent: str
    description: str = ""
    is_primary: bool = False
    trust_level: str = "high"


class ReviewConfig(BaseModel):
    """Configuration for the review workflow."""

    enabled: bool = True
    checkpoints: list[str] = Field(default_factory=lambda: ["plan", "code"])
    pass_threshold: float = 7.0
    max_rounds: int = 3


class LayoutConfig(BaseModel):
    """tmux layout configuration."""

    primary_pane_width: str = "60%"


class WorkflowConfig(BaseModel):
    """Complete workflow definition."""

    name: str
    description: str = ""
    roles: list[RoleAssignment] = Field(default_factory=list)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    layout: LayoutConfig = Field(default_factory=LayoutConfig)


class SessionState(BaseModel):
    """Runtime state for an active workspace session."""

    session_id: str
    project_name: str
    project_dir: Path
    tmux_session: str
    workflow: str = "default"
    agents: dict[str, AgentState] = Field(default_factory=dict)
    created_at: str = ""


class AgentStatus(str, enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class AgentState(BaseModel):
    """Runtime state for a single agent within a session."""

    name: str
    role: str
    pane_id: str = ""
    pid: int = 0
    status: AgentStatus = AgentStatus.STOPPED
    log_path: str = ""


class Message(BaseModel):
    """Structured message between agents."""

    id: str
    timestamp: str
    session_id: str
    from_agent: str
    from_role: str
    to_agent: str
    to_role: str
    type: str  # review_request | review_response | query | response
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
