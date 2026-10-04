from dataclasses import dataclass, field
from typing import Mapping

DEFAULT_SPECIALISTS = (
    "architecture",
    "backend",
    "frontend",
    "ux_ui",
    "security",
    "testing",
    "documentation",
    "reviewer",
)


@dataclass(slots=True)
class ProjectStack:
    backend: tuple[str, ...] = ()
    frontend: tuple[str, ...] = ()
    ui: tuple[str, ...] = ()
    database: tuple[str, ...] = ()
    infrastructure: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()

    def summary(self) -> str:
        groups = (
            ("Backend", self.backend),
            ("Frontend", self.frontend),
            ("UI", self.ui),
            ("Database", self.database),
            ("Infrastructure", self.infrastructure),
            ("Extra", self.extra),
        )
        rendered = [
            f"{label}: {', '.join(values)}"
            for label, values in groups
            if values
        ]
        return "\n".join(rendered) if rendered else "Stack not specified."


@dataclass(slots=True)
class ProjectConfig:
    name: str
    stack: ProjectStack
    enabled_specialists: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_SPECIALISTS
    )
    default_model: str | None = None
    specialist_models: Mapping[str, str] = field(default_factory=dict)
    project_guidelines: tuple[str, ...] = ()

    def model_for(self, specialist_key: str) -> str | None:
        return self.specialist_models.get(specialist_key, self.default_model)

    def guidelines_text(self) -> str:
        if not self.project_guidelines:
            return "No additional project-specific guidelines."
        return "\n".join(f"- {item}" for item in self.project_guidelines)
