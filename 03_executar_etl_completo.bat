@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
set "PY=%ROOT%backend\.venv\Scripts\python.exe"
cls

echo ============================================================
echo AgriShield - 03 - PIPELINE CLIMATICO - ETAPAS 1 A 3
echo ============================================================

if not exist "%PY%" (
  echo [ERRO] Ambiente Python nao encontrado.
  echo Execute 01_instalar_dependencias.bat primeiro.
  pause
  exit /b 1
)

cd /d "%ROOT%backend"
"%PY%" etl\etapa1_cadastro_fazendas.py
if errorlevel 1 goto :erro
"%PY%" etl\etapa2_coleta_nasa_power.py
if errorlevel 1 goto :erro
"%PY%" etl\etapa3_engenharia_variaveis.py
if errorlevel 1 goto :erro

echo.
echo [OK] ETL climatico concluido.
echo Verifique os CSVs em: backend\data
echo A Etapa 4 geoespacial e executada pelo cadastro ou pelo endpoint de recalculo.
pause
exit /b 0

:erro
echo.
echo [ERRO] Uma etapa do ETL falhou. Veja a mensagem acima.
pause
exit /b 1
