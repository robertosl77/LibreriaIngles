from agent_dev_kit import ProjectConfig, ProjectStack, build_dev_agent_kit


def test_conversation_starts_at_triage():
    config = ProjectConfig(
        name="Demo",
        stack=ProjectStack(),
        enabled_specialists=("backend",),
    )
    kit = build_dev_agent_kit(config)

    conversation = kit.conversation()

    assert conversation.current_agent_name == "Dev Triage"


def test_reset_route_returns_to_triage():
    config = ProjectConfig(
        name="Demo",
        stack=ProjectStack(),
        enabled_specialists=("backend",),
    )
    kit = build_dev_agent_kit(config)
    conversation = kit.conversation()

    conversation.active_agent = kit.specialists["backend"]
    assert conversation.current_agent_name == "Backend Specialist"

    conversation.reset_route()

    assert conversation.current_agent_name == "Dev Triage"
