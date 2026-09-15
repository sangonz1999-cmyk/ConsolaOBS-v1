import json
import os

from consola_obs import estado as E
from consola_obs import rutas as R


def cargar_config_conexion():
    if os.path.exists(R.ARCHIVO_CONEXION):
        try:
            with open(R.ARCHIVO_CONEXION, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"host": "localhost", "puerto": "4455", "password": ""}


def guardar_config_conexion(host, puerto, password):
    try:
        with open(R.ARCHIVO_CONEXION, "w", encoding="utf-8") as f:
            json.dump({"host": host, "puerto": str(puerto), "password": password}, f)
    except Exception as e:
        print(f"No se pudo guardar la configuración de conexión: {e}")



def cargar_config_soundboard():
    if os.path.exists(R.ARCHIVO_SOUNDBOARD):
        try:
            with open(R.ARCHIVO_SOUNDBOARD, "r", encoding="utf-8") as f:
                config_soundboard = json.load(f)
                return
        except Exception as e:
            print(f"No se pudo leer la configuración del soundboard: {e}")
    E.config_soundboard = {}


def guardar_config_soundboard():
    try:
        with open(R.ARCHIVO_SOUNDBOARD, "w", encoding="utf-8") as f:
            json.dump(E.config_soundboard, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"No se pudo guardar la configuración del soundboard: {e}")



def cargar_config_interfaz():
    if os.path.exists(R.ARCHIVO_INTERFAZ):
        try:
            with open(R.ARCHIVO_INTERFAZ, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"No se pudo leer la configuración de interfaz: {e}")
    return {}


def guardar_config_interfaz(datos_nuevos):
    """Actualiza sólo las claves indicadas, conservando el resto de la
    configuración de interfaz ya guardada."""
    actual = cargar_config_interfaz()
    actual.update(datos_nuevos)
    try:
        with open(R.ARCHIVO_INTERFAZ, "w", encoding="utf-8") as f:
            json.dump(actual, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"No se pudo guardar la configuración de interfaz: {e}")
