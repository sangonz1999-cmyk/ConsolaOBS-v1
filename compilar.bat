@echo off
REM ============================================================
REM  Recompila ConsolaOBS.exe DIRECTO en:
REM      .\dist\ConsolaOBS.exe
REM  (siempre con el icono asignado).
REM
REM  Sin pasos de copia intermedios: PyInstaller compila
REM  directamente en esa carpeta con --distpath. En modo --onefile
REM  PyInstaller solo crea/pisa el .exe ahi, no toca ni borra el
REM  resto de lo que haya en esa carpeta (assets\, los .json de
REM  configuracion, etc.).
REM
REM  Poner este archivo en la RAIZ del proyecto (junto a main.py)
REM  y doble clic cada vez que cambies el codigo.
REM ============================================================

cd /d "%~dp0"

set CARPETA_DESTINO=%~dp0dist
set CARPETA_BUILD=%~dp0_build_tmp

REM El icono se busca en assets\iconos\app_icon.ico. Si no esta ahi,
REM se compila igual pero sin icono.
set ICONO=%~dp0assets\iconos\app_icon.ico

echo Archivo que se va a compilar:
echo   %~dp0main.py
for %%A in (main.py) do echo Ultima modificacion: %%~tA
echo.
echo (Si esa fecha/hora no es de ahora hace un rato, este NO es el
echo  archivo que pensas que es: revisa que estes editando el codigo
echo  dentro de la carpeta consola_obs\.)
echo.

if exist "%ICONO%" (
    echo Icono encontrado:
    echo   %ICONO%
    set OPCION_ICONO=--icon "%ICONO%"
) else (
    echo ======================================================
    echo  AVISO: no se encontro el icono en:
    echo    %ICONO%
    echo  Se va a compilar SIN icono asignado.
    echo ======================================================
    set OPCION_ICONO=
)
echo.

echo Borrando restos de compilaciones anteriores...
rmdir /s /q "%CARPETA_BUILD%" 2>nul
del ConsolaOBS.spec 2>nul

if not exist "%CARPETA_DESTINO%" mkdir "%CARPETA_DESTINO%"

echo.
echo Compilando ConsolaOBS.exe...
py -m PyInstaller --onefile --windowed --name ConsolaOBS %OPCION_ICONO% --distpath "%CARPETA_DESTINO%" --workpath "%CARPETA_BUILD%" main.py

if not exist "%CARPETA_DESTINO%\ConsolaOBS.exe" (
    echo.
    echo ======================================================
    echo  ALGO FALLO. Revisa los mensajes de arriba en rojo.
    echo ======================================================
    pause
    exit /b 1
)

if not exist "%CARPETA_DESTINO%\assets" (
    echo Copiando assets (primera vez en esta carpeta)...
    xcopy assets "%CARPETA_DESTINO%\assets" /E /I /Y >nul
)

echo Limpiando carpeta temporal...
rmdir /s /q "%CARPETA_BUILD%" 2>nul
del ConsolaOBS.spec 2>nul

echo.
echo ======================================================
echo  Listo. El ejecutable esta en: %CARPETA_DESTINO%\ConsolaOBS.exe
echo  Fecha/hora del .exe generado:
for %%A in ("%CARPETA_DESTINO%\ConsolaOBS.exe") do echo    %%~tA
echo ======================================================
pause
