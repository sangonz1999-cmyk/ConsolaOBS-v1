@echo off
REM ============================================================
REM  Instala lo necesario para usar ConsolaOBS desde el codigo
REM  (para quien descargo el .zip de GitHub y no usa terminal).
REM
REM  Doble clic y listo: instala las dependencias con pip.
REM  Despues podes abrir el programa con:
REM    - doble clic en main.py (modo prueba), o
REM    - doble clic en compilar.bat (genera ConsolaOBS.exe)
REM ============================================================

cd /d "%~dp0."

REM Python: se prefiere el lanzador 'py', con 'python' como respaldo.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo ======================================================
    echo  NO SE ENCONTRO PYTHON.
    echo  Instala Python 3.9 o mas nuevo desde https://www.python.org/downloads/
    echo  Tilda "Add python.exe to PATH" durante la instalacion
    echo  y despues corre de nuevo este archivo.
    echo ======================================================
    pause
    exit /b 1
)

echo Python encontrado:
%PY% --version
echo.

if not exist "%~dp0requirements.txt" (
    echo ======================================================
    echo  No se encontro requirements.txt junto a este archivo.
    echo  Asegurate de haber descomprimido TODO el .zip en una
    echo  carpeta, no abrirlo desde adentro del .zip.
    echo ======================================================
    pause
    exit /b 1
)

echo Instalando dependencias (puede tardar unos minutos)...
%PY% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ======================================================
    echo  ALGO FALLO instalando las dependencias.
    echo  Probalo a mano en una terminal PowerShell en esta carpeta:
    echo    %PY% -m pip install -r requirements.txt
    echo  y pasa el mensaje de error que salga arriba.
    echo ======================================================
    pause
    exit /b 1
)

echo.
echo ======================================================
echo  Listo. Ya podes abrir el programa con doble clic en main.py
echo  (o generar ConsolaOBS.exe con doble clic en compilar.bat).
echo ======================================================
pause
