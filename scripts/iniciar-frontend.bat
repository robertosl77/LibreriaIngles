@echo off
setlocal
REM LibreriaIngles - arranque local de Angular en http://localhost:4200
title LibreriaIngles - Frontend
pushd "%~dp0..\frontend"
if errorlevel 1 (
  echo ERROR: no se pudo acceder a la carpeta frontend.
  pause
  exit /b 1
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo ERROR: no se encontro npm. Instalar Node.js 22.12+ y npm.
  popd
  pause
  exit /b 1
)
if not exist "node_modules\.bin\ng.cmd" (
  echo Faltan las dependencias del frontend. Ejecutando npm ci...
  call npm ci
  if errorlevel 1 (
    echo ERROR: npm ci fallo. Revisar Node.js, conexion y frontend\package-lock.json.
    popd
    pause
    exit /b 1
  )
)
echo Iniciando frontend en http://localhost:4200 ...
call npm start
set "resultado=%errorlevel%"
if not "%resultado%"=="0" echo ERROR: el frontend finalizo con codigo %resultado%.
popd
pause
exit /b %resultado%
