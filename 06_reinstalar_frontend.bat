@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
cls

echo ============================================================
echo AgriShield - 06 - REINSTALAR FRONTEND REACT/VITE
echo ============================================================

where node >nul 2>&1
if errorlevel 1 goto :sem_node
where npm >nul 2>&1
if errorlevel 1 goto :sem_node

cd /d "%ROOT%frontend"
if exist node_modules rmdir /s /q node_modules
if exist package-lock.json del /q package-lock.json

echo Instalando dependencias npm incluindo devDependencies...
call npm install --include=dev --no-audit --no-fund
if errorlevel 1 goto :erro

if not exist "node_modules\.bin\vite.cmd" (
  echo [ERRO] Vite nao foi instalado corretamente.
  goto :erro
)

call npm run build
if errorlevel 1 goto :erro

echo.
echo [OK] Frontend reinstalado e build validado.
echo Agora execute 02_iniciar_projeto.bat.
pause
exit /b 0

:sem_node
echo [ERRO] Node.js/npm nao encontrado.
echo Execute 00_instalar_pre_requisitos.bat primeiro.
pause
exit /b 1

:erro
echo.
echo [ERRO] Nao foi possivel reinstalar o frontend.
echo Confira sua internet, proxy/firewall e o acesso ao registry.npmjs.org.
pause
exit /b 1
