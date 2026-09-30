# Guía de desarrollo local

Este documento funciona como guía práctica para levantar y trabajar con la aplicación durante el desarrollo.

---

# 1. Iniciar el backend

## Requisitos

Tener instalado:

- Python 3.11 o superior
- Git

Verificar Python:

```powershell
python --version
```

## Windows

Desde una terminal, ubicarse en el repositorio y entrar al backend:

```powershell
cd backend
```

Crear el entorno virtual:

```powershell
python -m venv .venv
```

Activarlo en PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la ejecución de scripts, se puede usar CMD:

```cmd
.venv\Scripts\activate.bat
```

Instalar dependencias:

```powershell
pip install -e ".[dev]"
```

Copiar la configuración de ejemplo:

```powershell
Copy-Item .env.example .env
```

Crear o actualizar el esquema de la base con Alembic:

```powershell
alembic upgrade head
```

Iniciar FastAPI:

```powershell
uvicorn app.main:app --reload
```

## Linux / macOS

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

---

# 2. URLs útiles

Con el backend iniciado:

- API: http://localhost:8000
- Swagger / documentación interactiva: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health
- Metadata técnica: http://localhost:8000/api/v1/meta

---

# 3. Base de datos local

La primera etapa utiliza SQLite.

La configuración de ejemplo define:

```text
sqlite:///./data/libreria_ingles.db
```

La aplicación resuelve esa ruta siempre respecto de la carpeta `backend/`, independientemente del directorio desde el que se ejecute el proceso.

Por defecto la base queda en:

```text
backend/data/libreria_ingles.db
```

El esquema no se crea mediante `create_all()`.

Se administra mediante Alembic:

```powershell
alembic upgrade head
```

Consultar la versión aplicada:

```powershell
alembic current
```

---

# 4. Ejecutar tests

Desde `backend/`:

```powershell
pytest
```

Los tests configuran una SQLite en memoria y no utilizan la base local de desarrollo.

---

# 5. Detener el backend

En la terminal donde está ejecutándose:

```text
Ctrl + C
```

---

# 6. Próximos pasos de esta guía

Este documento se irá ampliando con:

- inicio del frontend Angular;
- creación de nuevas migraciones;
- variables de entorno;
- debugging;
- ejecución completa frontend + backend;
- futura configuración PostgreSQL;
- futura ejecución mediante contenedores.
