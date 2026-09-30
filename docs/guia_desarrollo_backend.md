# Librería Inglés — Guía de desarrollo local

**Objetivo:** documentar cómo preparar y levantar el proyecto durante el desarrollo, comenzando por el backend.

Esta guía refleja el flujo probado en Windows con Visual Studio Code.

---

# 1. Requisitos

Para el backend se necesita:

- Python 3.11 o superior;
- Git;
- Visual Studio Code;
- extensión **Python** de VS Code.

Verificar la versión de Python:

```powershell
python --version
```

La versión mínima configurada actualmente por el proyecto es:

```text
Python 3.11
```

Python 3.12 también funciona.

---

# 2. Preparación inicial del backend

Estos pasos se realizan la primera vez que se clona el repositorio o cuando se necesita reconstruir el entorno virtual.

Desde la raíz del repositorio:

```powershell
cd backend
```

## 2.1 Crear el entorno virtual

```powershell
python -m venv .venv
```

## 2.2 Activar el entorno virtual

En PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

La terminal debería pasar a mostrar algo similar a:

```text
(.venv) PS ...\LibreriaIngles\backend>
```

Si PowerShell impide ejecutar el script, puede activarse desde CMD:

```cmd
.venv\Scripts\activate.bat
```

---

# 3. Instalar las dependencias

Con el entorno virtual activo y parado dentro de `backend/`:

```powershell
pip install -e ".[dev]"
```

La opción `-e` instala el backend en modo editable. Esto permite modificar el código sin reinstalar el paquete después de cada cambio.

Las dependencias de desarrollo incluyen, entre otras:

- pytest;
- httpx.

Alembic forma parte de las dependencias principales porque las migraciones forman parte del funcionamiento normal de la aplicación.

---

# 4. Configuración local

Crear el archivo local `.env` a partir del ejemplo:

```powershell
Copy-Item .env.example .env
```

El archivo `.env` no se versiona en Git.

La configuración inicial utiliza SQLite:

```text
DATABASE_URL=sqlite:///./data/libreria_ingles.db
```

La aplicación resuelve esta ruta respecto de la carpeta `backend/`, por lo que la base queda siempre en:

```text
backend/data/libreria_ingles.db
```

independientemente de la carpeta desde la que se lance el proceso.

---

# 5. Crear o actualizar la base de datos

El esquema se administra con Alembic.

Desde `backend/`:

```powershell
alembic upgrade head
```

La primera ejecución correcta muestra algo similar a:

```text
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema, Initial schema.
```

Consultar la migración aplicada:

```powershell
alembic current
```

La aplicación **no** utiliza `Base.metadata.create_all()` para crear el esquema. Las modificaciones estructurales deben quedar registradas como migraciones Alembic.

---

# 6. Iniciar el backend manualmente

Con el entorno virtual activo y dentro de `backend/`:

```powershell
uvicorn app.main:app --reload
```

Una ejecución correcta muestra:

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

Para detener el backend:

```text
Ctrl + C
```

---

# 7. Iniciar el backend desde VS Code con F5

El repositorio incluye:

```text
.vscode/
├── launch.json
└── tasks.json
```

La configuración disponible se llama:

```text
Librería Inglés - Backend
```

## 7.1 Qué hace el launch

Al iniciar el launch, VS Code ejecuta automáticamente:

```text
1. backend/.venv/Scripts/python.exe -m alembic upgrade head
2. backend/.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Por lo tanto, para el uso habitual no es necesario ejecutar manualmente:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload
```

El launch apunta directamente al Python del entorno virtual del backend.

## 7.2 Cómo ejecutarlo

Abrir en VS Code **la raíz del repositorio `LibreriaIngles`**, no solamente la carpeta `backend`.

Luego:

1. abrir **Run and Debug**;
2. seleccionar **Librería Inglés - Backend**;
3. presionar **F5**.

Antes de levantar Uvicorn se ejecuta el task:

```text
Backend - Alembic upgrade
```

De esta forma cada arranque verifica primero que la base esté actualizada a la última migración disponible.

## 7.3 Primera ejecución

El launch supone que ya existe:

