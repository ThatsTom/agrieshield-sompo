@echo off
setlocal EnableExtensions
chcp 65001 >nul
cls

echo ============================================================
echo AgriShield - 00 - PRE-REQUISITOS DO WINDOWS
echo ============================================================
echo.
echo Este arquivo verifica Python e Node.js.
echo Se estiverem ausentes e o winget existir, ele pode instala-los.
echo.

set "PRECISA_PY=0"
set "PRECISA_NODE=0"

py -3.13 -V >nul 2>&1
if not errorlevel 1 goto :python_ok
py -3.12 -V >nul 2>&1
if not errorlevel 1 goto :python_ok
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1
if not errorlevel 1 goto :python_ok
set "PRECISA_PY=1"
:python_ok

where node >nul 2>&1
if errorlevel 1 set "PRECISA_NODE=1"
where npm >nul 2>&1
if errorlevel 1 set "PRECISA_NODE=1"

if "%PRECISA_PY%"=="0" (
  echo [OK] Python 3.12 ou 3.13 encontrado.
) else (
  echo [FALTA] Python 3.12/3.13 nao foi encontrado.
)

if "%PRECISA_NODE%"=="0" (
  for /f "delims=" %%V in ('node -v') do echo [OK] Node.js encontrado: %%V
  for /f "delims=" %%V in ('npm -v') do echo [OK] npm encontrado: %%V
) else (
  echo [FALTA] Node.js/npm nao foi encontrado.
)

if "%PRECISA_PY%"=="0" if "%PRECISA_NODE%"=="0" goto :fim_ok

echo.
where winget >nul 2>&1
if errorlevel 1 goto :sem_winget

echo O winget foi encontrado e pode instalar os itens ausentes.
choice /C SN /N /M "Deseja instalar automaticamente agora? [S/N]: "
if errorlevel 2 goto :fim_manual

if "%PRECISA_PY%"=="1" (
  echo.
  echo [INSTALANDO] Python 3.13...
  winget install --id Python.Python.3.13 -e --source winget --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERRO] O winget nao conseguiu instalar o Python.
    goto :fim_manual
  )
)

if "%PRECISA_NODE%"=="1" (
  echo.
  echo [INSTALANDO] Node.js LTS...
  winget install --id OpenJS.NodeJS.LTS -e --source winget --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERRO] O winget nao conseguiu instalar o Node.js.
    goto :fim_manual
  )
)

echo.
echo ============================================================
echo PRE-REQUISITOS INSTALADOS
echo ============================================================
echo Feche esta janela e abra um novo Prompt de Comando ou PowerShell.
echo Depois execute: 01_instalar_dependencias.bat
pause
exit /b 0

:sem_winget
echo.
echo [AVISO] winget nao esta disponivel neste Windows.
:fim_manual
echo Instale manualmente:
echo   - Python 3.13 ou 3.12 (64 bits)
echo   - Node.js LTS com npm
echo Depois feche e reabra o terminal e execute 01_instalar_dependencias.bat.
pause
exit /b 1

:fim_ok
echo.
echo Tudo pronto. Agora execute 01_instalar_dependencias.bat.
pause
exit /b 0
