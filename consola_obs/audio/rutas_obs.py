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
import re

from tkinter import messagebox

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


def _es_ruta_absoluta_obs(base):
    """Absoluta en cualquier sistema: /algo (Linux/macOS), D:... o
    D:/... (Windows) o \\\\equipo\\... (red Windows). A propósito no
    se usa os.path.isabs: ese chequea con el sistema LOCAL y acá la
    ruta es del sistema del OBS, que puede ser otro."""
    try:
        b = (base or "").strip()
    except Exception:
        return False
    if not b:
        return False
    if b.startswith("/") or b.startswith("\\"):
        return True
    return bool(re.match(r"^[A-Za-z]:", b))


def base_obs_lista_o_avisar():
    """True si se puede mandar audio al OBS (misma PC, o remoto con
    base útil). Si el OBS está en otra PC y la base falta o tiene un
    formato imposible para el sistema del OBS, avisa UNA vez por
    sesión con el arreglo exacto y devuelve False: así no se manda
    una ruta rota en silencio (el pad se ilumina y suena local pero
    en el stream hay silencio). Nunca lanza."""
    try:
        if not E.conectado:
            return True
        try:
            remoto = obs_en_otra_pc()
        except Exception:
            remoto = False
        if not remoto:
            return True
        base = base_obs()
        try:
            plataforma = str(getattr(E, "plataforma_obs", "") or "").lower()
        except Exception:
            plataforma = ""
        if "linux" in plataforma or "darwin" in plataforma or "mac" in plataforma:
            es_linux = True
        elif "win" in plataforma:
            es_linux = False
        else:
            es_linux = None  # no se informó: solo se exige absoluta
        if not base:
            motivo = "está vacía"
        elif not _es_ruta_absoluta_obs(base):
            motivo = "no es una ruta absoluta"
        elif es_linux is True and not base.startswith("/"):
            motivo = "el OBS está en Linux/macOS y no empieza con /"
        elif es_linux is False and not (
                base.startswith("\\")
                or re.match(r"^[A-Za-z]:", base)):
            motivo = "el OBS está en Windows y no parece ruta Windows (ej D:\\...)"
        else:
            return True
        try:
            ya = bool(getattr(E, "_aviso_base_obs_mostrado", False))
        except Exception:
            ya = False
        if not ya:
            try:
                E._aviso_base_obs_mostrado = True
            except Exception:
                pass
            try:
                mod_red.log_conexion("BASE_OBS", f"bloqueado por base inválida ({motivo}): {base!r}")
            except Exception:
                pass
            try:
                messagebox.showerror(
                    "Falta la Carpeta OBS",
                    f"El OBS está en otra PC y la Carpeta OBS {motivo}.\n\n"
                    f"Actual: {base or '(vacía)'}\n\n"
                    "Sin eso el sonido sale acá pero en el stream hay silencio.\n\n"
                    "Arreglo: en el menú CONEXIÓN → Carpeta OBS escribí la "
                    "ruta de la carpeta assets TAL COMO SE VE EN LA PC DEL "
                    "OBS (en esa PC: abrir la carpeta assets y copiar la "
                    "ruta completa; en Linux empieza con /home/). "
                    "Se guarda sola al salir del campo.",
                )
            except Exception:
                pass
        return False
    except Exception:
        return True


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
