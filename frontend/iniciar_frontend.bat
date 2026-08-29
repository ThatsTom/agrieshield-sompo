@echo off
setlocal
cd /d "%~dp0"
if not exist "node_modules\.bin\vite.cmd" (
  echo [ERRO] Vite local nao encontrado.
  echo Execute 01_instalar_dependencias.bat ou 06_reinstalar_frontend.bat.
  pause
  exit /b 1
)
call npm run dev
