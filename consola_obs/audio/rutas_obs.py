"""Traducción de rutas de audio para OBS (Fase 2 del plan de música).

El problema: la consola le manda a OBS rutas ABSOLUTAS de SU disco
(`D:\\...\\X.mp3`) y OBS las busca en EL SUYO. En la misma PC
coinciden; en otra PC, no (silencio en el stream aunque el pad se
ilumine y suene local).

La solución: guardar rutas RELATIVAS a assets/ y, solo cuando el OBS
está en otra PC, anteponerle la "carpeta base del OBS" (un ajuste que
se pide una sola vez y queda guardado). Misma PC = ruta directa,
cero cambio de comportamiento.
"""
import os

from consola_obs import estado as E
from consola_obs import rutas as R
from consola_obs import configuracion as mod_configuracion
from consola_obs import red as mod_red

EXTENSIONES_AUDIO = (".mp3", ".wav", ".ogg", ".flac", ".m4a")


def es_audio(ruta):
    return str(ruta).lower().endswith(EXTENSIONES_AUDIO)


def relativizar(ruta):
    """Devuelve la ruta relativa a assets/ si está adentro (caso
    normal, incluye Musica/...), o relativa a la carpeta de música
    con el prefijo 'Musica' si viviera afuera, o el nombre del
    archivo si está en otro lado (mejor esfuerzo para archivos
    elegidos fuera de assets con el diálogo)."""
    try:
        normal = os.path.normpath(ruta)
        for base, prefijo in (
            (R.CARPETA_ASSETS, ""),
            (R.CARPETA_MUSICA, "Musica"),
        ):
            b = os.path.normpath(base)
            if normal == b or normal.startswith(b + os.sep):
                rel = os.path.relpath(normal, b)
                if rel == ".":
                    return prefijo or rel
                return os.path.join(prefijo, rel) if prefijo else rel
    except Exception:
        pass
    try:
        return os.path.basename(ruta)
    except Exception:
        return ruta


def base_obs():
    """Carpeta assets del lado del OBS (ajuste, '' si no se configuró)."""
    try:
        return (mod_configuracion.cargar_config_interfaz().get("carpeta_base_obs") or "").strip()
    except Exception:
        return ""


def obs_en_otra_pc():
    """True si el OBS conectado está en otra PC (y por ende las rutas
    hay que traducirlas). Sin conexión, False (modo directo seguro)."""
    if not E.conectado:
        return False
    return not mod_red.es_localhost(E.host_conectado or "localhost")


def resolver_para_obs(ruta_local):
    """Ruta tal como hay que mandársela a OBS en set_input_settings:
    directa si misma PC (o sin base configurada), traducida
    (base_obs + relativa) si el OBS está en otra PC. Siempre con
    barras '/' (las acepta OBS en Windows y son obligatorias en
    Linux). Nunca lanza."""
    try:
        if not ruta_local:
            return ruta_local
        if not obs_en_otra_pc():
            return str(ruta_local).replace(os.sep, "/")
        base = base_obs()
        if not base:
            return str(ruta_local).replace(os.sep, "/")
        return os.path.join(base, relativizar(ruta_local)).replace(os.sep, "/")
    except Exception:
        return ruta_local
