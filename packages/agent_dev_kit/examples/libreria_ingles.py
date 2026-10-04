import asyncio

from agents import SQLiteSession

from agent_dev_kit import ProjectConfig, ProjectStack, build_dev_agent_kit


async def main() -> None:
    config = ProjectConfig(
        name="Librería Inglés",
        stack=ProjectStack(
            backend=("Python", "FastAPI", "SQLAlchemy"),
            frontend=("Angular",),
            ui=("Bootstrap",),
            database=("SQLite", "PostgreSQL"),
        ),
        project_guidelines=(
            "Reuse existing components and project conventions before creating new ones.",
            "Keep development-agent concerns separate from English-learning domain agents.",
        ),
    )

    kit = build_dev_agent_kit(config)
    conversation = kit.conversation(
        session=SQLiteSession("libreria-ingles-development")
    )

    result = await conversation.ask(
        "El botón funciona, pero visualmente no es consistente con el resto de la página."
    )

    print(f"Answered by: {result.last_agent.name}")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