```text
backend/.venv/
```

y que ya se ejecutó al menos:

```powershell
pip install -e ".[dev]"
```

Si el entorno virtual no existe, primero realizar los pasos de preparación inicial de esta guía.

---

# 8. URLs útiles

Con el backend iniciado:

## API

```text
http://127.0.0.1:8000
```

## Swagger

```text
http://127.0.0.1:8000/docs
```

`/docs` es la documentación interactiva generada automáticamente por FastAPI.

Permite:

- ver los endpoints disponibles;
- inspeccionar parámetros y respuestas;
- ejecutar requests directamente desde el navegador mediante **Try it out**.

Actualmente pueden verse, entre otros:

```text
GET /
GET /api/v1/health
GET /api/v1/meta
```

## ReDoc

```text
http://127.0.0.1:8000/redoc
```

Es una segunda visualización automática de la documentación OpenAPI.

## Health check

```text
http://127.0.0.1:8000/api/v1/health
```

## Metadata

```text
http://127.0.0.1:8000/api/v1/meta
```

---

# 9. Flujo habitual de trabajo

Una vez preparado el entorno, el flujo recomendado es:

```text
Abrir LibreriaIngles en VS Code
        ↓
actualizar la rama de trabajo
        ↓
Run and Debug
        ↓
Librería Inglés - Backend
        ↓
F5
        ↓
Alembic upgrade head automático
        ↓
Uvicorn / FastAPI
```

Si cambian las dependencias de `pyproject.toml`, ejecutar nuevamente:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

---

# 10. Ejecutar tests

Desde `backend/`, con el entorno virtual activo:

```powershell
pytest
```

Los tests utilizan una SQLite en memoria y no deben escribir sobre:

```text
backend/data/libreria_ingles.db
```

---

# 11. Problemas encontrados durante la preparación inicial

## 11.1 Multiple top-level packages discovered

Durante la primera instalación apareció:

```text
Multiple top-level packages discovered in a flat-layout:
['app', 'migrations']
```

El problema era el descubrimiento automático de paquetes de setuptools.

La configuración correcta ya quedó incorporada en `backend/pyproject.toml`:

```toml
[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["migrations*", "tests*"]
```

No hay que agregar nuevamente esta sección de forma manual.

---

## 11.2 Cannot declare ... packages.find twice

Si aparece:

```text
Cannot declare ('tool', 'setuptools', 'packages', 'find') twice
```

significa que `pyproject.toml` tiene duplicada la sección:

```toml
[tool.setuptools.packages.find]
```

Esto puede ocurrir si se aplicó manualmente una corrección que luego también llegó desde Git.

Estando dentro de `backend/`, revisar cambios locales con:

```powershell
git diff -- pyproject.toml
```

Desde la raíz del repositorio sería:

```powershell
git diff -- backend/pyproject.toml
```

Para localizar las apariciones desde `backend/`:

```powershell
Select-String -Path pyproject.toml -Pattern "\[tool\.setuptools\.packages\.find\]"
```

Debe existir una sola.

---

## 11.3 Alembic y rutas de Windows con E%3A

En Windows, SQLAlchemy puede representar una ruta como:

```text
E:/...
```

dentro de una URL como:

```text
E%3A/...
```

Alembic utiliza internamente `ConfigParser`, donde el carácter `%` tiene significado de interpolación.

El síntoma era:

```text
ValueError: invalid interpolation syntax in
'sqlite:///E%3A/...'
```

El proyecto ya contiene el fix en `migrations/env.py`: antes de pasar la URL a Alembic, los porcentajes se escapan como `%%`.

También existe un test específico para evitar que este caso vuelva a romperse.

---

# 12. Estado confirmado

El flujo fue probado correctamente en Windows con:

```text
alembic upgrade head
→ Running upgrade -> 0001_initial_schema

uvicorn app.main:app --reload
→ Application startup complete.
```

Por lo tanto, la base inicial del backend queda operativa con:

- Python;
- entorno virtual;
- FastAPI;
- Uvicorn;
- SQLAlchemy;
- SQLite;
- Alembic;
- launch de VS Code.
