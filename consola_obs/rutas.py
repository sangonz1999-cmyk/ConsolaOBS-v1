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
ARCHIVO_CONEXION = os.path.join(CARPETA_SCRIPT, "config_conexion.json")
ARCHIVO_SOUNDBOARD = os.path.join(CARPETA_SCRIPT, "config_soundboard.json")
ARCHIVO_INTERFAZ = os.path.join(CARPETA_SCRIPT, "config_interfaz.json")

CARPETA_ASSETS = os.path.join(CARPETA_SCRIPT, "assets")
CARPETA_ICONOS = os.path.join(CARPETA_ASSETS, "iconos")
CARPETA_FONDOS = os.path.join(CARPETA_ASSETS, "fondos")
CARPETA_FUENTES_TIPOGRAFIA = os.path.join(CARPETA_ASSETS, "fuentes")
CARPETA_SONIDOS_PAD = os.path.join(CARPETA_ASSETS, "Sondidos_pad")
CARPETA_IMAGENES_PAD = os.path.join(CARPETA_ASSETS, "Imagenes_pad")

for _carpeta in (CARPETA_ASSETS, CARPETA_ICONOS, CARPETA_FONDOS, CARPETA_FUENTES_TIPOGRAFIA,
                 CARPETA_SONIDOS_PAD, CARPETA_IMAGENES_PAD):
    try:
        os.makedirs(_carpeta, exist_ok=True)
    except Exception:
        pass
