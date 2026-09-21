@echo off
REM ============================================================
REM  Recompila ConsolaOBS.exe en ESTA MISMA CARPETA
REM      (junto a este .bat y a main.py, con el icono asignado).
REM
REM  En modo --onefile PyInstaller solo crea/pisa el .exe aca,
REM  no toca ni borra el resto (assets\, consola_obs\, etc.).
REM
REM  Poner este archivo en la RAIZ del proyecto (junto a main.py)
REM  y doble clic cada vez que cambies el codigo.
REM ============================================================

cd /d "%~dp0."

REM Python: se prefiere el lanzador 'py', con 'python' como respaldo
REM (en algunas PCs recien instaladas solo existe uno de los dos).
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

set CARPETA_DESTINO=%~dp0
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
echo El ejecutable se va a generar en:
echo   %CARPETA_DESTINO%ConsolaOBS.exe
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

echo.
echo Revisando herramientas de compilacion (solo la primera vez instala)...
%PY% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo Instalando PyInstaller...
    %PY% -m pip install pyinstaller
    %PY% -c "import PyInstaller" >nul 2>nul
    if errorlevel 1 (
        echo ======================================================
        echo  NO SE PUDO INSTALAR PYINSTALLER.
        echo  Revisa tu conexion e intenta a mano:
        echo    %PY% -m pip install pyinstaller
        echo ======================================================
        pause
        exit /b 1
    )
)
if exist "%~dp0requirements.txt" (
    echo Instalando dependencias del programa...
    %PY% -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo  AVISO: algo fallo instalando requirements.txt, sigo igual.
    )
)
echo.

echo Borrando restos de compilaciones anteriores...
REM Si el .exe anterior sigue abierto, Windows lo bloquea y la
REM compilación falla: se cierra primero.
taskkill /F /IM ConsolaOBS.exe 2>nul
rmdir /s /q "%CARPETA_BUILD%" 2>nul
del ConsolaOBS.spec 2>nul

echo.
echo Compilando ConsolaOBS.exe...
REM OJO: no quitar el \. de --distpath: como CARPETA_DESTINO termina en
REM barra invertida, "...\" escaparia la comilla de cierre y PyInstaller
REM recibiria mal los argumentos (diria que falta el script).
REM --hidden-import cffi: miniaudio lo necesita a nivel C (_miniaudio.pyd)
REM y PyInstaller no lo detecta solo; sin esto el .exe no tiene audio local.
%PY% -m PyInstaller --onefile --windowed --name ConsolaOBS %OPCION_ICONO% --hidden-import cffi --collect-all pymupdf --version-file "%~dp0version_info.txt" --distpath "%CARPETA_DESTINO%." --workpath "%CARPETA_BUILD%" main.py

if not exist "%CARPETA_DESTINO%\ConsolaOBS.exe" (
    echo.
    echo ======================================================
    echo  ALGO FALLO. Revisa los mensajes de arriba en rojo.
    echo ======================================================
    pause
    exit /b 1
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
