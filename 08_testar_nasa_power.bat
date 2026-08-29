@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
set "PY=%ROOT%backend\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERRO] Ambiente Python nao encontrado.
  echo Execute 01_instalar_dependencias.bat primeiro.
  pause
  exit /b 1
)

set "LATITUDE=%~1"
set "LONGITUDE=%~2"
set "DIAS=%~3"
if not defined LATITUDE set "LATITUDE=-12.545"
if not defined LONGITUDE set "LONGITUDE=-55.721"
if not defined DIAS set "DIAS=7"

echo ============================================================
echo AgriShield - TESTE NASA POWER
echo ============================================================
echo A API NASA POWER e publica: nao exige login nem chave de API.
echo Latitude: %LATITUDE%  Longitude: %LONGITUDE%  Dias: %DIAS%
echo.

cd /d "%ROOT%"
"%PY%" backend\scripts\testar_nasa_power.py --latitude "%LATITUDE%" --longitude "%LONGITUDE%" --dias "%DIAS%"
set "RESULTADO=%ERRORLEVEL%"
echo.
if "%RESULTADO%"=="0" (
  echo [OK] Integracao NASA POWER pronta para uso.
) else (
  echo [ERRO] Nao foi possivel validar uma resposta real da NASA POWER.
)
pause
exit /b %RESULTADO%
