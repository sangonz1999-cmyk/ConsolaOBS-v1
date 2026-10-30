"""Motor de música de fondo para el stream (Fase 2 del plan de música).

Arquitectura "el programa manda, OBS ejecuta": la biblioteca, la cola
y el transporte viven acá; OBS solo tiene la fuente tonta 'Musica'
(ffmpeg_source, sin loop) y obedece. La música sale SIEMPRE por el
stream; por los parlantes de la PC sólo si el sonidista activa "Música
en PC" en Ajustes > Audio (motor_local, miniaudio), y entonces el
transporte (play/pausa/stop/seek) y el fader de la fuente Musica se
replican en el motor local.

Sincronía con OBS (sólo con "Música en PC" activa): OBS SIEMPRE manda y
nunca se corrige; sólo se ajusta el audio local.
- Al conectar con OBS vacío y el local sonando: el local se pausa, OBS
  no se toca, y al dar play se carga el tema en OBS en la posición del
  local y arrancan juntos (ver al_conectar_obs / _hacer_reproducir).
- Al conectar con OBS sonando o en pausa: el local salta a la posición
  de OBS y copia su estado. Si el tema de OBS no está en la biblioteca,
  el local se saca y OBS queda como está.
- Mientras suenan los dos, un bucle propio (_bucle_sincronia, cada
  250 ms) compara el audio local contra el RELOJ MAESTRO (la última
  posición que informó OBS, interpolada). Hasta UMBRAL_DERIVA_MS no se
  toca nada; si difieren más, el local salta a la posición de OBS, y si
  la diferencia es enorme (UMBRAL_SALTO_MS: uno en la mitad del tema y
  el otro al principio) se corrige enseguida. El mismo bucle copia la
  pausa/play de OBS y relanza el local si se cayó.
- Si alguien cambia el tema desde OBS, el programa lo detecta (lee el
  archivo de la fuente cada ~2 s) y se sincroniza con ese tema.
- Un seek (clic en la barra) va a OBS y al local con el MISMO destino y
  abre una ventana de protección: los estados transitorios de OBS al
  buscar (STOPPED/ENDED) no cortan el local ni saltan al tema siguiente.

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
from consola_obs.audio import motor_local as mod_motor_local
from consola_obs.audio import volumen_salida as mod_volumen_salida

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
    # Sincronía local<->OBS. 'pendiente_obs': OBS está vacío y el local
    # quedó en pausa esperando el play (que carga el tema en OBS en la
    # posición del local). 'obs_ajeno': OBS suena un tema que no está en
    # la biblioteca y no se le toca nada. 'sync_hasta': mientras dura la
    # sincronización de la conexión el sondeo no pisa el estado.
    "pendiente_obs": False, "obs_ajeno": False,
    "sync_hasta": 0.0, "ultima_correccion_t": 0.0, "cliente_sync": None,
    # Estado que OBS tiene que informar para cerrar la ventana de acción
    # (None = esperar a que venza). Ver _marcar_accion().
    "accion_esperada": None,
}
_cola = []
_sondeo = {"en_marcha": False}


# Diferencia tolerada entre el audio local y OBS: hasta acá no se toca
# nada (nadie la nota y así no hay microcortes por corregir de más).
UMBRAL_DERIVA_MS = 700.0
# Diferencia "enorme" (uno en la mitad del tema y el otro al principio):
# se corrige enseguida, sin la espera normal entre correcciones.
UMBRAL_SALTO_MS = 1500.0
# Cuando OBS confirma un seek, la posición real a la que quedó puede
# diferir del destino pedido (redondeo del cursor, keyframes): si el
# local quedó más lejos que esto, se lo alinea con lo que OBS confirmó
# (OBS manda). Por debajo es ruido de medición y no se toca.
UMBRAL_REALINEO_MS = 250.0
# Tras arrancar un tema no se compara (OBS puede seguir informando el
# cursor del tema anterior hasta aplicar el RESTART).
GRACIA_DERIVA_SEG = 2.5
# Entre dos correcciones seguidas (evita cortes repetidos).
ESPERA_ENTRE_CORRECCIONES_SEG = 1.5
ESPERA_SALTO_SEG = 1.0
# Cada cuánto el bucle de sincronía compara el local con el reloj maestro
# (no consulta a OBS: usa la última posición informada, interpolada).
INTERVALO_SINCRONIA_SEG = 0.25
# Tras un seek, durante este tiempo se ignoran los STOPPED/ENDED
# transitorios de OBS (y no se espeja pausa/play).
SEEK_PROTEGER_SEG = 4.0
# Tras una acción del sonidista no se espeja el estado de OBS al local
# (OBS tarda en reflejar el cambio).
ESPERA_TRAS_ACCION_SEG = 3.0
# Seguimiento del archivo que tiene OBS cargado (cambio hecho en OBS).
INTERVALO_LEER_ARCHIVO_SEG = 2.0
GRACIA_ARCHIVO_SEG = 6.0
# Relanzar el local si se cayó mientras OBS sigue sonando.
ESPERA_RECUPERACION_SEG = 3.0
# Log de la deriva medida (diagnóstico).
INTERVALO_LOG_DERIVA_SEG = 15.0
# Tope de espera de la sincronización de la conexión.
MAX_SYNC_CONEXION_SEG = 10.0

_ESTADOS_ACTIVOS = ("SONANDO", "PAUSADA", "ABRIENDO")
_PAUSE = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE"
_PLAY = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY"
_RESTART = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"


def _log_sync(texto):
    """Diagnóstico de la sincronía local<->OBS (config/conexion.log)."""
    try:
        from consola_obs import red as mod_red
        mod_red.log_conexion("SYNC", texto)
    except Exception:
        pass


def _obs_pendiente():
    """True si OBS está conectado pero vacío y el local espera el play."""
    try:
        return bool(_sesion.get("pendiente_obs")) and bool(E.conectado)
    except Exception:
        return False


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


def _musica_en_escena():
    """True si la fuente Música está en la escena al aire (o no se sabe:
    sin dato no se castiga). La vista lo usa para congelar o interpolar."""
    try:
        w = (E.fuentes or {}).get(C.NOMBRE_FUENTE_MUSICA)
        if not w:
            return True
        return bool(w.get("en_escena", True))
    except Exception:
        return True


def _anclar_cursor(valor, t=None):
    """Fija cursor + base del reloj maestro (para interpolar entre
    sondeos). 't' es el instante (monotonic) en que se midió el valor;
    por defecto, ahora."""
    try:
        _sesion["cursor_ms"] = float(valor)
        _sesion["cursor_base_ms"] = float(valor)
        _sesion["cursor_base_t"] = float(t) if t is not None else time.monotonic()
    except Exception:
        pass


def _marcar_accion(esperado=None):
    """Anota que el sonidista acaba de tocar el transporte: durante unos
    segundos no se espeja el estado de OBS al local (OBS tarda en
    reflejar el cambio). 'esperado' es el estado que tiene que informar
    OBS para dar la acción por aplicada: en cuanto aparece, la ventana se
    cierra, así un toque posterior en OBS (pausa/play) se sigue al
    instante en vez de quedar ignorado hasta 3 s después."""
    try:
        _sesion["ultima_accion_t"] = time.monotonic()
        _sesion["accion_esperada"] = esperado
    except Exception:
        pass


def _proteger_seek(al_final=False):
    """Abre la ventana en la que los estados transitorios de OBS al
    buscar no cortan el local ni saltan al tema siguiente."""
    try:
        ahora = time.monotonic()
        _sesion["seek_proteger_hasta"] = ahora + SEEK_PROTEGER_SEG
        _sesion["seek_al_final"] = bool(al_final)
        # Mientras el local aplica el seek no se lo compara con OBS.
        _sesion["ultima_correccion_t"] = ahora
    except Exception:
        pass


def _reloj_maestro_ms():
    """Posición actual de OBS según el reloj maestro (última posición
    informada + tiempo corrido, sin pasarse de la duración). None si
    todavía no hay ancla."""
    try:
        base_t = float(_sesion.get("cursor_base_t") or 0.0)
        if base_t <= 0:
            return None
        cur = float(_sesion.get("cursor_base_ms") or 0.0)
        cur += (time.monotonic() - base_t) * 1000.0
        dur = float(_sesion.get("duracion_ms") or 0.0)
        if dur > 0:
            cur = min(cur, dur)
        return max(0.0, cur)
    except Exception:
        return None


def ganancia_desde_pct(pct):
    """Curva del control de volumen de la PC: 0-100 % -> ganancia lineal.
    Es cuadrática porque el oído no percibe el volumen en forma lineal:
    100 % = sin cambios, 50 % = -12 dB (se oye más o menos a la mitad),
    25 % = -24 dB, 2 % = casi silencio."""
    try:
        p = max(0.0, min(100.0, float(pct))) / 100.0
    except Exception:
        p = 1.0
    return p * p


def _volumen_musica_pc():
    """Volumen propio de la música en los parlantes (barra del mini
    player), como ganancia lineal 0.0 a 1.0. No toca OBS."""
    try:
        return ganancia_desde_pct(
            E.config_interfaz_previa.get("volumen_musica_pc", 100.0))
    except Exception:
        return 1.0


def _ganancia_musica_lineal():
    """Ganancia lineal (0.0 a 1.0) del audio LOCAL (parlantes de la PC).
    Depende SOLO de la barra de volumen del mini player (más el volumen
    general de Ajustes > Audio, hoy fijo en 1.0): el fader y el mute de
    la fuente Música de OBS mandan en el stream y no tocan los
    parlantes."""
    try:
        return mod_volumen_salida.factor_pc() * _volumen_musica_pc()
    except Exception:
        return 1.0


def _musica_en_parlantes():
    try:
        return bool(getattr(E, "musica_en_parlantes", False))
    except Exception:
        return False


def nota_volumen_musica():
    """El fader (o el mute) de la fuente Musica cambió, acá o en OBS:
    el audio local lo sigue en vivo. Nunca lanza."""
    try:
        if mod_motor_local.hay_sesion():
            mod_motor_local.fijar_ganancia(_ganancia_musica_lineal())
    except Exception:
        pass


def _arrancar_local(ruta_abs, inicio_ms=0.0, pausado=False):
    """Lanza la pista por los parlantes si la opción está activa."""
    if not _musica_en_parlantes():
        return
    try:
        mod_motor_local.reproducir(
            ruta_abs, _sesion.get("token"), _ganancia_musica_lineal(),
            inicio_ms=inicio_ms, pausado=pausado)
    except Exception as e:
        print(f"No se pudo lanzar la música por los parlantes: {e}")


def cambiar_musica_en_parlantes(valor):
    """Se llama desde el combobox 'Música en PC' del menú de ajustes.
    Al activarla con un tema en curso, el audio local se engancha en el
    punto donde va (y respeta la pausa); al apagarla se corta."""
    E.musica_en_parlantes = (valor == "Sí")
    mod_configuracion.guardar_config_interfaz(
        {"musica_en_parlantes": E.musica_en_parlantes})
    if not E.musica_en_parlantes:
        mod_motor_local.detener()
        if _sesion.get("pendiente_obs"):
            # Sin audio local ya no hay nada esperando el play.
            _sesion["pendiente_obs"] = False
            _sesion["estado"] = "DETENIDA"
            _sesion["crudo"] = "OBS_MEDIA_STATE_STOPPED"
        return
    try:
        archivo = _sesion.get("archivo")
        if archivo and _sesion.get("estado") in ("SONANDO", "PAUSADA", "ABRIENDO"):
            cursor = float(estado_actual().get("cursor_ms") or 0.0)
            _arrancar_local(archivo, inicio_ms=cursor,
                            pausado=(_sesion.get("estado") == "PAUSADA"))
    except Exception as e:
        print(f"No se pudo enganchar la música a los parlantes: {e}")


def estado_actual():
    """Foto para la UI (Fase 3/4). Nunca lanza."""
    try:
        snap = {
            "rel": _sesion["rel"],
            "titulo": os.path.splitext(os.path.basename(_sesion["rel"]))[0] if _sesion["rel"] else None,
            "estado": _sesion["estado"],
                "cursor_ms": float(_sesion["cursor_ms"] or 0.0),
                "duracion_ms": float(_sesion["duracion_ms"] or 0.0),
                "repetir": repetir(),
                "mezclar": mezclar(),
                "modo": modo(),
            }
        # Reloj local: entre sondeos de OBS (500 ms) la barra avanzaría
        # a saltos; interpolada se mueve fluida. Sólo sonando Y a la
        # vista: fuera de escena se congela donde quedó (al volver, el
        # sondeo re-ancla con lo real de OBS).
        try:
            if snap["estado"] == "SONANDO" and _musica_en_escena():
                base_t = float(_sesion.get("cursor_base_t") or 0.0)
                if base_t > 0:
                    cur = float(_sesion.get("cursor_base_ms") or 0.0)
                    cur += (time.monotonic() - base_t) * 1000.0
                    dur = float(_sesion.get("duracion_ms") or 0.0)
                    if dur > 0:
                        cur = min(cur, dur)
                    snap["cursor_ms"] = max(0.0, cur)
        except Exception:
            pass
        return snap
    except Exception:
        return {"rel": None, "titulo": None, "estado": "DETENIDA",
                "cursor_ms": 0.0, "duracion_ms": 0.0, "repetir": True,
                "mezclar": False, "modo": "repetir"}


def _hacer_reproducir(rel, token, inicio_ms=0.0, reusar_local=False):
    """Carga el tema en OBS y lo larga (sincrónico, para tests y para
    el hilo de las versiones públicas). Acepta rel a Musica o ruta
    absoluta (esta última es el selector provisorio de Fase 3 y no
    entra en recientes).

    inicio_ms > 0: arranque sincronizado (OBS estaba vacío y el local
    esperaba el play): se carga el tema en OBS, se lo deja en pausa en
    esa posición y recién entonces OBS y el local arrancan juntos.
    reusar_local: el audio local ya está cargado (en pausa) y sólo se
    alinea y reanuda, sin volver a decodificar."""
    if token is not None and token != _sesion["token"]:
        return False
    _marcar_accion()
    if not E.conectado:
        # Sin OBS: sonar sólo por los parlantes de la PC si está habilitado.
        if not _musica_en_parlantes():
            print("Sin conexión: conectate a OBS para la música.")
            return False
        try:
            es_absoluta = os.path.isabs(rel)
        except Exception:
            es_absoluta = False
        ruta_abs = rel if es_absoluta else _absoluta(rel)
        _sesion["pendiente_obs"] = False
        _sesion["obs_ajeno"] = False
        _sesion["rel"] = rel
        _sesion["archivo"] = ruta_abs
        _sesion["estado"] = "SONANDO"
        _sesion["crudo"] = "OBS_MEDIA_STATE_PLAYING"
        _sesion["inicio_t"] = time.monotonic()
        _anclar_cursor(0.0)
        _arrancar_local(ruta_abs)
        _sesion["seek_pendiente"] = None
        # Sin OBS nadie informa la duración: se lee del archivo (después
        # de arrancar el audio, así no demora el inicio del tema).
        _sesion["duracion_ms"] = 0.0
        asegurar_duracion()
        if not es_absoluta:
            _tocar_reciente(rel)
        asegurar_sondeo()
        return True
    try:
        if getattr(E, "_cerrando", False):
            return False
    except Exception:
        pass
    # Escena al aire NO permitida: la música (sólo-stream por diseño,
    # sin salida local) no se inyecta ahí. No es un error: es la lista
    # blanca (tildá la escena en Escenas permitidas si tiene que sonar).
    # Se avisa una vez por sesión para que no parezca que "no anda".
    try:
        from consola_obs.obs import cliente as mod_obs_cliente
        if not mod_obs_cliente.programa_actual_permitido():
            print("Escena al aire no permitida: la música no se inyecta ahí.")
            try:
                if not getattr(E, "_aviso_musica_protegida", False):
                    E._aviso_musica_protegida = True
                    from tkinter import messagebox as _mb
                    E.ventana.after(0, lambda: _mb.showinfo(
                        "Escena no permitida",
                        "La escena al aire no está tildada en ✅ Escenas "
                        "permitidas, así que la música no se inyecta ahí.\n\n"
                        "Tildala si tiene que sonar (o destildá todo para "
                        "que valga la del aire)."))
            except Exception:
                pass
            return False
    except Exception:
        pass
    # La fuente tiene que estar en la escena al aire para sonar: se
    # asegura ahí (sólo ahí) justo antes de disparar (import lazy).
    try:
        from consola_obs.obs import cliente as mod_obs_cliente
        mod_obs_cliente.asegurar_interna_en_escena_actual(
            C.NOMBRE_FUENTE_MUSICA, "ffmpeg_source", C.AJUSTES_FUENTE_MUSICA)
    except Exception as e:
        print(f"No se pudo asegurar la fuente de música en escena: {e}")
    try:
        mod_rutas_obs.intentar_aprender_base()
    except Exception:
        pass
    try:
        es_absoluta = os.path.isabs(rel)
    except Exception:
        es_absoluta = False
    ruta_abs = rel if es_absoluta else _absoluta(rel)
    try:
        ruta_obs, fijar_archivo = mod_rutas_obs.ruta_para_enviar(
            C.NOMBRE_FUENTE_MUSICA, ruta_abs)
        if fijar_archivo:
            E.cliente_obs.set_input_settings(
                C.NOMBRE_FUENTE_MUSICA,
                {
                    "local_file": ruta_obs,
                    "is_local_file": True,
                    "looping": False,
                    "restart_on_activate": False,
                    "close_when_inactive": False,
                },
                True
            )
            # Cambio hecho por nosotros: no es "OBS cambió por su cuenta".
            _sesion["archivo_obs_visto"] = ruta_obs
        try:
            inicio_ms = max(0.0, float(inicio_ms or 0.0))
        except Exception:
            inicio_ms = 0.0
        if inicio_ms > 0:
            # Arranque sincronizado: nada de RESTART (volvería al 0).
            _arrancar_obs_en_posicion(inicio_ms)
        else:
            E.cliente_obs.trigger_media_input_action(
                C.NOMBRE_FUENTE_MUSICA, _RESTART
            )
            try:
                tok = _sesion.get("token")
                mod_rutas_obs.reintentar_si_no_arranca(
                    C.NOMBRE_FUENTE_MUSICA,
                    lambda: _sesion.get("token") == tok)
            except Exception:
                pass
    except Exception as e:
        print(f"No se pudo reproducir la música {rel}: {e}")
        return False
    # Un tema elegido desde la biblioteca reemplaza lo que hubiera en
    # OBS (incluso un tema ajeno) y manda sobre cualquier espera.
    _sesion["pendiente_obs"] = False
    _sesion["obs_ajeno"] = False
    _sesion["rel"] = rel
    _sesion["archivo"] = ruta_abs
    _sesion["estado"] = "SONANDO"
    _sesion["crudo"] = "OBS_MEDIA_STATE_PLAYING"
    _sesion["inicio_t"] = time.monotonic()
    _anclar_cursor(inicio_ms)
    if reusar_local and mod_motor_local.hay_sesion():
        # El local ya está cargado (en pausa): se alinea con OBS y
        # arranca junto con él, sin decodificar de nuevo.
        mod_motor_local.buscar_ms(inicio_ms)
        mod_motor_local.reanudar()
    else:
        _arrancar_local(ruta_abs, inicio_ms=inicio_ms)
    _sesion["seek_pendiente"] = None
    if not es_absoluta:
        _tocar_reciente(rel)
    asegurar_sondeo()
    return True


def _a_float(valor):
    try:
        return float(valor) if valor is not None else None
    except Exception:
        return None


def _leer_status_obs():
    """(estado_crudo, cursor_ms, duracion_ms) de la fuente Musica, o
    (None, None, None) si OBS no contesta."""
    try:
        resp = E.cliente_obs.get_media_input_status(C.NOMBRE_FUENTE_MUSICA)
        crudo = mod_obs_eventos._valor(resp, "media_state", "mediaState")
        cursor = mod_obs_eventos._valor(resp, "media_cursor", "mediaCursor")
        duracion = mod_obs_eventos._valor(resp, "media_duration", "mediaDuration")
        return crudo, _a_float(cursor), _a_float(duracion)
    except Exception:
        return None, None, None


def _leer_archivo_obs():
    """Archivo (local_file) que tiene cargado la fuente Musica en OBS.
    '' si está vacía o la fuente todavía no existe."""
    try:
        resp = E.cliente_obs.get_input_settings(C.NOMBRE_FUENTE_MUSICA)
        ajustes = mod_obs_eventos._valor(resp, "input_settings", "inputSettings")
        if ajustes is None:
            ajustes = getattr(resp, "input_settings", None)
        if isinstance(ajustes, dict):
            return str(ajustes.get("local_file") or "")
        return str(getattr(ajustes, "local_file", "") or "")
    except Exception:
        return ""


def _normalizar_ruta(texto):
    try:
        import unicodedata
        crudo = unicodedata.normalize("NFC", str(texto or ""))
    except Exception:
        crudo = str(texto or "")
    return crudo.replace("\\", "/").strip().lower()


def _rel_desde_ruta_obs(ruta_obs):
    """Ruta que informa OBS -> rel de la biblioteca local (o None si ese
    tema no está en la biblioteca). OBS puede estar en otra PC, con otra
    carpeta base: se compara el final de la ruta contra Musica/<rel>.
    Si no hay coincidencia exacta con la carpeta, se acepta la
    coincidencia por final de ruta sólo si es única."""
    objetivo = _normalizar_ruta(ruta_obs)
    if not objetivo:
        return None
    try:
        carpeta = _normalizar_ruta(os.path.basename(os.path.normpath(R.CARPETA_MUSICA)))
    except Exception:
        carpeta = ""
    candidatos = []
    try:
        for temas in escanear_biblioteca().values():
            candidatos.extend(temas)
    except Exception:
        return None
    estrictos, laxos = [], []
    for rel in candidatos:
        r = _normalizar_ruta(rel)
        if not r:
            continue
        if carpeta and objetivo.endswith("/" + carpeta + "/" + r):
            estrictos.append((len(r), rel))
        elif objetivo == r or objetivo.endswith("/" + r):
            laxos.append((len(r), rel))
    if estrictos:
        return max(estrictos)[1]
    if len(laxos) == 1:
        return laxos[0][1]
    if laxos:
        # Varios temas con el mismo final: gana el de ruta más larga si
        # es inequívoco.
        laxos.sort(reverse=True)
        if laxos[0][0] > laxos[1][0]:
            return laxos[0][1]
    # OBS en esta misma PC: la ruta existe acá y cae dentro de la
    # carpeta de música.
    try:
        if os.path.isfile(str(ruta_obs)):
            relativa = os.path.relpath(str(ruta_obs), R.CARPETA_MUSICA)
            if not relativa.startswith("..") and not os.path.isabs(relativa):
                destino = _normalizar_ruta(relativa)
                for rel in candidatos:
                    if _normalizar_ruta(rel) == destino:
                        return rel
    except Exception:
        pass
    # Último recurso: mismo nombre de archivo, si es único en la
    # biblioteca (carpeta base distinta en la PC de OBS).
    nombre = objetivo.rsplit("/", 1)[-1]
    iguales = [rel for rel in candidatos
               if _normalizar_ruta(rel).rsplit("/", 1)[-1] == nombre]
    if len(iguales) == 1:
        return iguales[0]
    return None


def _preparar_obs_en_pausa(destino_ms):
    """Deja la fuente Musica ABIERTA, en PAUSA y en destino_ms. Devuelve
    'ok' (posición confirmada), 'sin_seek' (abierta y en pausa pero OBS
    no confirmó la posición) o 'no_abrio' (no llegó a abrir el tema)."""
    nombre = C.NOMBRE_FUENTE_MUSICA
    t0 = time.monotonic()
    reinicio = False
    abierto = False
    while time.monotonic() - t0 < 4.0:
        crudo, _c, _d = _leer_status_obs()
        if crudo == "OBS_MEDIA_STATE_PLAYING":
            # Cambiar el archivo puede arrancarla sola desde el 0: se
            # frena enseguida para buscar la posición en silencio.
            _hacer_accion(_PAUSE)
            abierto = True
            break
        if crudo == "OBS_MEDIA_STATE_PAUSED":
            abierto = True
            break
        detenida = (crudo is None or crudo in C.ESTADOS_MEDIA_DETENIDO
                    or crudo in ("OBS_MEDIA_STATE_NONE", "OBS_MEDIA_STATE_ENDED"))
        if not reinicio and detenida and time.monotonic() - t0 > 0.3:
            _hacer_accion(_RESTART)
            reinicio = True
        time.sleep(0.05)
    if not abierto:
        return "no_abrio"
    time.sleep(0.1)
    for _intento in range(3):
        try:
            E.cliente_obs.set_media_input_cursor(nombre, int(destino_ms))
        except Exception as e:
            _log_sync(f"set_media_input_cursor falló: {e}")
            break
        if _seek_confirmado(destino_ms, 0.15, 2500.0):
            return "ok"
    return "sin_seek"


def _arrancar_obs_en_posicion(destino_ms):
    """Carga ya hecha en OBS (set_input_settings): lo deja en destino_ms
    y lo pone a sonar. Si OBS no confirma la posición igual suena (OBS
    manda; el local se alinea solo con la corrección de deriva)."""
    resultado = _preparar_obs_en_pausa(destino_ms)
    _log_sync(f"arranque sincronizado en {destino_ms:.0f} ms: {resultado}")
    if resultado == "no_abrio":
        _hacer_accion(_RESTART)
    else:
        _hacer_accion(_PLAY)
    return resultado


def antes_de_conectar_obs():
    """Lo llama conectar_obs justo ANTES de marcar la conexión: mientras
    se decide qué hacer con el audio local, el sondeo no toca nada (si
    no, vería la fuente vacía y cortaría el local)."""
    try:
        if _musica_en_parlantes():
            _sesion["sync_hasta"] = time.monotonic() + MAX_SYNC_CONEXION_SEG
    except Exception:
        pass


def al_conectar_obs():
    """Lo llama conectar_obs apenas queda conectado (ver docstring del
    módulo). Corre en un hilo: hace consultas a OBS. Nunca lanza."""
    try:
        # Esta conexión ya está atendida (el sondeo no la repite).
        _sesion["cliente_sync"] = E.cliente_obs
        # El sondeo también sigue los cambios de tema hechos en OBS.
        asegurar_sondeo()
        if not _musica_en_parlantes():
            _sesion["sync_hasta"] = 0.0
            return
        _en_hilo(_sincronizar_al_conectar)
    except Exception:
        _sesion["sync_hasta"] = 0.0


def _sincronizar_al_conectar(seguir=False):
    """Alinea el programa con lo que tiene OBS. Al conectar sólo corre
    con 'Música en PC' activa; con seguir=True (OBS cambió de tema por
    su cuenta) corre siempre, para que el título y la barra muestren lo
    que realmente suena en OBS."""
    try:
        _sesion["pendiente_obs"] = False
        if not E.conectado or (not seguir and not _musica_en_parlantes()):
            return
        archivo_obs = _leer_archivo_obs()
        if archivo_obs:
            _sesion["archivo_obs_visto"] = archivo_obs
        crudo, cursor, duracion = _leer_status_obs()
        _log_sync(f"conexión: OBS archivo={archivo_obs!r} estado={crudo} "
                  f"cursor={cursor} | local estado={_sesion.get('estado')} "
                  f"hay_local={mod_motor_local.hay_sesion()}")
        activo_obs = crudo in ("OBS_MEDIA_STATE_PLAYING", "OBS_MEDIA_STATE_PAUSED",
                               "OBS_MEDIA_STATE_OPENING", "OBS_MEDIA_STATE_BUFFERING")
        if not archivo_obs:
            if activo_obs:
                # OBS está sonando pero no se pudo leer qué tema es: NUNCA
                # se lo trata como vacío (el play del local lo pisaría).
                _log_sync("OBS suena pero no se pudo leer su archivo: "
                          "se deja intacto y el local se saca")
                _sync_obs_ajeno(crudo)
            else:
                _sync_obs_vacio()
            return
        rel = _rel_desde_ruta_obs(archivo_obs)
        if rel is None:
            try:
                total = sum(len(v) for v in escanear_biblioteca().values())
            except Exception:
                total = -1
            _log_sync(f"no se ubicó {archivo_obs!r} en la biblioteca "
                      f"({R.CARPETA_MUSICA!r}, {total} temas)")
            _sync_obs_ajeno(crudo)
            return
        _sync_copiar_obs(rel, crudo, cursor, duracion)
    except Exception as e:
        _log_sync(f"error sincronizando al conectar: {e}")
    finally:
        _sesion["sync_hasta"] = 0.0


def _sync_obs_vacio():
    """OBS sin tema. Si el local estaba sonando (o en pausa) se deja
    EN PAUSA y OBS no se toca: al dar play se carga el tema en OBS en la
    posición del local y arrancan juntos."""
    if (not _sesion.get("archivo")
            or _sesion.get("estado") not in _ESTADOS_ACTIVOS
            or not mod_motor_local.hay_sesion()):
        _log_sync("OBS vacío y sin audio local activo: nada que enganchar")
        return
    mod_motor_local.pausar()
    time.sleep(0.1)
    pos = mod_motor_local.posicion_ms()
    if pos is None:
        pos = float(estado_actual().get("cursor_ms") or 0.0)
    _sesion["estado"] = "PAUSADA"
    _sesion["crudo"] = "OBS_MEDIA_STATE_PAUSED"
    _sesion["seek_pendiente"] = None
    _anclar_cursor(pos)
    _sesion["pendiente_obs"] = True
    _log_sync(f"OBS vacío: local en pausa en {pos:.0f} ms, esperando play")


def _sync_obs_ajeno(crudo):
    """OBS tiene un tema que no está en la biblioteca (sólo pasa si
    alguien lo cambió a mano): el local se saca y a OBS no se le toca
    nada."""
    mod_motor_local.detener()
    _sesion["rel"] = None
    _sesion["archivo"] = None
    _sesion["indice_cola"] = None
    _sesion["obs_ajeno"] = True
    _sesion["crudo"] = crudo
    # Estado que no sea "DETENIDA" mientras OBS suena algo, para que
    # nada lo vacíe creyendo la música ociosa (ver _musica_ociosa).
    if crudo == "OBS_MEDIA_STATE_PAUSED":
        _sesion["estado"] = "PAUSADA"
    elif crudo in (None, "") or crudo in C.ESTADOS_MEDIA_DETENIDO:
        _sesion["estado"] = "DETENIDA"
    else:
        _sesion["estado"] = "SONANDO"
    _anclar_cursor(0.0)
    _sesion["duracion_ms"] = 0.0
    _sesion["seek_pendiente"] = None
    _log_sync("OBS tiene un tema fuera de la biblioteca: local sacado, OBS intacto")


def _sync_copiar_obs(rel, crudo, cursor, duracion):
    """OBS tiene un tema de la biblioteca: el local salta a su posición
    y copia su estado (sonando / pausa / detenido). A OBS no se le
    toca nada."""
    ruta_abs = _absoluta(rel)
    if crudo == "OBS_MEDIA_STATE_PAUSED":
        estado = "PAUSADA"
    elif crudo == "OBS_MEDIA_STATE_PLAYING":
        estado = "SONANDO"
    elif crudo in ("OBS_MEDIA_STATE_OPENING", "OBS_MEDIA_STATE_BUFFERING"):
        estado = "ABRIENDO"
    else:
        estado = "DETENIDA"
    try:
        mismo = (os.path.normcase(os.path.normpath(str(_sesion.get("archivo") or "x")))
                 == os.path.normcase(os.path.normpath(ruta_abs)))
    except Exception:
        mismo = False
    reusar = mismo and mod_motor_local.hay_sesion()
    pos = float(cursor or 0.0)

    # Sesión del programa = lo que realmente tiene OBS.
    if rel not in _cola:
        lista = playlist_actual()
        _cola[:] = lista if rel in lista else [rel]
    _sesion["obs_ajeno"] = False
    _sesion["rel"] = rel
    _sesion["archivo"] = ruta_abs
    _sesion["indice_cola"] = _indice_sano()
    _sesion["token"] += 1
    _sesion["estado"] = estado
    _sesion["crudo"] = crudo
    _sesion["inicio_t"] = time.monotonic() - 10.0  # OBS informa lo real
    _sesion["seek_pendiente"] = None
    if duracion is not None and duracion > 0:
        _sesion["duracion_ms"] = duracion
    _anclar_cursor(pos)
    if estado in _ESTADOS_ACTIVOS:
        pausado = (estado == "PAUSADA")
        if reusar:
            mod_motor_local.buscar_ms(pos)
            if pausado:
                mod_motor_local.pausar()
            else:
                mod_motor_local.reanudar()
        else:
            _arrancar_local(ruta_abs, inicio_ms=pos, pausado=pausado)
    else:
        mod_motor_local.detener()
    _log_sync(f"copiado de OBS: {rel} {estado} en {pos:.0f} ms "
              f"(local {'reusado' if reusar else 'nuevo'})")
    asegurar_sondeo()
    _en_hilo(asegurar_duracion)


def _olvidar_deriva():
    """Descarta la medición de deriva anterior (el estado cambió o no se
    pudo medir): la próxima corrección vuelve a pedir confirmación."""
    try:
        _sesion["deriva_previa"] = None
    except Exception:
        pass


def _sincronizar_local_tick():
    """Un ciclo del bucle de sincronía (cada 250 ms). El audio local es
    ESCLAVO del reloj maestro (la posición de OBS): nunca se corrige
    OBS, sólo el local. Hace tres cosas, en este orden:
      1) Espeja pausa/play de OBS (p. ej. si lo pausaron desde OBS).
      2) Si el local se cayó mientras OBS suena, lo relanza donde va OBS.
      3) Si la diferencia pasa de UMBRAL_DERIVA_MS, el local salta a la
         posición de OBS (enseguida si pasa de UMBRAL_SALTO_MS), pero
         sólo si DOS mediciones seguidas coinciden: una sola puede ser
         un transitorio (una consulta lenta, un pico de CPU) y corregir
         de más se oye como un salto. La posición de OBS se compara con
         el reloj maestro interpolado, que ya tiene en cuenta el tiempo
         que pasó desde la última consulta.
    Nunca lanza."""
    try:
        if not E.conectado or not _musica_en_parlantes():
            return
        if not _sesion.get("archivo") or _sesion.get("obs_ajeno"):
            return
        if _obs_pendiente():
            return
        ahora = time.monotonic()
        if ahora < float(_sesion.get("sync_hasta") or 0.0):
            return
        if ahora - float(_sesion.get("inicio_t") or 0.0) < GRACIA_DERIVA_SEG:
            return
        # Fuera de escena OBS no avanza y el reloj maestro no vale.
        if not _musica_en_escena():
            return
        estado = _sesion.get("estado")
        crudo = _sesion.get("crudo")
        en_ventana = (ahora < float(_sesion.get("seek_proteger_hasta") or 0.0)
                      or (ahora - float(_sesion.get("ultima_accion_t") or 0.0))
                      < ESPERA_TRAS_ACCION_SEG)
        if not mod_motor_local.hay_sesion():
            _olvidar_deriva()
            # 2) Local caído con OBS sonando: se relanza donde va OBS.
            if (estado == "SONANDO" and crudo == "OBS_MEDIA_STATE_PLAYING"
                    and not en_ventana
                    and ahora - float(_sesion.get("ultima_recuperacion_t") or 0.0)
                    >= ESPERA_RECUPERACION_SEG):
                maestro = _reloj_maestro_ms()
                dur = float(_sesion.get("duracion_ms") or 0.0)
                if maestro is not None and (dur <= 0 or maestro < dur - 1500.0):
                    _sesion["ultima_recuperacion_t"] = ahora
                    _log_sync(f"local caído con OBS sonando: se relanza en {maestro:.0f} ms")
                    _arrancar_local(_sesion["archivo"], inicio_ms=maestro)
            return
        # 1) Espejo de pausa/play.
        if not en_ventana:
            if estado == "PAUSADA" and not mod_motor_local.pausado():
                _log_sync("OBS está en pausa: se pausa el local")
                mod_motor_local.pausar()
                _olvidar_deriva()
                # El reloj maestro puede venir atrasado respecto del
                # cambio recién visto: no se compara hasta que OBS
                # vuelva a informar (si no, se "corrige" a un punto
                # viejo y el audio pega un salto).
                _sesion["ultima_correccion_t"] = ahora
                return
            if (estado == "SONANDO" and crudo == "OBS_MEDIA_STATE_PLAYING"
                    and mod_motor_local.pausado()):
                _log_sync("OBS está sonando: se reanuda el local")
                mod_motor_local.reanudar()
                _olvidar_deriva()
                _sesion["ultima_correccion_t"] = ahora
        # 3) Deriva.
        if estado != "SONANDO" or not mod_motor_local.sonando():
            _olvidar_deriva()
            return
        maestro = _reloj_maestro_ms()
        if maestro is None:
            _olvidar_deriva()
            return
        if not mod_motor_local.listo():
            # Todavía decodificando: que arranque ya donde está OBS.
            mod_motor_local.buscar_ms(maestro)
            _olvidar_deriva()
            return
        if mod_motor_local.buscando():
            # Seek local en curso: la posición todavía es transitoria.
            _olvidar_deriva()
            return
        pos = mod_motor_local.posicion_ms()
        if pos is None:
            _olvidar_deriva()
            return
        diferencia = pos - maestro
        absoluta = abs(diferencia)
        if ahora - float(_sesion.get("ultimo_log_deriva_t") or 0.0) >= INTERVALO_LOG_DERIVA_SEG:
            _sesion["ultimo_log_deriva_t"] = ahora
            _log_sync(f"deriva local-OBS {diferencia:+.0f} ms "
                      f"(local {pos:.0f} / OBS {maestro:.0f})")
        if absoluta <= UMBRAL_DERIVA_MS:
            _olvidar_deriva()
            return
        # Confirmación: hacen falta DOS mediciones seguidas del mismo
        # lado, y la anterior tiene que ser reciente (si no, es otra
        # situación y se vuelve a empezar).
        previa = _sesion.get("deriva_previa")
        _sesion["deriva_previa"] = {"d": diferencia, "t": ahora}
        if previa is None:
            return
        if ahora - float(previa.get("t") or 0.0) > 1.0:
            return
        anterior = float(previa.get("d") or 0.0)
        if abs(anterior) <= UMBRAL_DERIVA_MS:
            return
        if (diferencia > 0.0) != (anterior > 0.0):
            return
        espera = ESPERA_SALTO_SEG if absoluta > UMBRAL_SALTO_MS else ESPERA_ENTRE_CORRECCIONES_SEG
        if ahora - float(_sesion.get("ultima_correccion_t") or 0.0) < espera:
            return
        _sesion["ultima_correccion_t"] = ahora
        _olvidar_deriva()
        mod_motor_local.buscar_ms(maestro)
        _log_sync(f"deriva {diferencia:+.0f} ms: local -> {maestro:.0f} ms (OBS)"
                  + (" [salto grande]" if absoluta > UMBRAL_SALTO_MS else ""))
    except Exception:
        pass


def _bucle_sincronia():
    while True:
        try:
            _sincronizar_local_tick()
        except Exception:
            pass
        time.sleep(INTERVALO_SINCRONIA_SEG)


def _seguir_archivo_obs():
    """Si alguien cambia el tema desde OBS (otro archivo en la fuente
    Música), el programa se sincroniza con ese tema: OBS manda. Lee el
    archivo cada INTERVALO_LEER_ARCHIVO_SEG. Nunca lanza."""
    try:
        ahora = time.monotonic()
        if ahora - float(_sesion.get("ultima_lectura_archivo_t") or 0.0) < INTERVALO_LEER_ARCHIVO_SEG:
            return
        _sesion["ultima_lectura_archivo_t"] = ahora
        if _obs_pendiente() or ahora < float(_sesion.get("sync_hasta") or 0.0):
            return
        # Recién cargamos nosotros un tema, o seek en curso: no vale.
        if ahora - float(_sesion.get("inicio_t") or 0.0) < GRACIA_ARCHIVO_SEG:
            return
        if ahora < float(_sesion.get("seek_proteger_hasta") or 0.0):
            return
        archivo_obs = _leer_archivo_obs()
        if not archivo_obs:
            # Vacío o la lectura falló: no se interpreta como cambio.
            return
        visto = _sesion.get("archivo_obs_visto")
        if visto is None:
            _sesion["archivo_obs_visto"] = archivo_obs
            return
        if _normalizar_ruta(archivo_obs) == _normalizar_ruta(visto):
            return
        _sesion["archivo_obs_visto"] = archivo_obs
        rel = _rel_desde_ruta_obs(archivo_obs)
        if (rel is not None and rel == _sesion.get("rel")
                and not _sesion.get("obs_ajeno")):
            return
        _log_sync(f"OBS cambió de tema por su cuenta: {archivo_obs!r}")
        _sincronizar_al_conectar(seguir=True)
    except Exception:
        pass


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
        _marcar_accion()
        _anclar_cursor(0.0)
        _proteger_seek()
        if not _obs_pendiente():
            _hacer_accion(_RESTART)
        mod_motor_local.buscar_ms(0.0)
        return
    base = _indice_sano()
    if base is None:
        base = 0
    _sesion["indice_cola"] = (base - 1) % len(_cola)
    _sesion["token"] += 1
    _hacer_reproducir(_cola[_sesion["indice_cola"]], _sesion["token"])


def pausar():
    # El audio local se corta aunque OBS se haya caído: no queda sonando
    # solo.
    _marcar_accion("OBS_MEDIA_STATE_PAUSED")
    mod_motor_local.pausar()
    if _obs_pendiente():
        # OBS está vacío y el local ya espera el play: nada más que hacer.
        return
    if E.conectado:
        _en_hilo(_hacer_accion, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE")
    elif _sesion.get("archivo") and _sesion.get("estado") == "SONANDO":
        # Sin OBS no hay sondeo que actualice el estado: se congela la
        # barra acá para que el seek y el reloj sigan coherentes.
        cursor = float(estado_actual().get("cursor_ms") or 0.0)
        _sesion["estado"] = "PAUSADA"
        _sesion["crudo"] = "OBS_MEDIA_STATE_PAUSED"
        _anclar_cursor(cursor)


def reanudar():
    """PLAY si estaba pausada, RESTART en cualquier otro caso (quirk:
    después de STOP, PLAY no reanuda)."""
    # Si era una pausa, se espera que OBS pase a PLAYING: en cuanto lo
    # informe la ventana de acción se cierra (si el usuario pausa enseguida
    # en OBS, el local lo sigue al instante). Con RESTART no se espera nada:
    # OBS puede seguir informando el estado viejo mientras aplica.
    _marcar_accion("OBS_MEDIA_STATE_PLAYING"
                   if _sesion.get("crudo") == "OBS_MEDIA_STATE_PAUSED"
                   else None)
    if not E.conectado:
        # Solo parlantes: reanuda el motor local donde quedó.
        if _musica_en_parlantes() and _sesion.get("archivo"):
            if _sesion.get("estado") == "PAUSADA":
                mod_motor_local.reanudar()
                _sesion["estado"] = "SONANDO"
                _sesion["crudo"] = "OBS_MEDIA_STATE_PLAYING"
                _anclar_cursor(float(_sesion.get("cursor_ms") or 0.0))
            else:
                _sesion["token"] += 1
                _en_hilo(_hacer_reproducir, _sesion["rel"], _sesion["token"])
        return
    if _obs_pendiente() and _sesion.get("archivo") and _sesion.get("rel"):
        # OBS estaba vacío: se carga el tema ahí en la posición donde
        # quedó el local y arrancan los dos juntos.
        pos = mod_motor_local.posicion_ms()
        inicio = float(pos if pos is not None else (_sesion.get("cursor_ms") or 0.0))
        _sesion["token"] += 1
        _en_hilo(_hacer_reproducir, _sesion["rel"], _sesion["token"], inicio, True)
        return
    if _sesion.get("crudo") == "OBS_MEDIA_STATE_PAUSED":
        mod_motor_local.reanudar()
        _en_hilo(_hacer_accion, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY")
    elif _sesion.get("archivo"):
        _sesion["token"] += 1
        _en_hilo(_hacer_reproducir, _sesion["rel"], _sesion["token"])


def detener():
    """STOP manual: no avanza solo (el avance solo reacciona a ENDED)."""
    _marcar_accion()
    mod_motor_local.detener()
    if _obs_pendiente():
        # OBS está vacío: no hay nada que frenar allá.
        _sesion["pendiente_obs"] = False
        _sesion["estado"] = "DETENIDA"
        _sesion["crudo"] = "OBS_MEDIA_STATE_STOPPED"
        return
    if not E.conectado:
        if _sesion.get("archivo"):
            _sesion["estado"] = "DETENIDA"
            _sesion["crudo"] = "OBS_MEDIA_STATE_STOPPED"
        return
    _en_hilo(_hacer_detener)


def _hacer_detener():
    mod_motor_local.detener()
    if _hacer_accion("OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"):
        _sesion["estado"] = "DETENIDA"
        _sesion["crudo"] = "OBS_MEDIA_STATE_STOPPED"


def reiniciar():
    _marcar_accion()
    if _obs_pendiente() and _sesion.get("archivo"):
        # OBS vacío: sólo se vuelve al principio en el local (en pausa).
        _anclar_cursor(0.0)
        mod_motor_local.buscar_ms(0.0)
        return
    if E.conectado and _sesion.get("archivo"):
        # El reloj maestro salta a 0 junto con los dos reproductores.
        _anclar_cursor(0.0)
        _proteger_seek()
        mod_motor_local.buscar_ms(0.0)
        mod_motor_local.reanudar()
        _en_hilo(_hacer_accion, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")


def asegurar_duracion():
    """Duración (ms) del tema actual. Si la sesión todavía no la tiene
    (sin OBS el sondeo no corre, y con OBS puede tardar o llegar en 0)
    la saca del caché o decodificando el archivo con miniaudio. Puede
    decodificar: llamarla desde un hilo o con el tema ya cacheado.
    Devuelve 0.0 si no se pudo saber. Nunca lanza."""
    try:
        dur = float(_sesion.get("duracion_ms") or 0.0)
        if dur > 0:
            return dur
        rel = _sesion.get("rel")
        if not rel:
            return 0.0
        ms = duracion_de(rel)
        if ms:
            _sesion["duracion_ms"] = float(ms)
        return float(_sesion.get("duracion_ms") or 0.0)
    except Exception:
        return 0.0


def seek_ms(milisegundos):
    """Salta al momento exacto (clic en la barra, Fase 3). Muestra el
    destino en el acto (update optimista: la UI lo levanta en el
    próximo refresco, esté sonando o en pausa). Con OBS abre además una
    ventana de confirmación de 2 s donde el sondeo solo acepta lo que
    confirme el destino; los ceros/nulos transitorios que OBS manda al
    buscar en pausa se ignoran para que la barra no se borre. Sin OBS
    funciona igual si 'Música en PC' está activa (solo motor local)."""
    if not (E.conectado or _musica_en_parlantes()) or not _sesion.get("archivo"):
        return
    try:
        destino = max(0.0, float(milisegundos))
        dur = asegurar_duracion()
        if dur > 0:
            destino = min(destino, dur)
    except Exception:
        return
    # Un solo destino para los dos reproductores: el reloj maestro salta
    # y el local busca ahí mismo (o se relanza ahí si se había caído).
    _anclar_cursor(destino)
    _marcar_accion()
    _proteger_seek(al_final=(dur > 0 and destino >= dur - 2000.0))
    try:
        estado = _sesion.get("estado")
        if (_musica_en_parlantes() and not mod_motor_local.hay_sesion()
                and estado in _ESTADOS_ACTIVOS):
            _arrancar_local(_sesion["archivo"], inicio_ms=destino,
                            pausado=(estado == "PAUSADA"))
        else:
            mod_motor_local.buscar_ms(destino)
    except Exception:
        mod_motor_local.buscar_ms(destino)
    if _obs_pendiente():
        # OBS vacío: la posición se guarda en el local; OBS la recibe
        # al dar play.
        _sesion["seek_pendiente"] = None
        return
    if E.conectado:
        _sesion["seek_pendiente"] = {"destino": destino, "t": time.monotonic()}
    else:
        _sesion["seek_pendiente"] = None
    _en_hilo(_hacer_seek, destino)


def _leer_cursor_obs():
    """Cursor actual (ms) que informa OBS, o None."""
    try:
        resp = E.cliente_obs.get_media_input_status(C.NOMBRE_FUENTE_MUSICA)
        cursor = mod_obs_eventos._valor(resp, "media_cursor", "mediaCursor")
        return float(cursor) if cursor is not None else None
    except Exception:
        return None


def _seek_confirmado(destino, espera=0.25, tolerancia=1500.0):
    """True si OBS quedó cerca del destino. La tolerancia cubre el viaje
    de ida y vuelta mientras el tema sigue corriendo; sin OBS que
    conteste, False. Si se quedó en el principio (o no se movió), False."""
    time.sleep(espera)
    cursor = _leer_cursor_obs()
    if cursor is None:
        return False
    return abs(cursor - float(destino)) < tolerancia


def _hacer_seek(destino):
    """Seek en OBS (ms) VERIFICADO. El local ya saltó al destino por su
    cuenta (buscar_ms); acá sólo se mueve OBS, se comprueba que quedó
    cerca y se reintenta si no prendió (OBS a veces ignora el primero)."""
    if not E.conectado:
        _anclar_cursor(destino)
        return False
    nombre = C.NOMBRE_FUENTE_MUSICA
    try:
        destino = max(0.0, float(destino))
    except Exception:
        return False
    for intento in range(3):
        try:
            E.cliente_obs.set_media_input_cursor(nombre, int(destino))
        except Exception as e:
            _log_sync(f"seek a OBS falló ({e}): reintento")
            time.sleep(0.12)
            continue
        if _seek_confirmado(destino, 0.15):
            return True
        _log_sync(f"seek a OBS no prendió (intento {intento + 1}, "
                  f"destino {destino:.0f} ms)")
        time.sleep(0.1)
    return False



def _alinear_local_a_obs(cursor):
    """OBS confirmó un seek pero en SU posición real (que no siempre es
    exactamente la pedida). El local ya había saltado al destino por su
    cuenta: si quedó lejos de donde realmente está OBS, se lo alinea
    ahí. OBS manda. Nunca lanza."""
    try:
        if not _musica_en_parlantes() or not mod_motor_local.hay_sesion():
            return
        pos = mod_motor_local.posicion_ms()
        if pos is None:
            return
        cursor = float(cursor)
        if abs(pos - cursor) <= UMBRAL_REALINEO_MS:
            return
        mod_motor_local.buscar_ms(cursor)
        _log_sync(f"seek confirmado por OBS en {cursor:.0f} ms: local alineado "
                  f"(estaba en {pos:.0f} ms)")
    except Exception:
        pass


def _sondear_una_vez():
    """Un ciclo de sondeo (sincrónico, testeable): actualiza
    estado/cursor/duración (el reloj maestro) y auto-avanza SOLO ante
    ENDED natural. La corrección del audio local la hace aparte
    _bucle_sincronia."""
    if not E.conectado:
        return
    # Conexión nueva que no pasó por conectar_obs (reconexión automática,
    # etc.): se sincroniza igual, antes de leer nada del OBS.
    if (_sesion.get("cliente_sync") is not E.cliente_obs
            and E.cliente_obs is not None and _musica_en_parlantes()
            and time.monotonic() >= float(_sesion.get("sync_hasta") or 0.0)):
        _sesion["cliente_sync"] = E.cliente_obs
        _log_sync("conexión nueva detectada por el sondeo")
        _sincronizar_al_conectar()
        return
    # ¿Cambiaron el tema desde OBS? Si es así, nos alineamos con él.
    if _sesion.get("cliente_sync") is E.cliente_obs:
        _seguir_archivo_obs()
    if not _sesion.get("archivo"):
        return
    # Sincronizando la conexión, o OBS vacío con el local esperando el
    # play: lo que informa OBS (fuente vacía) no debe pisar nada ni
    # cortar el local.
    if _obs_pendiente() or time.monotonic() < float(_sesion.get("sync_hasta") or 0.0):
        return
    # Red de contención del fader: si el volumen o el mute cambiaron por
    # un camino que no pasó por nota_volumen_musica, el local se entera
    # igual en el próximo ciclo.
    nota_volumen_musica()
    t_ini = time.monotonic()
    try:
        respuesta = E.cliente_obs.get_media_input_status(C.NOMBRE_FUENTE_MUSICA)
    except Exception:
        # Conexión perdida: no imprimir error, solo salir silenciosamente
        return
    t_fin = time.monotonic()
    # OBS midió el cursor más o menos a mitad del viaje de ida y vuelta.
    t_medio = (t_ini + t_fin) / 2.0
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
    # Fuera de escena: se congela todo (ni cursor, ni estados, ni
    # auto-avance por ENDED). Al volver, el sondeo re-ancla con OBS.
    if not _musica_en_escena():
        return
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
            _anclar_cursor(cursor, t_medio)
            _sesion["seek_pendiente"] = None
            # OBS confirma: el local se alinea con SU posición real (el
            # cursor al que quedó, no el destino que se le pidió).
            _alinear_local_a_obs(cursor)
    else:
        _anclar_cursor(cursor, t_medio)
    if not crudo:
        return
    # Ventana de protección del seek: OBS informa STOPPED/ENDED/NONE
    # transitorios mientras busca. Se ignoran (no cortan el local ni
    # saltan al tema siguiente), salvo que el seek haya sido al final
    # del tema, donde un ENDED es legítimo.
    if (ahora < float(_sesion.get("seek_proteger_hasta") or 0.0)
            and not _sesion.get("seek_al_final")
            and (crudo in C.ESTADOS_MEDIA_DETENIDO
                 or crudo == "OBS_MEDIA_STATE_NONE")):
        return
    _sesion["crudo"] = crudo
    if crudo == _sesion.get("accion_esperada"):
        # OBS ya aplicó la acción del programa (pausa o play): se cierra
        # la ventana de protección para que un toque posterior en OBS se
        # siga al instante (si no, el local seguiría sonando hasta 3 s
        # después y quedaría adelantado respecto de OBS).
        _sesion["accion_esperada"] = None
        _sesion["ultima_accion_t"] = 0.0
    if crudo == "OBS_MEDIA_STATE_PLAYING":
        _sesion["estado"] = "SONANDO"
    elif crudo == "OBS_MEDIA_STATE_PAUSED":
        _sesion["estado"] = "PAUSADA"
    elif crudo in ("OBS_MEDIA_STATE_OPENING", "OBS_MEDIA_STATE_BUFFERING"):
        _sesion["estado"] = "ABRIENDO"
    elif crudo == "OBS_MEDIA_STATE_ENDED":
        _sesion["estado"] = "DETENIDA"
        _detener_local_si_corresponde()
        _avanzar(auto=True)
    elif crudo in C.ESTADOS_MEDIA_DETENIDO:
        _sesion["estado"] = "DETENIDA"
        _detener_local_si_corresponde()


def _detener_local_si_corresponde():
    """OBS informó que la música terminó o se detuvo: el audio local se
    corta también. Los primeros 1,5 s de un tema nuevo se ignoran: OBS
    puede seguir informando el estado terminal del tema anterior hasta
    aplicar el RESTART, y cortaría el audio local recién arrancado."""
    try:
        if (time.monotonic() - float(_sesion.get("inicio_t") or 0.0)) < 1.5:
            return
    except Exception:
        pass
    mod_motor_local.detener()


def _bucle_sondeo():
    while True:
        try:
            _sondear_una_vez()
        except Exception:
            pass
        time.sleep(C.INTERVALO_SONDEO_MUSICA_MS / 1000.0)


def asegurar_sondeo():
    """Arranca el hilo de sondeo una sola vez (idempotente)."""
    if _sondeo["en_marcha"]:
        return
    _sondeo["en_marcha"] = True
    threading.Thread(target=_bucle_sondeo, daemon=True).start()
    threading.Thread(target=_bucle_sincronia, daemon=True).start()


def detener_y_vaciar_musica():
    """STOP + vaciado para el cierre/desconexión (Fase 5): así OBS no
    auto-reproduce al abrirse. También corta el audio local de los
    parlantes, si estaba activo."""
    _marcar_accion()
    # Se marca la sesión vacía ANTES de cortar el local: el bucle de
    # sincronía no debe confundir este corte con una caída del motor y
    # relanzar el tema mientras OBS todavía informa PLAYING.
    _sesion["archivo"] = None
    _sesion["rel"] = None
    _sesion["estado"] = "DETENIDA"
    _sesion["crudo"] = None
    mod_motor_local.detener()
    _sesion["pendiente_obs"] = False
    _sesion["obs_ajeno"] = False
    _sesion["sync_hasta"] = 0.0
    _sesion["archivo_obs_visto"] = ""
    _sesion["indice_cola"] = None
    _anclar_cursor(0.0)
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
