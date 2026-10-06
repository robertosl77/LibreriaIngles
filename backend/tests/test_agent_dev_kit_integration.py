from importlib.metadata import version
from pathlib import Path

from agent_dev_kit.project_config import load_project_config


def test_agent_dev_kit_v010_is_integrated():
    project_root = Path(__file__).resolve().parents[2]

    config = load_project_config(project_root)

    assert version("agent-dev-kit") == "0.2.0"
    assert config.name == "LibreriaIngles"
    assert config.provider.provider == "anthropic"
    assert config.git_workflow.integration_branch == "develop"
    assert config.git_workflow.production_branch == "main"
    assert "triage" in config.enabled_agents
    assert "backend" in config.enabled_agents
    assert "frontend" in config.enabled_agents
    assert config.orchestration.trace_enabled is True
