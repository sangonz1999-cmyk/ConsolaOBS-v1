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
import threading

from consola_obs import estado as E
from consola_obs import constantes as C
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


def _base_valida_para_obs(base, plataforma):
    """None si la base sirve para ese OBS; si no, el motivo corto."""
    if not base:
        return "está vacía"
    if not _es_ruta_absoluta_obs(base):
        return "no es una ruta absoluta"
    if "linux" in plataforma or "darwin" in plataforma or "mac" in plataforma:
        if not base.startswith("/"):
            return "el OBS está en Linux/macOS y no empieza con /"
    elif "win" in plataforma:
        if not (base.startswith("\\") or re.match(r"^[A-Za-z]:", base)):
            return "el OBS está en Windows y no parece ruta Windows (ej D:\\...)"
    return None


def _plataforma_obs():
    try:
        return str(getattr(E, "plataforma_obs", "") or "").lower()
    except Exception:
        return ""


def motivo_base_obs():
    """Motivo corto si el OBS remoto no tiene base útil; None si todo
    bien (misma PC, sin conexión o base válida). Sin carteles: es para
    el hint del menú. Nunca lanza."""
    try:
        if not E.conectado:
            return None
        try:
            remoto = obs_en_otra_pc()
        except Exception:
            remoto = False
        if not remoto:
            return None
        return _base_valida_para_obs(base_obs(), _plataforma_obs())
    except Exception:
        return None


def _leer_archivo_actual(nombre_fuente):
    """El local_file que la fuente tiene AHORA en OBS ('' si no hay).
    Nunca lanza."""
    try:
        cliente = E.cliente_obs
    except Exception:
        return ""
    if cliente is None:
        return ""
    try:
        respuesta = cliente.get_input_settings(nombre_fuente)
    except Exception:
        return ""
    try:
        ajustes = None
        if isinstance(respuesta, dict):
            ajustes = respuesta.get("input_settings") or respuesta.get("inputSettings")
        else:
            ajustes = getattr(respuesta, "input_settings", None)
        if ajustes is None and not isinstance(respuesta, dict):
            ajustes = getattr(respuesta, "inputSettings", None)
        if isinstance(ajustes, dict):
            return str(ajustes.get("local_file") or "").strip()
    except Exception:
        pass
    return ""


def _aprender_base_de(archivo):
    """Adopta la base desde un archivo con pinta de assets (segmento
    '/assets/') con formato válido para el OBS remoto. Guarda sola.
    Devuelve True si aprendió. Nunca lanza."""
    try:
        normal = str(archivo or "").replace("\\", "/")
    except Exception:
        return False
    if not normal:
        return False
    cortado = normal.lower().rfind("/assets/")
    if cortado < 0:
        return False
    base = normal[:cortado + len("/assets/")]
    if _base_valida_para_obs(base, _plataforma_obs()) is not None:
        return False
    try:
        mod_configuracion.guardar_config_interfaz({"carpeta_base_obs": base})
    except Exception:
        return False
    try:
        mod_red.log_conexion("BASE_OBS", f"aprendida sola: {base}")
    except Exception:
        pass
    try:
        refrescar = getattr(E, "refrescar_hint_base_obs", None)
        if refrescar:
            refrescar()
    except Exception:
        pass
    return True


def intentar_aprender_base():
    """Auto-detecta la base remota desde las fuentes que YA existen en
    el OBS: si alguna tiene cargado un archivo con pinta de assets
    (carpeta 'assets' en la ruta) y con formato válido para el sistema
    de ese OBS, se adopta su carpeta y se guarda sola. Una vez por
    sesión, en silencio. Devuelve True si aprendió algo."""
    try:
        try:
            if bool(getattr(E, "_base_aprendida_intentada", False)):
                return False
        except Exception:
            pass
        try:
            E._base_aprendida_intentada = True
        except Exception:
            pass
        if not E.conectado:
            return False
        try:
            remoto = obs_en_otra_pc()
        except Exception:
            remoto = False
        if not remoto:
            return False
        if base_obs():
            return False
        for nombre in (C.NOMBRE_FUENTE_EFECTOS, C.NOMBRE_FUENTE_MUSICA):
            if _aprender_base_de(_leer_archivo_actual(nombre)):
                return True
        return False
    except Exception:
        return False


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


def ruta_para_enviar(nombre_fuente, ruta_local):
    """(ruta, hay_que_fijar): qué mandar al OBS para esa fuente.
    En remoto, si la fuente YA tiene un archivo válido para el sistema
    del OBS (ej lo pusiste a mano con Examinar) y lo que calcularíamos
    nosotros es inválido allá (típico: sin base saldría D:/... en un
    Linux), NO se pisa: se usa el que ya está (y se aprende la base de
    él). Si lo nuestro vale, se fija como siempre. Nunca lanza."""
    try:
        if not E.conectado:
            return ruta_local, True
        try:
            remoto = obs_en_otra_pc()
        except Exception:
            remoto = False
        if not remoto:
            return resolver_para_obs(ruta_local), True
        plataforma = _plataforma_obs()
        nuestra = resolver_para_obs(ruta_local)
        actual = _leer_archivo_actual(nombre_fuente)
        if (actual
                and _base_valida_para_obs(actual, plataforma) is None
                and _base_valida_para_obs(nuestra, plataforma) is not None):
            _aprender_base_de(actual)
            return actual, False
        return nuestra, True
    except Exception:
        try:
            return resolver_para_obs(ruta_local), True
        except Exception:
            return ruta_local, True


def reintentar_si_no_arranca(nombre_fuente, sigue_vigente, espera_seg=2.5):
    """Hilo: si el OBS remoto no arranca el medio (ni PLAYING ni ENDED
    ni duración en ~espera_seg), manda un RESTART más y lo anota en el
    log. Cubre la carrera set→restart en enlaces con latencia (el
    restart llegaba antes de que OBS aplicara el archivo y era
    silencio). En misma PC no hace nada. Nunca lanza."""
    def _hilo():
        try:
            import time as _t
            fin = _t.time() + espera_seg
            while _t.time() < fin:
                try:
                    if not sigue_vigente():
                        return
                    respuesta = E.cliente_obs.get_media_input_status(nombre_fuente)
                except Exception:
                    return
                estado = None
                dur = 0
                try:
                    if isinstance(respuesta, dict):
                        estado = respuesta.get("media_state") or respuesta.get("mediaState")
                        dur = respuesta.get("media_duration") or respuesta.get("mediaDuration") or 0
                    else:
                        estado = getattr(respuesta, "media_state", None)
                        dur = getattr(respuesta, "media_duration", 0) or 0
                except Exception:
                    pass
                try:
                    hay = (estado == "OBS_MEDIA_STATE_PLAYING"
                           or estado == "OBS_MEDIA_STATE_ENDED"
                           or (dur and float(dur) > 0))
                except Exception:
                    hay = False
                if hay:
                    return
                _t.sleep(0.3)
            try:
                if not sigue_vigente():
                    return
                E.cliente_obs.trigger_media_input_action(
                    nombre_fuente, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
            except Exception:
                return
            try:
                mod_red.log_conexion("BASE_OBS",
                                     f"re-disparo a '{nombre_fuente}' por falta de arranque")
            except Exception:
                pass
        except Exception:
            pass
    try:
        if not E.conectado:
            return
        try:
            remoto = obs_en_otra_pc()
        except Exception:
            remoto = False
        if not remoto:
            return
        threading.Thread(target=_hilo, daemon=True).start()
    except Exception:
        pass
