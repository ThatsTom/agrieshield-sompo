@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
cls

echo ============================================================
echo AgriShield - 01 - INSTALACAO COMPLETA
echo ============================================================
echo.

rem ------------------------------------------------------------
rem Seleciona Python 3.13 ou 3.12. Evita usar Python 3.14+ com
rem dependencias antigas do trabalho.
rem ------------------------------------------------------------
set "PY_CMD="
py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,13) else 1)" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3.13"
if not defined PY_CMD (
  py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
  if not errorlevel 1 set "PY_CMD=py -3.12"
)
if not defined PY_CMD (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1
  if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo [ERRO] Python 3.12 ou 3.13 nao encontrado.
  echo Execute primeiro: 00_instalar_pre_requisitos.bat
  pause
  exit /b 1
)

for /f "delims=" %%V in ('%PY_CMD% -V') do echo [OK] %%V

echo.
echo [1/5] Preparando ambiente virtual Python...
cd /d "%ROOT%backend"
if not exist ".venv\Scripts\python.exe" (
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto :erro
) else (
  echo Ambiente virtual ja existe: backend\.venv
)

set "VENV_PY=%ROOT%backend\.venv\Scripts\python.exe"
"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [ERRO] A .venv existente foi criada com uma versao de Python incompativel.
  echo Execute 05_reinstalar_backend.bat e tente novamente.
  pause
  exit /b 1
)

echo.
echo [2/5] Atualizando ferramentas do pip...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :erro

echo.
echo [3/5] Instalando dependencias Python...
echo Primeiro NumPy/Pandas por pacote binario para evitar compilacao local.
"%VENV_PY%" -m pip install --only-binary=:all: numpy==2.1.3 pandas==2.2.3
if errorlevel 1 goto :erro_python
"%VENV_PY%" -m pip install -r "%ROOT%backend\requirements.txt"
if errorlevel 1 goto :erro_python

"%VENV_PY%" -c "import dotenv,ee,fastapi,httpx,uvicorn,pydantic,requests,pandas,numpy; print('[OK] Backend Python:', fastapi.__version__, '| httpx:', httpx.__version__, '| pandas:', pandas.__version__, '| numpy:', numpy.__version__)"
if errorlevel 1 goto :erro_python

"%VENV_PY%" "%ROOT%backend\etl\etapa1_cadastro_fazendas.py"
if errorlevel 1 goto :erro_python

echo.
echo [4/5] Verificando Node.js e npm...
where node >nul 2>&1
if errorlevel 1 goto :erro_node
where npm >nul 2>&1
if errorlevel 1 goto :erro_node
for /f "delims=" %%V in ('node -v') do echo [OK] Node.js %%V
for /f "delims=" %%V in ('npm -v') do echo [OK] npm %%V
for /f %%M in ('node -p "parseInt(process.versions.node.split('.')[0],10)"') do set "NODE_MAJOR=%%M"
if %NODE_MAJOR% LSS 18 (
  echo [ERRO] Node.js muito antigo. Use Node.js LTS 20 ou superior.
  pause
  exit /b 1
)

echo.
echo [5/5] Instalando React, Vite e pacotes npm...
cd /d "%ROOT%frontend"
if exist "node_modules" if not exist "node_modules\.bin\vite.cmd" (
  echo Detectado node_modules incompleto. Limpando...
  rmdir /s /q node_modules
)
call npm install --include=dev --no-audit --no-fund
if errorlevel 1 goto :erro_npm

if not exist "node_modules\.bin\vite.cmd" (
  echo [ERRO] O Vite nao foi instalado em frontend\node_modules\.bin.
  goto :erro_npm
)

call npm run build
if errorlevel 1 goto :erro_npm

echo.
echo ============================================================
echo INSTALACAO CONCLUIDA COM SUCESSO
echo ============================================================
echo Backend: Python/FastAPI instalado em backend\.venv
echo Frontend: React/Vite instalado em frontend\node_modules
echo.
echo Proximo passo: execute 02_iniciar_projeto.bat
pause
exit /b 0

:erro_python
echo.
echo [ERRO] Falha na instalacao Python.
echo Se aparecer erro de pandas/Meson/Visual Studio, execute 05_reinstalar_backend.bat.
pause
exit /b 1

:erro_node
echo.
echo [ERRO] Node.js/npm nao foi encontrado.
echo Execute 00_instalar_pre_requisitos.bat, feche o terminal e tente novamente.
pause
exit /b 1

:erro_npm
echo.
echo [ERRO] Falha na instalacao npm/React/Vite.
echo Execute 06_reinstalar_frontend.bat para limpar e tentar novamente.
pause
exit /b 1

:erro
echo.
echo [ERRO] A instalacao foi interrompida. Verifique as mensagens acima.
pause
exit /b 1
