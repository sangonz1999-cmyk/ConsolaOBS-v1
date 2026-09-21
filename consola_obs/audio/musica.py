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
    # Confirmación post-seek: {"destino": ms, "t": monotonic}. Mientras
    # está vigente (2 s), el sondeo solo acepta lo que confirme el
    # destino e ignora los ceros/nulos transitorios que OBS manda al
    # buscar en pausa (si no, la barra se borra).
    "seek_pendiente": None,
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


MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic")


def formatear_fecha(timestamp):
    """segundos epoch -> '18 ago 2026' (columna de la tabla)."""
    try:
        import datetime
        f = datetime.datetime.fromtimestamp(float(timestamp))
        return f"{f.day} {MESES_ES[f.month - 1]} {f.year}"
    except Exception:
        return "--"


def fecha_de_archivo(ruta_abs):
    """Fecha de agregado (mtime del archivo) o '--'."""
    try:
        return formatear_fecha(os.path.getmtime(ruta_abs))
    except Exception:
        return "--"


def album_de_rel(rel):
    """La carpeta actúa como álbum; lo suelto es 'General'."""
    try:
        carpeta = os.path.dirname(rel)
        return carpeta if carpeta else "General"
    except Exception:
        return "General"


def leer_duracion_local(ruta_abs):
    """Duración en ms decodificando con miniaudio (None si no se
    puede). Se lee a bytes con Python y se decodifica en memoria
    porque miniaudio no abre en Windows rutas con caracteres raros
    (｜, emojis, etc.): falla aunque el archivo esté perfecto."""
    try:
        with open(ruta_abs, "rb") as f:
            crudo = f.read()
    except Exception:
        return None
    if not crudo:
        return None
    try:
        import miniaudio
        decodificado = miniaudio.decode(crudo)
        ncan = max(1, decodificado.nchannels or 1)
        rate = max(1, decodificado.sample_rate or 1)
        ms = len(decodificado.samples) / ncan / rate * 1000.0
        return ms if ms > 0 else None
    except Exception:
        return None


def _firma_archivo(ruta_abs):
    try:
        st = os.stat(ruta_abs)
        return [st.st_size, int(st.st_mtime)]
    except Exception:
        return None


def duracion_cacheada(rel):
    """Duración desde el caché SIN decodificar (None si no está o el
    archivo cambió). Para pintar la tabla sin congelar la UI; el hilo
    de relleno del panel usa duracion_de()."""
    try:
        mem = _dur_mem.get(rel)
        ruta_abs = _absoluta_si_rel(rel)
        firma = _firma_archivo(ruta_abs)
        if firma is None:
            return None
        if isinstance(mem, dict) and mem.get("firma") == firma and mem.get("ms"):
            return float(mem["ms"])
        caché = _config().get("duraciones") or {}
        vieja = caché.get(rel)
        if isinstance(vieja, dict) and vieja.get("firma") == firma and vieja.get("ms"):
            return float(vieja["ms"])
        return None
    except Exception:
        return None


# Duraciones decodificadas pendientes de persistir + último flush.
# Sin esto, abrir la biblioteca con cientos de temas disparaba un
# guardado de JSON por tema y los writes chocaban entre sí y con el
# antivirus (WinError 5 en Windows).
_dur_mem = {}
_flush_dur = {"t": 0.0}
INTERVALO_FLUSH_DURACIONES_SEG = 5.0


def _flush_duraciones(forzar=False):
    """Vuelca las duraciones pendientes al JSON (con debounce de 5 s,
    o ya si forzar=True). Devuelve True si no quedó nada pendiente."""
    if not _dur_mem:
        return True
    try:
        ahora = time.monotonic()
    except Exception:
        ahora = 0.0
    if not forzar and (ahora - _flush_dur.get("t", 0.0)) < INTERVALO_FLUSH_DURACIONES_SEG:
        return False
    try:
        cfg = _config()
        caché = cfg.get("duraciones") or {}
        caché.update(_dur_mem)
        cfg["duraciones"] = caché
        if mod_configuracion.guardar_config_musica(cfg):
            _dur_mem.clear()
            _flush_dur["t"] = ahora
            return True
        return False
    except Exception as e:
        print(f"No se pudo persistir duraciones: {e}")
        return False


