# Librería Inglés

Primera implementación de la plataforma de aprendizaje de inglés definida en los documentos funcionales del repositorio.

## Rama de desarrollo

La base técnica inicial se desarrolla en `feat/mvp-foundation-v0.1`. La rama `main` no se modifica directamente.

## Stack inicial

- Frontend: Angular
- Backend: Python + FastAPI
- Persistencia: SQLAlchemy
- Base local: SQLite
- Base prevista para producción: PostgreSQL

## Estructura

```text
frontend/   Angular
backend/    FastAPI + dominio + persistencia
```

Los prototipos HTML históricos permanecen como referencia, pero no forman parte de la nueva arquitectura.

## Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
# source .venv/bin/activate

pip install -e ".[dev]"
uvicorn app.main:app --reload
```

API: http://localhost:8000  
Swagger: http://localhost:8000/docs  
Health: http://localhost:8000/api/v1/health

La base SQLite se crea en `backend/data/libreria_ingles.db`.

## Frontend

```bash
cd frontend
npm install
npm start
```

Frontend: http://localhost:4200

## Alcance v0.1

- separación Angular / FastAPI;
- configuración por ambiente;
- SQLite detrás de SQLAlchemy;
- modelos iniciales de cuenta, organización, membresía, invitación y sesión de estudio;
- relación N:N entre cuentas y sesiones de estudio;
- branding básico por organización;
- endpoints de health/meta;
- landing inicial con caminos personal y organización.

Todavía no implementa autenticación real, pagos ni proveedores de IA.
