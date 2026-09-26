@echo off
REM ============================================================
REM  Arma los dos ZIP de la Release (vX.Y.Z):
REM    ConsolaOBS-Consola.zip  -> carpeta ConsolaOBS/ (programa + todo)
REM    ConsolaOBS-OBS.zip      -> carpeta OBS/ (solo sonidos + musica)
REM
REM  Se usan tal cual estan para subirlos a GitHub Releases.
REM  Antes: compilar.bat (para que los .exe sean los nuevos) y que
REM  VERSION en consola_obs\update\version.py coincida con el tag.
REM ============================================================

cd /d "%~dp0."

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo NO SE ENCONTRO PYTHON. Instalalo y reintenta.
    pause
    exit /b 1
)

echo Armando zips de la Release...
%PY% armar_release.py
if errorlevel 1 (
    echo.
    echo ALGO FALLO. Revisa los mensajes de arriba.
    pause
    exit /b 1
)

echo.
echo Listo. Subi estos dos archivos a la Release en GitHub:
dir /b ConsolaOBS-Consola.zip ConsolaOBS-OBS.zip
pause
