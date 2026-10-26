@echo off
setlocal
REM LibreriaIngles - arranque local de FastAPI en http://127.0.0.1:8000
title LibreriaIngles - Backend
pushd "%~dp0..\backend"
if errorlevel 1 (
  echo ERROR: no se pudo acceder a la carpeta backend.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta backend\.venv\Scripts\python.exe.
  echo Preparar el entorno siguiendo docs\guia_desarrollo_backend.md.
  popd
  pause
  exit /b 1
)
if not exist ".env" (
  echo ERROR: falta backend\.env.
  echo Copiar backend\.env.example a backend\.env y configurarlo.
  popd
  pause
  exit /b 1
)
echo Iniciando backend en http://127.0.0.1:8000 ...
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
set "resultado=%errorlevel%"
if not "%resultado%"=="0" echo ERROR: el backend finalizo con codigo %resultado%.
popd
pause
exit /b %resultado%
