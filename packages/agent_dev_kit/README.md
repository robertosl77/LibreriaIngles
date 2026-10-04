# Agent Dev Kit

Paquete reutilizable para proyectos de desarrollo, construido sobre **OpenAI Agents SDK**.

## Objetivo

Separar los especialistas de desarrollo de la lógica de negocio de cada aplicación. Un proyecto configura su stack y habilita únicamente los especialistas que necesita.

Especialistas base de v0.1:

- arquitectura;
- backend;
- frontend;
- UX/UI;
- seguridad;
- testing;
- documentación;
- reviewer.

## Instalación local

Desde la raíz del repositorio:

```bash
python -m pip install -e "packages/agent_dev_kit[dev]"
```

Para ejecutar llamadas reales:

```bash
export OPENAI_API_KEY="..."
```

## Configuración

```python
from agent_dev_kit import ProjectConfig, ProjectStack, build_dev_agent_kit

config = ProjectConfig(
    name="Mi aplicación",
    stack=ProjectStack(
        backend=("Python", "FastAPI"),
        frontend=("Angular",),
        ui=("Bootstrap",),
        database=("PostgreSQL",),
    ),
    enabled_specialists=(
        "architecture",
        "backend",
        "frontend",
        "ux_ui",
        "testing",
    ),
)

kit = build_dev_agent_kit(config)
```

La tecnología se configura por proyecto. No hace falta crear otro framework para Spring Boot, React, Tailwind, etc.

## Conversación con handoff persistente

```python
from agents import SQLiteSession

conversation = kit.conversation(
    session=SQLiteSession("mi-proyecto-dev")
)

result = conversation.ask_sync(
    "El botón funciona, pero visualmente no coincide con el resto."
)

print(result.last_agent.name)
print(result.final_output)
```

El primer mensaje entra por **Dev Triage**. Después del handoff, el siguiente mensaje comienza directamente con el especialista que quedó activo. Si el tema cambia, ese especialista puede devolver el control a Dev Triage.

Esto evita mantener al orquestador en el medio de todas las preguntas.

## Modelos

El SDK decide su modelo por defecto si no se configura ninguno.

También puede definirse por proyecto:

```python
config = ProjectConfig(
    name="Mi aplicación",
    stack=ProjectStack(),
    default_model="...",
    specialist_models={
        "triage": "...",
        "security": "...",
    },
)
```

El framework no impone un mismo modelo para todos los especialistas.

## Decisiones permanentes del proyecto

Los especialistas reciben una regla explícita: las decisiones duraderas no deben quedar únicamente en la conversación.

Ejemplos:

- componentes reutilizables;
- design tokens;
- convenciones del backend;
- decisiones de arquitectura;
- reglas de testing;
- documentación técnica.

Deben quedar persistidas en código, configuración, tests o documentación del proyecto.

## Alcance de v0.1

Incluido:

- especialistas generales;
- stack configurable;
- handoffs;
- retorno al triage cuando cambia el dominio;
- conservación del especialista activo entre turnos;
- sesión opcional mediante las sesiones del Agents SDK;
- modelos configurables por especialista.

No incluido todavía:

- agentes propios del dominio Inglés (M-002);
- ejecución automática contra repositorios;
- herramientas de GitHub/MCP;
- sandbox de código;
- agregación paralela de varios especialistas sobre una misma consulta;
- publicación del paquete en un registry.

