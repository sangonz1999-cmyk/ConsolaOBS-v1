@echo off
REM ============================================================
REM  Sincroniza sonidos/imagenes/musica nuevos con el git.
REM
REM  Doble clic y listo: detecta archivos nuevos en
REM  assets\Sondidos_pad, assets\Imagenes_pad y assets\Musica,
REM  los agrega, commitea y pushea. Si no hay nada nuevo,
REM  no hace nada.
REM ============================================================

cd /d "%~dp0"

if exist "assets\Sondidos_pad" git add "assets\Sondidos_pad"
if exist "assets\Imagenes_pad" git add "assets\Imagenes_pad"
if exist "assets\Musica" git add "assets\Musica"

git diff --cached --quiet
if %errorlevel%==0 (
    echo Sin sonidos nuevos para subir. Todo al dia.
    pause
    exit /b 0
)

git commit -m "Assets: sincronizar sonidos/imagenes/musica nuevos"
if errorlevel 1 (
    echo No se pudo commitear. Revisa el mensaje de arriba.
    pause
    exit /b 1
)
git push origin main
if errorlevel 1 (
    echo No se pudo pushear. Revisa tu conexion.
    pause
    exit /b 1
)

echo.
echo Listo. Sonidos nuevos subidos al git.
pause
