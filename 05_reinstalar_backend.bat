@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
cls

echo ============================================================
echo AgriShield - 05 - REINSTALAR BACKEND
echo ============================================================
echo Este processo remove APENAS backend\.venv.
echo Seus codigos e CSVs nao serao apagados.
echo.
choice /C SN /N /M "Continuar? [S/N]: "
if errorlevel 2 exit /b 0

if exist "%ROOT%backend\.venv" rmdir /s /q "%ROOT%backend\.venv"
echo Ambiente Python removido.
echo.
echo Agora execute 01_instalar_dependencias.bat.
pause
