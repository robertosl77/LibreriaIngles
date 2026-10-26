# Inicio local en Windows (BAT)

Estos comandos replican el esquema de inicio de `MisAhorros/scripts`, adaptado a Librería Inglés.

## Inicio habitual (doble clic)

- `iniciar-todo.bat`: inicia **backend** y **frontend** en dos ventanas CMD independientes.
- `iniciar-backend.bat`: inicia solo la API FastAPI.
- `iniciar-frontend.bat`: inicia solo Angular; si falta `node_modules/.bin/ng.cmd`, ejecuta `npm ci` desde el lockfile antes de arrancar.

Los scripts funcionan desde cualquier carpeta, incluso si la ruta del repositorio contiene espacios. No necesitan que antes se active un entorno virtual o se abra VS Code.

**URLs:** frontend `http://localhost:4200`; API `http://127.0.0.1:8000`; salud `http://127.0.0.1:8000/api/v1/health`; Swagger `http://127.0.0.1:8000/docs`. El proxy de Angular ya apunta a `127.0.0.1:8000` en `frontend/proxy.conf.json`.

## Preparación inicial (una vez)

1. Instalar Python 3.11+ y Node.js 22.12+ con npm.
2. Crear `backend/.venv` e instalar dependencias según `docs/guia_desarrollo_backend.md` (desde `backend/`: `python -m venv .venv` y `.venv\Scripts\python.exe -m pip install -e ".[dev]"`).
3. Copiar `backend/.env.example` a `backend/.env` y completar las variables locales que correspondan. **No subir `.env` a Git.**
4. Con respaldo previo si hay datos que conservar, ejecutar desde `backend/`: `.venv\Scripts\python.exe -m alembic upgrade head`. Las migraciones son deliberadamente **manuales**, no se ejecutan con doble clic.
5. Ejecutar `scripts/iniciar-todo.bat`. El frontend instala automáticamente dependencias con `npm ci` si faltan. Si cambiaron `package.json` o `package-lock.json`, ejecutar `npm ci` manualmente antes de iniciar.

## Verificación

1. Comprobar que la ventana Backend informa `Uvicorn running` y que `/api/v1/health` responde.
2. Comprobar que la ventana Frontend informa `http://localhost:4200/` y que la aplicación abre.
3. Probar una llamada del frontend a `/api` para verificar el proxy.
4. `Ctrl+C` detiene cada servicio en su ventana. Cerrar una ventana no detiene el otro servicio.

## Errores típicos

- Falta `.venv` o `.env`: el backend explica qué preparar y no arranca.
- Falta npm: instalar Node.js y volver a abrir CMD para refrescar `PATH`.
- Falla `npm ci`: revisar red/Node y el `package-lock.json`.
- Puerto 8000 o 4200 ocupado: detener el proceso previo antes de relanzar.
- Es una facilidad de **desarrollo en Windows**: no reemplaza Docker, CI ni un despliegue de producción.

Consultar también `docs/guia_desarrollo_backend.md` y `docs/guia_desarrollo_frontend.md`.
