@echo off
setlocal
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERRO] backend\.venv nao existe.
  echo Execute 01_instalar_dependencias.bat na pasta principal.
  pause
  exit /b 1
)
cd /d "%~dp0.."
"%PY%" -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