def duracion_de(rel):
    """Duración en ms con caché persistente (config): la primera vez
    decodifica, después sale del JSON. El guardado va con debounce
    para no aporrear el disco. None si no se pudo."""
    try:
        ms = duracion_cacheada(rel)
        if ms:
            return ms
        ruta_abs = _absoluta_si_rel(rel)
        if _firma_archivo(ruta_abs) is None:
            return None
        ms = leer_duracion_local(ruta_abs)
        if ms:
            _dur_mem[rel] = {"ms": ms, "firma": _firma_archivo(ruta_abs)}
            _flush_duraciones()
            return float(ms)
        return None
    except Exception:
        return None


def _absoluta_si_rel(rel):
    try:
        if os.path.isabs(rel):
            return rel
        return _absoluta(rel)
    except Exception:
        return rel


def obtener_playlist():
    """La playlist actual (copia, tal cual está guardada)."""
    try:
        lista = [r for r in _config().get("playlist", []) if isinstance(r, str)]
    except Exception:
        lista = []
    return lista


def playlist_actual():
    """Playlist podada a archivos existentes (copia). Es lo que se
    muestra y reproduce."""
    try:
        return [r for r in obtener_playlist()
                if isinstance(r, str) and os.path.isfile(_absoluta_si_rel(r))]
    except Exception:
        return []


def ruta_absoluta(rel):
    """Absoluta local de un rel (o tal cual si ya es absoluta)."""
    return _absoluta_si_rel(rel)


def _playlist_existente():
    try:
        return [r for r in obtener_playlist()
                if os.path.isfile(_absoluta_si_rel(r))]
    except Exception:
        return []


def definir_playlist(lista):
    """Reemplaza la playlist actual (y la cola) y la guarda. Solo
    acepta rels a la biblioteca: las rutas absolutas (pistas sueltas
    provisorias) suenan en memoria pero no se persisten, para que no
    quede basura como pistas del Temp en la playlist guardada."""
    try:
        limpia = [r for r in list(lista)
                  if isinstance(r, str) and r and not os.path.isabs(r)]
    except Exception:
        limpia = []
    _cola[:] = limpia
    try:
        cfg = _config()
        cfg["playlist"] = limpia
        mod_configuracion.guardar_config_musica(cfg)
    except Exception as e:
        print(f"No se pudo guardar la playlist: {e}")
    return list(limpia)


def agregar_a_playlist(rel):
    """Suma al final (sin duplicar el mismo). Devuelve True si entró."""
    if not isinstance(rel, str) or not rel:
        return False
    actual = _playlist_existente()
    if rel in actual:
        _cola[:] = actual
        return False
    actual.append(rel)
    definir_playlist(actual)
    return True


def sacar_de_playlist(indice):
    """Saca por posición. Si era el tema sonando, avanza (o frena)."""
    actual = _playlist_existente()
    try:
        indice = int(indice)
    except Exception:
        return False
    if not 0 <= indice < len(actual):
        return False
    era_actual = (_sesion.get("rel") == actual[indice])
    actual.pop(indice)
    definir_playlist(actual)
    if era_actual:
        if actual:
            _sesion["indice_cola"] = min(indice, len(actual) - 1)
            _sesion["token"] += 1
            _en_hilo(_hacer_reproducir, actual[_sesion["indice_cola"]], _sesion["token"])
        else:
            detener()
    return True


