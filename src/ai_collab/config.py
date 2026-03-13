"""Configuration loading: global defaults + per-project overrides."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .models import AgentConfig, WorkflowConfig, RoleAssignment, ReviewConfig

GLOBAL_CONFIG_DIR = Path.home() / ".ai-collab"
PROJECT_CONFIG_DIR_NAME = ".ai-collab"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, return empty dict if not found."""
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def get_global_config_dir() -> Path:
    return GLOBAL_CONFIG_DIR


def get_project_config_dir(project_dir: Path) -> Path:
    return project_dir / PROJECT_CONFIG_DIR_NAME


def load_agent_configs(project_dir: Path | None = None) -> dict[str, AgentConfig]:
    """Load agent configs: global defaults, then project overrides."""
    agents: dict[str, AgentConfig] = {}

    # Global agents
    global_agents_dir = GLOBAL_CONFIG_DIR / "agents"
    if global_agents_dir.exists():
        for f in sorted(global_agents_dir.glob("*.toml")):
            data = _load_toml(f)
            if "agent" in data:
                agent = AgentConfig(**data["agent"])
                agents[agent.name] = agent

    # Project-level overrides
    if project_dir:
        proj_agents_dir = get_project_config_dir(project_dir) / "agents"
        if proj_agents_dir.exists():
            for f in sorted(proj_agents_dir.glob("*.toml")):
                data = _load_toml(f)
                if "agent" in data:
                    agent = AgentConfig(**data["agent"])
                    agents[agent.name] = agent

    return agents


def load_workflow_config(
    workflow_name: str = "default", project_dir: Path | None = None
) -> WorkflowConfig:
    """Load workflow config: check project first, then global."""
    # Project-level workflow
    if project_dir:
        proj_path = get_project_config_dir(project_dir) / "workflows" / f"{workflow_name}.toml"
        if proj_path.exists():
            return _parse_workflow(_load_toml(proj_path))

    # Global workflow
    global_path = GLOBAL_CONFIG_DIR / "workflows" / f"{workflow_name}.toml"
    if global_path.exists():
        return _parse_workflow(_load_toml(global_path))

    # Built-in default
    return _default_workflow()


def _parse_workflow(data: dict[str, Any]) -> WorkflowConfig:
    """Parse a workflow TOML into WorkflowConfig."""
    wf = data.get("workflow", {})
    roles = [RoleAssignment(**r) for r in wf.get("roles", [])]
    review = ReviewConfig(**wf.get("review", {})) if "review" in wf else ReviewConfig()
    return WorkflowConfig(
        name=wf.get("name", "custom"),
        description=wf.get("description", ""),
        roles=roles,
        review=review,
    )


def _default_workflow() -> WorkflowConfig:
    """Built-in default workflow when no config files exist."""
    return WorkflowConfig(
        name="default",
        description="Standard three-model collaboration",
        roles=[
            RoleAssignment(role="designer", agent="claude", description="Primary architect", is_primary=True),
            RoleAssignment(role="reviewer", agent="codex", description="Code reviewer"),
            RoleAssignment(role="inspiration", agent="gemini", description="Creative ideas", trust_level="low"),
        ],
    )


def ensure_global_config():
    """Create global config directory and default configs if they don't exist."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (GLOBAL_CONFIG_DIR / "agents").mkdir(exist_ok=True)
    (GLOBAL_CONFIG_DIR / "workflows").mkdir(exist_ok=True)
