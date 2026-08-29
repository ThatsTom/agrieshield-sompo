@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
cls

echo ============================================================
echo AgriShield - 04 - VERIFICAR INSTALACAO
echo ============================================================
set "FALHA=0"

if exist "%ROOT%backend\.venv\Scripts\python.exe" (
  "%ROOT%backend\.venv\Scripts\python.exe" -V
  "%ROOT%backend\.venv\Scripts\python.exe" -c "import dotenv,ee,fastapi,httpx,uvicorn,pydantic,requests,pandas,numpy; print('[OK] imports Python'); print('FastAPI',fastapi.__version__,'HTTPX',httpx.__version__,'Pandas',pandas.__version__,'NumPy',numpy.__version__)"
  if errorlevel 1 set "FALHA=1"
  cd /d "%ROOT%"
  "%ROOT%backend\.venv\Scripts\python.exe" -c "from backend.app.main import app; print('[OK] API carregada:', app.title)"
  if errorlevel 1 set "FALHA=1"
  "%ROOT%backend\.venv\Scripts\python.exe" -m backend.scripts.verificar_contexto_exposicao
  if errorlevel 1 set "FALHA=1"
) else (
  echo [FALHA] backend\.venv nao existe.
  set "FALHA=1"
)

echo.
where node >nul 2>&1
if errorlevel 1 (
  echo [FALHA] Node.js nao encontrado.
  set "FALHA=1"
) else (
  node -v
)
where npm >nul 2>&1
if errorlevel 1 (
  echo [FALHA] npm nao encontrado.
  set "FALHA=1"
) else (
  call npm.cmd -v
)

if exist "%ROOT%frontend\node_modules\.bin\vite.cmd" (
  cd /d "%ROOT%frontend"
  call npm run build
  if errorlevel 1 set "FALHA=1"
) else (
  echo [FALHA] frontend\node_modules\.bin\vite.cmd nao existe.
  set "FALHA=1"
)

echo.
if "%FALHA%"=="0" (
  echo ============================================================
  echo [OK] INSTALACAO VALIDADA
  echo Agora execute 02_iniciar_projeto.bat
) else (
  echo ============================================================
  echo [FALHA] Ha itens a corrigir.
  echo Tente 05_reinstalar_backend.bat ou 06_reinstalar_frontend.bat.
)
pause
exit /b %FALHA%