def mover_en_playlist(origen, destino):
    """Reordena dentro de la playlist (drag & drop interno)."""
    actual = _playlist_existente()
    try:
        origen, destino = int(origen), int(destino)
    except Exception:
        return False
    if not 0 <= origen < len(actual) or not 0 <= destino < len(actual):
        return False
    if origen == destino:
        return True
    tema = actual.pop(origen)
    actual.insert(destino, tema)
    # El índice de lo que suena se recalcula por identidad.
    try:
        _sesion["indice_cola"] = actual.index(_sesion["rel"]) if _sesion.get("rel") in actual else None
    except Exception:
        pass
    definir_playlist(actual)
    return True


def reproducir_playlist(indice):
    """Reproduce la playlist actual desde una posición."""
    actual = _playlist_existente()
    if not actual:
        return
    try:
        indice = max(0, min(int(indice), len(actual) - 1))
    except Exception:
        indice = 0
    reproducir_lista(actual, indice)


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


def mezclar():
    """Aleatorio real (no solo el icono): True = el siguiente tema se
    elige al azar sin repetir el actual."""
    try:
        return bool(_config().get("mezclar", False))
    except Exception:
        return False


def modo():
    """Modo de reproducción: repetir, mezclar u off."""
    try:
        if mezclar():
            return "mezclar"
        return "repetir" if repetir() else "off"
    except Exception:
        return "repetir"


def alternar_modo():
    """El botón recorre repetir -> mezclar -> apagado -> repetir.
    Mezclar implica no frenar nunca (siempre hay siguiente)."""
    try:
        actual = modo()
        cfg = _config()
        if actual == "repetir":
            cfg["mezclar"] = True
        elif actual == "mezclar":
            cfg["mezclar"] = False
            cfg["repetir"] = False
        else:
            cfg["repetir"] = True
        mod_configuracion.guardar_config_musica(cfg)
        return modo()
    except Exception as e:
        print(f"No se pudo cambiar el modo: {e}")
        return modo()


def alternar_repetir():
    """Invierte repetir-lista y devuelve el nuevo valor (compat: lo
    usa el ciclo del botón cuando sale de apagado)."""
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
                "mezclar": mezclar(),
                "modo": modo(),
            }
    except Exception:
        return {"rel": None, "titulo": None, "estado": "DETENIDA",
                "cursor_ms": 0.0, "duracion_ms": 0.0, "repetir": True,
                "mezclar": False, "modo": "repetir"}


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
        base_ok = mod_rutas_obs.base_obs_lista_o_avisar()
    except Exception:
        base_ok = True
    if not base_ok:
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
    _sesion["seek_pendiente"] = None
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


def _largar_lista(lista, indice):
    """Pone la cola en memoria y larga el tema (sin guardar nada)."""
    _cola[:] = list(lista)
    _sesion["indice_cola"] = indice
    _sesion["token"] += 1
    _en_hilo(_hacer_reproducir, list(lista)[indice], _sesion["token"])


def reproducir_lista(lista, indice=0):
    """Pone la cola, la guarda como playlist actual y larga el tema
    indicado (versión pública, en hilo). Para sonar SIN tocar la
    playlist (carpeta directa) usar reproducir_sesion."""
    if not lista:
        return
    try:
        indice = max(0, min(int(indice), len(lista) - 1))
    except Exception:
        indice = 0
    definir_playlist(lista)
    _largar_lista(list(lista), indice)


def reproducir_sesion(lista, indice=0):
    """Larga una lista SIN guardarla como playlist (carpeta directa):
    la playlist actual queda intacta."""
    try:
        lista = list(lista)
    except Exception:
        return
    if not lista:
        return
    try:
        indice = max(0, min(int(indice), len(lista) - 1))
    except Exception:
        indice = 0
    _largar_lista(lista, indice)


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


def _indice_sano():
    """Índice válido del tema que suena dentro de la cola (se
    auto-repara por identidad si el índice guardado quedó viejo tras
    agregar/sacar/mover). None si no se puede saber."""
    try:
        if _sesion.get("rel") in _cola:
            return _cola.index(_sesion["rel"])
    except Exception:
        pass
    try:
        i = _sesion.get("indice_cola")
        if i is not None and 0 <= int(i) < len(_cola):
            return int(i)
    except Exception:
        pass
    return None


