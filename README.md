# Librería Inglés

Plataforma de aprendizaje adaptativo de inglés.

La implementación se guía por los documentos funcionales y técnicos incluidos en este repositorio.

## Flujo de Ramas (Branching Workflow)

El proyecto sigue un flujo de ramas estructurado con las siguientes reglas:

### Ramas principales

| Rama | Rol | Protección |
|------|-----|------------|
| `main` | Rama de **producción**. Contiene únicamente código estable y listo para release. | **Protegida** — no se permiten escrituras directas. |
| `develop` | Rama de **integración**. Aquí se consolidan todas las funcionalidades antes de un release. | **Protegida** — no se permiten escrituras directas. |

### Ramas de tarea

Cada tarea o corrección se trabaja en una rama dedicada creada **a partir de `develop`**, siguiendo la convención de nombres:

```
{kind}/{issue}-{slug}
```

Ejemplos: `feat/T-042-crud-libros`, `fix/T-066-readme-workflow`.

### Flujo de trabajo

1. **Crear la rama de tarea** desde `develop` (asegurarse de que `develop` esté actualizado).
2. **Desarrollar** los cambios en la rama de tarea.
3. **Abrir un Pull Request** con destino a `develop`.
   - El PR **debe referenciar el issue** correspondiente (e.g., `T-066`).
   - La rama de tarea debe estar actualizada con `develop` antes de fusionar.
4. **Revisión y merge** a `develop`.
5. **Release**: cuando `develop` está listo para producción, se abre un PR de `develop` → `main`.

### Reglas importantes

- **No se permite escribir directamente** en `main` ni en `develop` (salvo autorización humana explícita).
- Toda modificación llega a las ramas protegidas exclusivamente mediante Pull Requests.
- Antes de crear una rama de tarea, se debe sincronizar con la última versión de `develop`.

## Terminología de negocio

Para evitar ambigüedades entre conceptos comerciales y modelos técnicos, el proyecto usa esta nomenclatura:

| Término | Significado | Ejemplos / notas |
|---|---|---|
| **Servicio** | Fila del modelo de negocio: qué tipo de servicio se ofrece. | Hoy: `PERSONAL`, `CORPORATE`. Debe poder evolucionar a futuros tipos sin duplicar motores. |
| **Fuente IA** | Columna del modelo: de dónde salen las conexiones de IA permitidas para ese servicio. | `BYOK`, `PLATFORM`, `HYBRID`. |
| **Membresía comercial** | Intersección **Servicio × Fuente IA**. Describe una combinación comercial habilitable. | Ej.: `CORPORATE × HYBRID`. No representa una persona dentro de una empresa. |
| **Suscripción / Contrato** | Instancia efectiva que habilita una membresía comercial durante una vigencia y bajo condiciones económicas. | Puede incluir pago, renovación, seats/licencias, cuotas de asistencias IA, excedentes y otros entitlements. |
| **OrganizationMembership** | Vínculo entre una `Account` y una `Organization`, con rol y estado dentro de esa organización. | Ej.: Roberto pertenece a Kakatua como `ADMIN`; otra persona pertenece como `STUDENT`. |
| **Tenant** | Contexto aislado de una organización dentro de la misma aplicación. | Kakatua es un tenant: sus personas, datos, branding, campañas, conexiones y reportes no se mezclan con otra organización. |
| **Onboarding** | Flujo guiado de alta y configuración inicial. | En B2B: desde “Crear empresa” hasta dejar la organización operativa. |

### Regla de nomenclatura

En conversaciones de producto, **membresía** refiere a la combinación `Servicio × Fuente IA`. El modelo técnico histórico `Membership` representa actualmente el vínculo cuenta ↔ organización; cuando se trabaje esa capa se debe evaluar renombrarlo a `OrganizationMembership` para evitar la colisión semántica.

La arquitectura debe privilegiar configuración/catálogos/capacidades sobre condicionales hardcodeados por tipo de cliente. Persona, empresa o futuros contextos (por ejemplo universidad) deben reutilizar los mismos motores base cuando la responsabilidad sea la misma.

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
