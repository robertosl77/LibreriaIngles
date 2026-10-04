from agents import Agent

from .config import ProjectConfig
from .runtime import DevAgentKit
from .specialists import BASE_SPECIALISTS, SpecialistSpec


def _specialist_instructions(spec: SpecialistSpec, config: ProjectConfig) -> str:
    return f"""You are the {spec.name} for project '{config.name}'.

Responsibility:
{spec.responsibility}

Project stack:
{config.stack.summary()}

Project-specific guidelines:
{config.guidelines_text()}

Working rules:
- Stay focused on your responsibility and the configured project stack.
- Prefer the project's existing patterns and reusable abstractions over inventing duplicates.
- Treat project-wide decisions as durable project knowledge: recommend storing them in code, configuration, tests, or documentation rather than relying only on chat memory.
- If the user's request moves outside your responsibility, hand control back to Dev Triage instead of improvising as another specialist.
- Keep answers and proposed changes proportional to the request.
"""


def _triage_instructions(config: ProjectConfig) -> str:
    enabled = ", ".join(config.enabled_specialists)
    return f"""You are Dev Triage for project '{config.name}'.

Your primary job is routing, not solving specialist work yourself.

Enabled specialists:
{enabled}

Project stack:
{config.stack.summary()}

Routing rules:
- Hand off to the specialist whose responsibility best matches the user's current request.
- If the user changes topic later, the active specialist can hand control back to you and you route again.
- For a request containing multiple domains, route first to the domain that owns the primary problem. The specialist may return control for the next domain when needed.
- Do not involve specialists that are unrelated to the request.
- Prefer handoffs over keeping yourself in the middle of every conversational turn.
"""


def build_dev_agent_kit(config: ProjectConfig) -> DevAgentKit:
    unknown = [
        key for key in config.enabled_specialists
        if key not in BASE_SPECIALISTS
    ]
    if unknown:
        raise ValueError(
            "Unknown specialist keys: " + ", ".join(sorted(unknown))
        )

    specialists: dict[str, Agent] = {}
    for key in config.enabled_specialists:
        spec = BASE_SPECIALISTS[key]
        kwargs = {
            "name": spec.name,
            "handoff_description": spec.handoff_description,
            "instructions": _specialist_instructions(spec, config),
        }
        model = config.model_for(key)
        if model:
            kwargs["model"] = model
        specialists[key] = Agent(**kwargs)

    triage_kwargs = {
        "name": "Dev Triage",
        "instructions": _triage_instructions(config),
        "handoffs": list(specialists.values()),
    }
    triage_model = config.model_for("triage")
    if triage_model:
        triage_kwargs["model"] = triage_model

    triage = Agent(**triage_kwargs)

    # A specialist keeps the conversation until the topic changes. Returning
    # to triage avoids paying for an orchestration hop on every normal turn.
    for specialist in specialists.values():
        specialist.handoffs = [triage]

    return DevAgentKit(
        config=config,
        triage_agent=triage,
        specialists=specialists,
    )