def _indice_siguiente():
    """Índice del próximo tema o None (frenar). Con mezclar elige al
    azar sin repetir el actual; si no, el siguiente con vuelta."""
    n = len(_cola)
    if n == 0:
        return None
    if _mezclar_activo() and n > 1:
        import random as _r
        base = _indice_sano()
        candidatos = [i for i in range(n) if i != base]
        return _r.choice(candidatos) if candidatos else 0
    base = _indice_sano()
    if base is None:
        base = -1
    return (base + 1) % n


def _mezclar_activo():
    try:
        return bool(mezclar())
    except Exception:
        return False


def _avanzar(auto):
    """Avanza (fin natural con auto=True, manual con False). Con
    mezclar nunca frena; sin repetir ni mezclar, el fin natural frena
    pero el manual da la vuelta igual."""
    if not _cola:
        return
    if auto and not (repetir() or _mezclar_activo()):
        _sesion["estado"] = "DETENIDA"
        return
    siguiente = _indice_siguiente()
    if siguiente is None:
        _sesion["estado"] = "DETENIDA"
        return
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
    # Estilo Spotify: si pasaron más de 3 s, anterior reinicia el
    # tema actual en vez de cambiar (si no, un toque accidental te
    # saca del tema). Si no, va al anterior con vuelta.
    if not _cola:
        return
    try:
        cursor = float(_sesion.get("cursor_ms") or 0.0)
    except Exception:
        cursor = 0.0
    if cursor > 3000.0 and _sesion.get("rel"):
        _sesion["cursor_ms"] = 0.0
        _hacer_accion("OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
        return
    base = _indice_sano()
    if base is None:
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
    """Salta al momento exacto (clic en la barra, Fase 3). Muestra el
    destino en el acto (update optimista: la UI lo levanta en el
    próximo refresco, esté sonando o en pausa) y abre una ventana de
    confirmación de 2 s donde el sondeo solo acepta lo que confirme
    el destino; los ceros/nulos transitorios que OBS manda al buscar
    en pausa se ignoran para que la barra no se borre."""
    if not E.conectado or not _sesion.get("archivo"):
        return
    try:
        destino = max(0.0, float(milisegundos))
        if _sesion.get("duracion_ms"):
            destino = min(destino, float(_sesion["duracion_ms"]))
    except Exception:
        return
    _sesion["cursor_ms"] = destino
    _sesion["seek_pendiente"] = {"destino": destino, "t": time.monotonic()}
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
        cursor = float(cursor) if cursor is not None else None
        duracion = float(duracion) if duracion is not None else None
    except Exception:
        cursor, duracion = None, None
    # Duración: nunca pisar un valor conocido con 0/None (OBS los
    # manda transitorios al buscar en pausa).
    if duracion is not None and duracion > 0:
        _sesion["duracion_ms"] = duracion
    elif not _sesion.get("duracion_ms"):
        _sesion["duracion_ms"] = 0.0
    # Cursor: ventana de confirmación post-seek (2 s). Ahí solo vale
    # lo que confirme el destino; el resto se ignora para que la
    # barra no se borre al buscar en pausa. Vencida, se confía en OBS.
    ahora = time.monotonic()
    pend = _sesion.get("seek_pendiente")
    if pend is not None and (ahora - pend.get("t", 0)) >= 2.0:
        _sesion["seek_pendiente"] = None
        pend = None
    if cursor is None:
        pass
    elif pend is not None:
        if abs(cursor - pend["destino"]) < 2000.0:
            _sesion["cursor_ms"] = cursor
            _sesion["seek_pendiente"] = None
    else:
        _sesion["cursor_ms"] = cursor
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
    _sesion["seek_pendiente"] = None
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
