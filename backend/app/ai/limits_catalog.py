"""T-220 (N-01) · Límites comerciales de la IA, declarados en el catálogo único."""

from app.limits.registry import LimitDefinition, define_limit

PERSON_DAILY_REQUESTS = define_limit(
    LimitDefinition(
        key="person_daily_requests",
        label="Pedidos de IA por persona por día",
        unit="pedidos / 24 h",
        description=(
            "Pedidos a la IA de la plataforma por persona en 24 h, sumando todas las conexiones "
            "(T-217). El dueño no tiene tope."
        ),
        default=None,
    )
)
