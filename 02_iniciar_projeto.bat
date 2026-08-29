@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
cls

echo ============================================================
echo AgriShield - 02 - INICIAR PROJETO
echo ============================================================

if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo [ERRO] Backend ainda nao foi instalado.
  echo Execute 01_instalar_dependencias.bat primeiro.
  pause
  exit /b 1
)
if not exist "%ROOT%frontend\node_modules\.bin\vite.cmd" (
  echo [ERRO] Frontend ainda nao foi instalado ou o Vite esta faltando.
  echo Execute 01_instalar_dependencias.bat ou 06_reinstalar_frontend.bat.
  pause
  exit /b 1
)

start "AgriShield API - FastAPI" "%ComSpec%" /k call "%ROOT%backend\iniciar_backend.bat"
start "AgriShield Frontend - React" "%ComSpec%" /k call "%ROOT%frontend\iniciar_frontend.bat"

echo.
echo Aguardando os servidores iniciarem...
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:5173"

echo.
echo Frontend: http://127.0.0.1:5173
echo API:      http://127.0.0.1:8000
echo Swagger:  http://127.0.0.1:8000/docs
echo.
echo Para encerrar, feche as duas janelas de servidor ou pressione Ctrl+C nelas.
pause
