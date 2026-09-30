# Librería Inglés

Plataforma de aprendizaje adaptativo de inglés.

La implementación se guía por los documentos funcionales y técnicos incluidos en este repositorio.

## Rama de desarrollo actual

`fix/mvp-funcional` (sobre `feat/mvp-foundation-v0.1`)

La rama `main` no se modifica directamente durante el desarrollo.

## Stack inicial

- Frontend: Angular
- Backend: Python + FastAPI
- Persistencia: SQLAlchemy
- Migraciones: Alembic
- Base local: SQLite
- Base prevista para producción: PostgreSQL

## Estructura

```text
frontend/   Angular
backend/    FastAPI + dominio + persistencia
docs/       Guías prácticas de desarrollo
```

Los prototipos HTML históricos permanecen como referencia, pero no forman parte de la nueva arquitectura.

## Backend rápido

```bash
cd backend
python -m venv .venv
# activar .venv
pip install -e ".[dev]"
# copiar .env.example a .env
alembic upgrade head
uvicorn app.main:app --reload
```

API: http://localhost:8000  
Swagger: http://localhost:8000/docs

Guías:

- `docs/guia_desarrollo_backend.md` — preparar y levantar el backend.
- `docs/guia_desarrollo_frontend.md` — preparar y levantar el frontend.
- `docs/guia_mvp_funcional.md` — configurar login, IA y probar el flujo completo.

## Estado v0.1

La base actual incluye:

- separación Angular / FastAPI;
- configuración por ambiente;
- SQLite detrás de SQLAlchemy;
- Alembic como mecanismo de esquema desde el inicio;
- ruta SQLite estable respecto de `backend/`;
- modelos iniciales de cuenta, organización, membresía, invitación y sesión de estudio;
- identificación estable de Google mediante `google_subject`;
- invitaciones con token hasheado y expiración;
- relación N:N entre cuentas y sesiones de estudio;
- branding básico por organización;
- endpoints de health/meta;
- landing inicial.

## Estado MVP funcional

Sobre esa base, la app ya se puede usar de punta a punta con una cuenta personal:

- login con Google (y login de desarrollo en local);
- elección de nivel y currícula A1 como datos;
- conexiones de IA propias (OpenAI, Gemini, Anthropic) con failover y backoff;
- clases generadas por IA, autoguardado, evaluación híbrida, apelación y rehacer;
- progreso por skill, dashboard e historial.

Detalle, configuración y pendientes: `docs/guia_mvp_funcional.md`.

Todavía no implementa organizaciones/ADMIN, pagos, audio ni niveles A2–C2.
