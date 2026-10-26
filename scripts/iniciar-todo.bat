@echo off
REM LibreriaIngles - abre backend y frontend en dos ventanas independientes.
REM /D fija la carpeta de scripts; funciona aunque el repositorio tenga espacios.
start "LibreriaIngles - Backend" /D "%~dp0" cmd.exe /k "call iniciar-backend.bat"
start "LibreriaIngles - Frontend" /D "%~dp0" cmd.exe /k "call iniciar-frontend.bat"
