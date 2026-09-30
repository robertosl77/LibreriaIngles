# Guía de desarrollo local

Este documento funciona como guía práctica para levantar y trabajar con la aplicación durante el desarrollo.

---

# 1. Iniciar el backend

## Requisitos

Tener instalado:

- Python 3.12 o superior
- Git

## Windows

Desde una terminal, ubicarse en el repositorio y entrar al backend:

```powershell
cd backend
```

Crear el entorno virtual:

```powershell
python -m venv .venv
```

Activarlo:

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

En la configuración inicial se utiliza SQLite.

Al iniciar el backend por primera vez se crea:

```text
backend/data/libreria_ingles.db
```

La base se genera automáticamente durante esta primera etapa del proyecto.

Más adelante el esquema será manejado exclusivamente mediante Alembic y la base productiva prevista será PostgreSQL.

---

# 4. Detener el backend

En la terminal donde está ejecutándose:

```text
Ctrl + C
```

---

# 5. Próximos pasos de esta guía

Este documento se irá ampliando con:

- inicio del frontend Angular;
- creación y ejecución de migraciones;
- testing;
- variables de entorno;
- debugging;
- ejecución completa frontend + backend;
- futura configuración PostgreSQL;
- futura ejecución mediante contenedores.
