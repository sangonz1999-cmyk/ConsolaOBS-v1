import os
import sys


_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))



if getattr(sys, "frozen", False):
    # Empaquetado con PyInstaller (--onefile o --onedir): __file__ acá
    # apunta a la carpeta temporal donde Windows descomprime el .exe
    # al abrirlo (algo tipo AppData\Local\Temp\_MEIxxxxx), no a donde
    # está el .exe de verdad. Guardar la config ahí, o buscar la
    # carpeta "assets" ahí, no serviría de nada: esa carpeta temporal
    # se borra apenas se cierra el programa. sys.executable, en
    # cambio, sí apunta siempre al .exe real, esté donde esté.
    CARPETA_SCRIPT = os.path.dirname(os.path.abspath(sys.executable))
else:
    CARPETA_SCRIPT = _RAIZ_PROYECTO
ARCHIVO_CONEXION = os.path.join(CARPETA_SCRIPT, "config", "config_conexion.json")
ARCHIVO_SOUNDBOARD = os.path.join(CARPETA_SCRIPT, "config", "config_soundboard.json")
ARCHIVO_INTERFAZ = os.path.join(CARPETA_SCRIPT, "config", "config_interfaz.json")
ARCHIVO_MUSICA = os.path.join(CARPETA_SCRIPT, "config", "config_musica.json")

CARPETA_CONFIG = os.path.join(CARPETA_SCRIPT, "config")

CARPETA_ASSETS = os.path.join(CARPETA_SCRIPT, "assets")
CARPETA_ICONOS = os.path.join(CARPETA_ASSETS, "iconos")
CARPETA_FONDOS = os.path.join(CARPETA_ASSETS, "fondos")
CARPETA_FUENTES_TIPOGRAFIA = os.path.join(CARPETA_ASSETS, "fuentes")
CARPETA_SONIDOS_PAD = os.path.join(CARPETA_ASSETS, "Sondidos_pad")
CARPETA_IMAGENES_PAD = os.path.join(CARPETA_ASSETS, "Imagenes_pad")
# Biblioteca de música de fondo (Fase 1 del plan de música): cada
# subcarpeta es una categoría en la ventana biblioteca. Los archivos
# los lee OBS (no el programa), así que en una PC remota tienen que
# existir del lado del OBS (ver ajuste de carpeta base, Fase 2).
CARPETA_MUSICA = os.path.join(CARPETA_ASSETS, "Musica")

for _carpeta in (CARPETA_CONFIG, CARPETA_ASSETS, CARPETA_ICONOS, CARPETA_FONDOS, CARPETA_FUENTES_TIPOGRAFIA,
                 CARPETA_SONIDOS_PAD, CARPETA_IMAGENES_PAD, CARPETA_MUSICA):
    try:
        os.makedirs(_carpeta, exist_ok=True)
    except Exception:
        pass

# Migración: antes los JSON vivían sueltos junto al .py/.exe.
# Si existen ahí y todavía no están en config/, se mudan solos.
for _nuevo, _viejo in ((ARCHIVO_CONEXION, os.path.join(CARPETA_SCRIPT, "config_conexion.json")),
                       (ARCHIVO_SOUNDBOARD, os.path.join(CARPETA_SCRIPT, "config_soundboard.json")),
                       (ARCHIVO_INTERFAZ, os.path.join(CARPETA_SCRIPT, "config_interfaz.json"))):
    try:
        if os.path.exists(_viejo) and not os.path.exists(_nuevo):
            os.rename(_viejo, _nuevo)
    except Exception:
        pass
