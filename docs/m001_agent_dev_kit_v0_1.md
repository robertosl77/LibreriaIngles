# M-001 — Agent Dev Kit v0.1

## Objetivo

Crear un paquete independiente y reutilizable de agentes especialistas para acompañar el desarrollo de aplicaciones.

## Decisión de arquitectura

La primera versión usa el **OpenAI Agents SDK para Python** y el patrón de **handoffs**.

Flujo normal:

```text
usuario
  ↓
Dev Triage
  ↓ handoff
especialista
  ↓
especialista mantiene la conversación
```

Si cambia el tema:

```text
especialista
  ↓ handoff
Dev Triage
  ↓
nuevo especialista
```

El objetivo es evitar una llamada al orquestador en cada turno.

## Separación respecto del producto

`packages/agent_dev_kit` contiene únicamente agentes de desarrollo reutilizables.

Los futuros agentes especializados en enseñanza de inglés corresponden a M-002 y deben vivir en el dominio de Librería Inglés.

## Especialistas iniciales

- Architecture Specialist
- Backend Specialist
- Frontend Specialist
- UX/UI Specialist
- Security Specialist
- Testing Specialist
- Documentation Specialist
- Reviewer Specialist

## Configuración por proyecto

Cada aplicación declara:

- stack backend;
- stack frontend;
- framework de UI;
- base de datos;
- infraestructura;
- especialistas activos;
- modelo por defecto;
- excepciones de modelo por especialista;
- reglas particulares del proyecto.

Por eso el paquete puede servir para combinaciones diferentes, por ejemplo:

```text
Python + FastAPI + Angular + Bootstrap
Spring Boot + React + Tailwind
```

sin duplicar el framework.

## Persistencia de conversación

La clase `DevConversation` conserva el último agente activo. Las sesiones del Agents SDK pueden agregarse para conservar el historial entre runs.

## Evoluciones posteriores

- herramientas para leer/modificar repositorios;
- integración GitHub/MCP;
- SandboxAgent para tareas reales de código;
- guardrails;
- ejecución coordinada de múltiples especialistas cuando una consulta abarque varios dominios;
- empaquetado/publicación fuera del repositorio Librería Inglés.

