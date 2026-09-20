"""Motor de música de fondo para el stream (Fase 2 del plan de música).

Arquitectura "el programa manda, OBS ejecuta": la biblioteca, la cola
y el transporte viven acá; OBS solo tiene la fuente tonta 'Musica'
(ffmpeg_source, sin loop) y obedece. Sin audio local (miniaudio): la
música sale ÚNICAMENTE por el stream, nunca por los parlantes de la
PC (a diferencia del soundboard).

Quirks de OBS-WebSocket que este módulo esconde:
- Después de STOP, PLAY no reanuda: hay que usar RESTART. reanudar()
  elige solo (PLAY si estaba pausada, RESTART en cualquier otro caso).
- El avance automático solo se dispara con ENDED (fin natural), nunca
  con STOPPED (detención manual): así el stop del sonidista no salta
  solo al tema siguiente.
"""
import os
import threading
import time

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import rutas as R
from consola_obs import configuracion as mod_configuracion
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.audio import rutas_obs as mod_rutas_obs

# Sesión vigente. 'rel' es la ruta RELATIVA a assets/Musica (portable
# entre PCs con la misma estructura); 'archivo' la absoluta local.
# 'crudo' guarda el último mediaState tal cual lo informó OBS.
_sesion = {
    "rel": None, "archivo": None, "indice_cola": None,
    "estado": "DETENIDA", "crudo": None,
    "cursor_ms": 0.0, "duracion_ms": 0.0, "token": 0,
}
_cola = []
_sondeo = {"en_marcha": False}


