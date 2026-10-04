from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpecialistSpec:
    key: str
    name: str
    handoff_description: str
    responsibility: str


BASE_SPECIALISTS: dict[str, SpecialistSpec] = {
    "architecture": SpecialistSpec(
        key="architecture",
        name="Architecture Specialist",
        handoff_description="Use for architecture, boundaries, integration patterns, tradeoffs, and system-wide technical decisions.",
        responsibility=(
            "Own software architecture decisions, component boundaries, integration patterns, "
            "non-functional tradeoffs, and consistency across the system."
        ),
    ),
    "backend": SpecialistSpec(
        key="backend",
        name="Backend Specialist",
        handoff_description="Use for APIs, services, business logic, persistence, backend frameworks, and server-side debugging.",
        responsibility=(
            "Own backend implementation, APIs, service logic, persistence integration, "
            "server-side performance, and backend framework conventions."
        ),
    ),
    "frontend": SpecialistSpec(
        key="frontend",
        name="Frontend Specialist",
        handoff_description="Use for frontend application code, components, state, browser behavior, Angular, React, or similar frameworks.",
        responsibility=(
            "Own frontend application structure, components, state, browser behavior, "
            "framework conventions, and client-side integration."
        ),
    ),
    "ux_ui": SpecialistSpec(
        key="ux_ui",
        name="UX/UI Specialist",
        handoff_description="Use for interaction design, visual consistency, accessibility, responsive layout, design systems, Bootstrap, Tailwind, or UI components.",
        responsibility=(
            "Own interaction design, visual consistency, accessibility, responsive behavior, "
            "design-system reuse, and UI framework conventions."
        ),
    ),
    "security": SpecialistSpec(
        key="security",
        name="Security Specialist",
        handoff_description="Use for authentication, authorization, secrets, threat review, secure defaults, and security-sensitive changes.",
        responsibility=(
            "Own security review, authentication and authorization concerns, secrets handling, "
            "threat analysis, secure defaults, and abuse-resistant design."
        ),
    ),
    "testing": SpecialistSpec(
        key="testing",
        name="Testing Specialist",
        handoff_description="Use for test strategy, automated tests, regression coverage, fixtures, edge cases, and validation.",
        responsibility=(
            "Own test strategy, automated coverage, regression prevention, edge cases, "
            "fixtures, and validation of expected behavior."
        ),
    ),
    "documentation": SpecialistSpec(
        key="documentation",
        name="Documentation Specialist",
        handoff_description="Use for technical documentation, setup guides, architecture notes, runbooks, and keeping docs synchronized with code.",
        responsibility=(
            "Own technical documentation, setup and operational guides, architecture notes, "
            "and keeping written project knowledge synchronized with implementation."
        ),
    ),
    "reviewer": SpecialistSpec(
        key="reviewer",
        name="Reviewer Specialist",
        handoff_description="Use for cross-cutting review of proposed or completed changes, consistency checks, regressions, and maintainability.",
        responsibility=(
            "Review changes across domains for correctness, regressions, maintainability, "
            "consistency with project rules, and missing follow-up work."
        ),
    ),
}
