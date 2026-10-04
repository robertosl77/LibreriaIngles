from agent_dev_kit import ProjectConfig, ProjectStack, build_dev_agent_kit


def test_builds_only_enabled_specialists():
    config = ProjectConfig(
        name="Demo",
        stack=ProjectStack(
            backend=("Python", "FastAPI"),
            frontend=("Angular",),
            ui=("Bootstrap",),
        ),
        enabled_specialists=("backend", "frontend", "ux_ui"),
    )

    kit = build_dev_agent_kit(config)

    assert set(kit.specialists) == {"backend", "frontend", "ux_ui"}
    assert len(kit.triage_agent.handoffs) == 3
    assert all(agent.handoffs == [kit.triage_agent] for agent in kit.specialists.values())


def test_instructions_include_project_stack_and_guidelines():
    config = ProjectConfig(
        name="Demo",
        stack=ProjectStack(
            backend=("Python", "FastAPI"),
            database=("PostgreSQL",),
        ),
        enabled_specialists=("backend",),
        project_guidelines=("Use REST APIs.", "Reuse existing components."),
    )

    kit = build_dev_agent_kit(config)
    instructions = kit.specialists["backend"].instructions

    assert "Python, FastAPI" in instructions
    assert "PostgreSQL" in instructions
    assert "Use REST APIs." in instructions
    assert "Reuse existing components." in instructions


def test_rejects_unknown_specialist():
    config = ProjectConfig(
        name="Demo",
        stack=ProjectStack(),
        enabled_specialists=("unknown",),
    )

    try:
        build_dev_agent_kit(config)
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