def formatear_ms(milisegundos):
    """123456 -> '02:03'. Para la barra de progreso (Fase 3)."""
    try:
        segundos = max(0, int(float(milisegundos) // 1000))
        return f"{segundos // 60:02d}:{segundos % 60:02d}"
    except Exception:
        return "00:00"


def escanear_biblioteca():
    """Lee assets/Musica/: {carpeta: [rel, ...]} ordenado. Los audios
    sueltos en la raíz van en la carpeta 'General'. Solo extensiones
    de audio; si la carpeta no existe, diccionario vacío."""
    biblioteca = {}
    try:
        base = R.CARPETA_MUSICA
        if not os.path.isdir(base):
            return {}
        for entrada in sorted(os.listdir(base)):
            ruta = os.path.join(base, entrada)
            if os.path.isdir(ruta):
                temas = [
                    os.path.join(entrada, a)
                    for a in sorted(os.listdir(ruta))
                    if os.path.isfile(os.path.join(ruta, a))
                    and mod_rutas_obs.es_audio(a)
                ]
                if temas:
                    biblioteca[entrada] = temas
        sueltos = [
            a for a in sorted(os.listdir(base))
            if os.path.isfile(os.path.join(base, a))
            and mod_rutas_obs.es_audio(a)
        ]
        if sueltos:
            biblioteca["General"] = sueltos
    except Exception as e:
        print(f"No se pudo escanear la biblioteca de música: {e}")
    return biblioteca


def _absoluta(rel):
    return os.path.join(R.CARPETA_MUSICA, rel)


def _config():
    return mod_configuracion.cargar_config_musica()


def recientes():
    """Últimas pistas (rels), más reciente primero."""
    try:
        return [r for r in _config().get("recientes", []) if isinstance(r, str)]
    except Exception:
        return []


def _tocar_reciente(rel):
    try:
        cfg = _config()
        rec = [r for r in cfg.get("recientes", []) if isinstance(r, str) and r != rel]
        cfg["recientes"] = [rel] + rec[:C.MAX_RECIENTES_MUSICA - 1]
        mod_configuracion.guardar_config_musica(cfg)
    except Exception as e:
        print(f"No se pudo guardar el reciente de música: {e}")


def repetir():
    try:
        return bool(_config().get("repetir", True))
    except Exception:
        return True


def alternar_repetir():
    """Invierte repetir-lista y devuelve el nuevo valor (Fase 3)."""
    try:
        cfg = _config()
        cfg["repetir"] = not bool(cfg.get("repetir", True))
        mod_configuracion.guardar_config_musica(cfg)
        return cfg["repetir"]
    except Exception as e:
        print(f"No se pudo cambiar la repetición: {e}")
        return True


def estado_actual():
    """Foto para la UI (Fase 3/4). Nunca lanza."""
    try:
        return {
            "rel": _sesion["rel"],
            "titulo": os.path.splitext(os.path.basename(_sesion["rel"]))[0] if _sesion["rel"] else None,
            "estado": _sesion["estado"],
            "cursor_ms": float(_sesion["cursor_ms"] or 0.0),
            "duracion_ms": float(_sesion["duracion_ms"] or 0.0),
            "repetir": repetir(),
        }
    except Exception:
        return {"rel": None, "titulo": None, "estado": "DETENIDA",
                "cursor_ms": 0.0, "duracion_ms": 0.0, "repetir": True}


def _hacer_reproducir(rel, token):
    """Carga el tema en OBS y lo larga (sincrónico, para tests y para
    el hilo de las versiones públicas). Acepta rel a Musica o ruta
    absoluta (esta última es el selector provisorio de Fase 3 y no
    entra en recientes)."""
    if token is not None and token != _sesion["token"]:
        return False
    if not E.conectado:
        print("Sin conexión: conectate a OBS para la música.")
        return False
    try:
        es_absoluta = os.path.isabs(rel)
    except Exception:
        es_absoluta = False
    ruta_abs = rel if es_absoluta else _absoluta(rel)
    try:
        E.cliente_obs.set_input_settings(
            C.NOMBRE_FUENTE_MUSICA,
            {
                "local_file": mod_rutas_obs.resolver_para_obs(ruta_abs),
                "is_local_file": True,
                "looping": False,
                "restart_on_activate": False,
                "close_when_inactive": False,
            },
            True
        )
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_MUSICA, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
        )
    except Exception as e:
        print(f"No se pudo reproducir la música {rel}: {e}")
        return False
    _sesion["rel"] = rel
    _sesion["archivo"] = ruta_abs
    _sesion["estado"] = "SONANDO"
    _sesion["crudo"] = "OBS_MEDIA_STATE_PLAYING"
    _sesion["cursor_ms"] = 0.0
    if not es_absoluta:
        _tocar_reciente(rel)
    asegurar_sondeo()
    return True


def _hacer_accion(accion):
    try:
        E.cliente_obs.trigger_media_input_action(C.NOMBRE_FUENTE_MUSICA, accion)
        return True
    except Exception as e:
        print(f"No se pudo mandar {accion} a la música: {e}")
        return False


def _en_hilo(funcion, *args):
    threading.Thread(target=funcion, args=args, daemon=True).start()


def reproducir_lista(lista, indice=0):
    """Pone la cola y larga el tema indicado (versión pública, en hilo)."""
    if not lista:
        return
    try:
        indice = max(0, min(int(indice), len(lista) - 1))
    except Exception:
        indice = 0
    _cola[:] = list(lista)
    _sesion["indice_cola"] = indice
    _sesion["token"] += 1
    _en_hilo(_hacer_reproducir, lista[indice], _sesion["token"])


def reproducir_rel(rel):
    """Atajo: cola de un solo tema (versión pública, en hilo)."""
    reproducir_lista([rel], 0)


def reproducir_archivo(ruta_abs):
    """Reproduce un archivo suelto por ruta absoluta (selector
    provisorio del mini player en Fase 3; en Fase 4 la biblioteca
    reemplaza este camino y todo pasa por rels)."""
    if not ruta_abs or not os.path.isabs(ruta_abs):
        return
    reproducir_lista([os.path.normpath(ruta_abs)], 0)


def _avanzar(auto):
    """Pasa al siguiente tema de la cola (con vuelta si repetir).
    auto=True viene del fin natural; manual siempre avanza."""
    if not _cola:
        return
    if auto and not repetir():
        _sesion["estado"] = "DETENIDA"
        return
    base = _sesion.get("indice_cola")
    try:
        base = int(base) if base is not None else -1
    except Exception:
        base = -1
    siguiente = (base + 1) % len(_cola)
    _sesion["indice_cola"] = siguiente
    _sesion["token"] += 1
    if auto:
        _hacer_reproducir(_cola[siguiente], _sesion["token"])
    else:
        _en_hilo(_hacer_reproducir, _cola[siguiente], _sesion["token"])


def siguiente():
    """Tema siguiente (manual, con vuelta)."""
    _en_hilo(_avanzar_si_hay_cola, 1)


def anterior():
    """Tema anterior (manual, con vuelta): retrocede y reproduce."""
    _en_hilo(_retroceder_si_hay_cola)


def _avanzar_si_hay_cola(_paso):
    if _cola:
        _avanzar(auto=False)


def _retroceder_si_hay_cola():
    if not _cola:
        return
    base = _sesion.get("indice_cola")
    try:
        base = int(base) if base is not None else 0
    except Exception:
        base = 0
    _sesion["indice_cola"] = (base - 1) % len(_cola)
    _sesion["token"] += 1
    _hacer_reproducir(_cola[_sesion["indice_cola"]], _sesion["token"])


def pausar():
    if E.conectado:
        _en_hilo(_hacer_accion, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE")


def reanudar():
    """PLAY si estaba pausada, RESTART en cualquier otro caso (quirk:
    después de STOP, PLAY no reanuda)."""
    if not E.conectado:
        return
    if _sesion.get("crudo") == "OBS_MEDIA_STATE_PAUSED":
        _en_hilo(_hacer_accion, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY")
    elif _sesion.get("archivo"):
        _sesion["token"] += 1
        _en_hilo(_hacer_reproducir, _sesion["rel"], _sesion["token"])


def detener():
    """STOP manual: no avanza solo (el avance solo reacciona a ENDED)."""
    if not E.conectado:
        return
    _en_hilo(_hacer_detener)


def _hacer_detener():
    if _hacer_accion("OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"):
        _sesion["estado"] = "DETENIDA"
        _sesion["crudo"] = "OBS_MEDIA_STATE_STOPPED"


def reiniciar():
    if E.conectado and _sesion.get("archivo"):
        _en_hilo(_hacer_accion, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")


def seek_ms(milisegundos):
    """Salta al momento exacto (clic en la barra, Fase 3)."""
    if not E.conectado or not _sesion.get("archivo"):
        return
    try:
        destino = max(0.0, float(milisegundos))
        if _sesion.get("duracion_ms"):
            destino = min(destino, float(_sesion["duracion_ms"]))
    except Exception:
        return
    _en_hilo(_hacer_seek, destino)


def _hacer_seek(destino):
    try:
        E.cliente_obs.set_media_input_cursor(C.NOMBRE_FUENTE_MUSICA, float(destino))
    except Exception as e:
        print(f"No se pudo saltar la música a {destino} ms: {e}")


def _sondear_una_vez():
    """Un ciclo de sondeo (sincrónico, testeable): actualiza
    estado/cursor/duración y auto-avanza SOLO ante ENDED natural."""
    if not E.conectado or not _sesion.get("archivo"):
        return
    try:
        respuesta = E.cliente_obs.get_media_input_status(C.NOMBRE_FUENTE_MUSICA)
    except Exception as e:
        print(f"No se pudo sondear la música: {e}")
        return
    crudo = mod_obs_eventos._valor(respuesta, "media_state", "mediaState")
    try:
        cursor = mod_obs_eventos._valor(respuesta, "media_cursor", "mediaCursor")
        duracion = mod_obs_eventos._valor(respuesta, "media_duration", "mediaDuration")
        if cursor is not None:
            _sesion["cursor_ms"] = float(cursor)
        if duracion is not None:
            _sesion["duracion_ms"] = float(duracion)
    except Exception:
        pass
    if not crudo:
        return
    _sesion["crudo"] = crudo
    if crudo == "OBS_MEDIA_STATE_PLAYING":
        _sesion["estado"] = "SONANDO"
    elif crudo == "OBS_MEDIA_STATE_PAUSED":
        _sesion["estado"] = "PAUSADA"
    elif crudo in ("OBS_MEDIA_STATE_OPENING", "OBS_MEDIA_STATE_BUFFERING"):
        _sesion["estado"] = "ABRIENDO"
    elif crudo == "OBS_MEDIA_STATE_ENDED":
        _sesion["estado"] = "DETENIDA"
        _avanzar(auto=True)
    elif crudo in C.ESTADOS_MEDIA_DETENIDO:
        _sesion["estado"] = "DETENIDA"


def _bucle_sondeo():
    while True:
        try:
            _sondear_una_vez()
        except Exception as e:
            print(f"Error en el sondeo de música: {e}")
        time.sleep(C.INTERVALO_SONDEO_MUSICA_MS / 1000.0)


def asegurar_sondeo():
    """Arranca el hilo de sondeo una sola vez (idempotente)."""
    if _sondeo["en_marcha"]:
        return
    _sondeo["en_marcha"] = True
    threading.Thread(target=_bucle_sondeo, daemon=True).start()


def detener_y_vaciar_musica():
    """STOP + vaciado para el cierre/desconexión (Fase 5): así OBS no
    auto-reproduce al abrirse. Sin audio local que cortar (la música
    nunca sale por parlantes)."""
    _sesion["rel"] = None
    _sesion["archivo"] = None
    _sesion["indice_cola"] = None
    _sesion["estado"] = "DETENIDA"
    _sesion["crudo"] = None
    _sesion["cursor_ms"] = 0.0
    _sesion["duracion_ms"] = 0.0
    if not E.conectado:
        return
    try:
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_MUSICA, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        )
    except Exception:
        pass
    try:
        E.cliente_obs.set_input_settings(
            C.NOMBRE_FUENTE_MUSICA,
            {"local_file": "", "looping": False},
            True
        )
    except Exception as e:
        print(f"No se pudo vaciar la fuente de música: {e}")
