"""T-220 · Raíz de composición de tareas: importa los módulos que las registran.

Igual que `app/api.py` con los routers: es el único lugar que conoce a todos. Sacar un módulo del
producto = sacar su línea de acá.
"""

import app.campaigns.jobs  # noqa: F401
import app.classes.jobs  # noqa: F401
import app.subscriptions.jobs  # noqa: F401
