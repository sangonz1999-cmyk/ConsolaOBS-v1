"""Configuración del sync bidireccional (aislada de la config actual).

Archivo: config/sync_config.json con carpeta_local, ip_remota, puerto
y api_key. La key se busca en este orden: variable de entorno
CONSOLAOBS_SYNC_KEY -> sync_config.json -> se genera una al azar y se
guarda (se muestra en la UI para copiarla a la otra PC: las 2 PCs
tienen que usar LA MISMA key).
"""
import json
import os
import secrets

from consola_obs import rutas as R
from consola_obs import secretos
from consola_obs import configuracion as mod_configuracion

ARCHIVO_SYNC_CONFIG = os.path.join(R.CARPETA_CONFIG, "sync_config.json")
ARCHIVO_ULTIMO_INDICE = os.path.join(R.CARPETA_CONFIG, "ultimo_indice.json")

VAR_ENTORNO_KEY = "CONSOLAOBS_SYNC_KEY"
PUERTO_POR_DEFECTO = 4456  # distinto del 4455 de OBS-WebSocket a propósito


def _defecto():
    return {
        "carpeta_local": R.CARPETA_ASSETS,
        "ip_remota": "",
        "puerto": PUERTO_POR_DEFECTO,
        "api_key": "",
    }


def cargar():
    """Lee sync_config.json (o valores de fábrica). Nunca lanza."""
    cfg = _defecto()
    try:
        if os.path.exists(ARCHIVO_SYNC_CONFIG):
            with open(ARCHIVO_SYNC_CONFIG, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if isinstance(datos, dict):
                for k in cfg:
                    if k in datos and isinstance(datos[k], type(cfg[k])):
                        cfg[k] = datos[k]
                # La clave se guarda cifrada (ver secretos.py); una
                # clave vieja en texto plano se sigue leyendo.
                cfg["api_key"] = secretos.desproteger(cfg.get("api_key") or "")
    except Exception as e:
        print(f"No se pudo leer la configuración de sync: {e}")
    # La key del entorno manda sobre la guardada (para no dejarla sólo
    # en disco si preferís pasarla por entorno).
    try:
        key_env = (os.getenv(VAR_ENTORNO_KEY) or "").strip()
    except Exception:
        key_env = ""
    if key_env:
        cfg["api_key"] = key_env
    return cfg


def guardar(datos_nuevos):
    """Actualiza sólo las claves indicadas. Nunca lanza."""
    cfg = cargar()
    # Si viene key del entorno, no se pisa el archivo con otra.
    try:
        if (os.getenv(VAR_ENTORNO_KEY) or "").strip():
            datos_nuevos = {k: v for k, v in datos_nuevos.items() if k != "api_key"}
    except Exception:
        pass
    cfg.update(datos_nuevos)
    a_disco = dict(cfg)
    # La key que vino del entorno no se escribe en disco.
    try:
        if (os.getenv(VAR_ENTORNO_KEY) or "").strip():
            a_disco["api_key"] = ""
    except Exception:
        pass
    a_disco["api_key"] = secretos.proteger(a_disco.get("api_key") or "")
    mod_configuracion.escribir_json_atomico(ARCHIVO_SYNC_CONFIG, a_disco)
    return cfg


def obtener_api_key(cfg=None):
    """API key efectiva: entorno -> config -> generar y guardar una
    nueva (se genera una sola vez; la UI la muestra para copiarla a la
    otra PC). Nunca lanza ni devuelve vacío."""
    try:
        key_env = (os.getenv(VAR_ENTORNO_KEY) or "").strip()
    except Exception:
        key_env = ""
    if key_env:
        return key_env
    if cfg is None:
        cfg = cargar()
    key = (cfg.get("api_key") or "").strip()
    if key:
        return key
    key = secrets.token_urlsafe(24)
    guardar({"api_key": key})
    print("Sync: se generó una API key nueva (copiala a la otra PC).")
    return key


def cargar_ultimo_indice():
    """Snapshot de la última sincronización: {relpath: {size, mtime,
    sha256}}. Sirve para distinguir 'archivo nuevo' de 'archivo
    borrado del otro lado'. Si no existe, {} (todo faltante es nuevo).
    Nunca lanza."""
    try:
        if os.path.exists(ARCHIVO_ULTIMO_INDICE):
            with open(ARCHIVO_ULTIMO_INDICE, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if isinstance(datos, dict):
                return datos
    except Exception as e:
        print(f"No se pudo leer el último índice de sync: {e}")
    return {}


def guardar_ultimo_indice(indice):
    """Guarda el snapshot post-sync. Nunca lanza."""
    mod_configuracion.escribir_json_atomico(ARCHIVO_ULTIMO_INDICE, indice)
