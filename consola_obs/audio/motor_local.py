"""Motor de audio local para la música de fondo (parlantes de la PC).

Solo se usa cuando el sonidista activa "Música en PC" en Ajustes > Audio:
la música sigue saliendo SIEMPRE por el stream de OBS (que es quien
manda), y este motor la reproduce además por la salida de audio de la
PC (parlantes / auriculares) con miniaudio, igual patrón que
_reproducir_local de reproduccion.py (generador + PlaybackDevice).

Diferencias con el audio local de los pads:
- Es UNA sola pista a la vez y dura minutos, así que se puede pausar,
  reanudar y buscar (seek) sin cerrar el dispositivo.
- La ganancia es "viva": la barra de volumen del reproductor la cambia
  en pleno tema (fijar_ganancia), sin reabrir nada.
- El archivo se lee a bytes con Python y se decodifica en memoria
  (stream_memory) porque miniaudio no abre en Windows rutas con
  caracteres raros (｜, emojis, etc.), igual que leer_duracion_local.

Nunca lanza hacia afuera: si falla, avisa una vez y la música sigue
saliendo por OBS como siempre.
"""
import array
import threading
import time

from consola_obs.audio import rampa_ganancia as mod_rampa_ganancia
from consola_obs.audio import motor_mci as mod_motor_mci

SAMPLE_RATE = 44100
NCANALES = 2
FRAMES_POR_DEFECTO = 1024

# Un único candado reentrante para entregar/frenar el dispositivo como
# una operación atómica (mismo motivo que _lock_local en reproduccion).
_lock = threading.RLock()
_sesion = {"dispositivo": None, "est": None}
_generacion = {"n": 0}
_aviso_miniaudio = {"mostrado": False}


def _aplicar_ganancia(trozo, ganancia):
    """Multiplica las muestras por la ganancia (0.0 a 1.0) con
    saturación, devolviendo el trozo (en el lugar). Mismo criterio que
    reproduccion._aplicar_ganancia."""
    if ganancia >= 0.9999:
        return trozo
    formato = getattr(trozo, "typecode", None)
    try:
        if formato == "h":
            if ganancia <= 0.0001:
                for j in range(len(trozo)):
                    trozo[j] = 0
            else:
                for j in range(len(trozo)):
                    valor = int(trozo[j] * ganancia)
                    trozo[j] = 32767 if valor > 32767 else (-32768 if valor < -32768 else valor)
        elif formato in ("f", "d"):
            for j in range(len(trozo)):
                valor = trozo[j] * ganancia
                trozo[j] = 1.0 if valor > 1.0 else (-1.0 if valor < -1.0 else valor)
    except Exception:
        pass
    return trozo


def _silencio(pedido):
    """Trozo de silencio para el pedido (frames) del dispositivo: así la
    pausa mantiene el dispositivo abierto sin consumir el decodificador."""
    try:
        frames = int(pedido) if pedido else FRAMES_POR_DEFECTO
    except Exception:
        frames = FRAMES_POR_DEFECTO
    return array.array("h", bytes(2 * NCANALES * max(1, frames)))


def _abrir_flujo(miniaudio, crudo, inicio_ms):
    """Flujo decodificado en memoria, arrancando en inicio_ms."""
    try:
        frame = max(0, int(float(inicio_ms) / 1000.0 * SAMPLE_RATE))
    except Exception:
        frame = 0
    try:
        return miniaudio.stream_memory(
            crudo, output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=NCANALES, sample_rate=SAMPLE_RATE, seek_frame=frame)
    except TypeError:
        # miniaudio viejo sin seek_frame: arranca desde el principio.
        return miniaudio.stream_memory(
            crudo, output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=NCANALES, sample_rate=SAMPLE_RATE)


def _generador(miniaudio, est, crudo, inicio_ms, terminado):
    """Generador para PlaybackDevice.start. El primer yield vacío es el
    apretón de manos (ver _reproducir_local). Lee de 'est' en cada
    trozo la ganancia, la pausa y el pedido de seek."""
    pedido = yield b""
    flujo = None
    rampa = mod_rampa_ganancia.RampaGanancia()
    try:
        flujo = _abrir_flujo(miniaudio, crudo, inicio_ms)
        try:
            trozo = next(flujo)
        except StopIteration:
            return
        while True:
            if est["cancelar"].is_set():
                break
            destino = est.get("seek_ms")
            if destino is not None:
                est["seek_ms"] = None
                try:
                    flujo.close()
                except Exception:
                    pass
                flujo = _abrir_flujo(miniaudio, crudo, destino)
                try:
                    trozo = next(flujo)
                except StopIteration:
                    break
            if est.get("pausado"):
                try:
                    pedido = yield _silencio(pedido)
                except GeneratorExit:
                    break
                continue
            saliente = rampa.aplicar(trozo, est.get("ganancia", 1.0))
            try:
                pedido = yield saliente
            except GeneratorExit:
                break
            try:
                trozo = flujo.send(pedido) if pedido else next(flujo)
            except StopIteration:
                break
    finally:
        try:
            if flujo is not None:
                flujo.close()
        except Exception:
            pass
        terminado.set()


def _cerrar_dispositivo(dispositivo):
    for accion in ("stop", "close"):
        try:
            getattr(dispositivo, accion)()
        except Exception:
            pass


def _detener_cuerpo():
    """Corta lo que esté sonando (con el candado ya tomado)."""
    est = _sesion.pop("est", None)
    _sesion["est"] = None
    if est is not None:
        try:
            est["cancelar"].set()
        except Exception:
            pass
    dispositivo = _sesion.pop("dispositivo", None)
    _sesion["dispositivo"] = None
    if dispositivo is not None:
        _cerrar_dispositivo(dispositivo)


def _avisar_sin_miniaudio(error):
    if _aviso_miniaudio["mostrado"]:
        return
    _aviso_miniaudio["mostrado"] = True
    print(f"miniaudio no disponible ({error}): la música sólo saldrá por OBS.")
    try:
        # Aviso visible (en el .exe no hay consola donde ver el print).
        from tkinter import messagebox
        from consola_obs import estado as E
        E.ventana.after(0, lambda: messagebox.showwarning(
            "Sin audio local",
            f"No se pudo cargar el motor de audio local ({error}).\n\n"
            "La música sólo saldrá por OBS."))
    except Exception:
        pass


def reproducir(ruta_abs, token, ganancia_lineal=1.0, inicio_ms=0.0, pausado=False):
    """Reproduce el archivo por los parlantes de la PC (frena lo que
    hubiera). No bloquea: el hilo de reproducción se lanza acá.
    'token' es el de la sesión de música (sólo informativo, para
    detener(token) selectivo)."""
    est = {
        "cancelar": threading.Event(), "ganancia": float(ganancia_lineal),
        "pausado": bool(pausado), "seek_ms": None, "token": token,
    }
    with _lock:
        _generacion["n"] += 1
        mi_generacion = _generacion["n"]
        _detener_cuerpo()
        _sesion["est"] = est
    threading.Thread(
        target=_correr, args=(ruta_abs, est, mi_generacion, inicio_ms), daemon=True
    ).start()


def _log(texto):
    try:
        from consola_obs import red as mod_red
        mod_red.log_conexion("AUDIO", texto)
    except Exception:
        pass


def _correr_mci(ruta_abs, est, mi_generacion, inicio_ms):
    """Música por los parlantes con el reproductor de Windows (MCI):
    volumen en vivo, pausa y búsqueda. Todo desde este mismo hilo."""
    rep = mod_motor_mci.Reproductor()
    with _lock:
        if _generacion["n"] != mi_generacion or est["cancelar"].is_set():
            return
        if not rep.abrir(ruta_abs):
            _log(f"MCI no pudo abrir la música {ruta_abs}: {rep.error}")
            _soltar(est, None)
            return
    try:
        rep.volumen(est.get("ganancia", 1.0))
        rep.reproducir(inicio_ms)
        pausado = bool(est.get("pausado"))
        if pausado:
            rep.pausar()
        t0 = time.time()
        while not est["cancelar"].is_set():
            destino = est.get("seek_ms")
            if destino is not None:
                est["seek_ms"] = None
                rep.buscar(destino, seguir_sonando=True)
                if est.get("pausado"):
                    rep.pausar()
                t0 = time.time()
            quiere_pausa = bool(est.get("pausado"))
            if quiere_pausa != pausado:
                pausado = quiere_pausa
                rep.pausar() if pausado else rep.reanudar()
            rep.volumen(est.get("ganancia", 1.0))
            if (not pausado and time.time() - t0 > 0.5
                    and rep.modo() in ("stopped", "not ready", "")):
                break
            time.sleep(0.025)
    except Exception as e:
        _log(f"error en la música por MCI: {e}")
    finally:
        rep.cerrar()
        _soltar(est, None)


def _correr(ruta_abs, est, mi_generacion, inicio_ms):
    try:
        import miniaudio
    except Exception as e:
        _log(f"miniaudio no disponible para la música: {e}")
        if mod_motor_mci.disponible():
            _correr_mci(ruta_abs, est, mi_generacion, inicio_ms)
        else:
            _avisar_sin_miniaudio(e)
            _soltar(est, None)
        return
    try:
        with open(ruta_abs, "rb") as f:
            crudo = f.read()
        if not crudo:
            raise ValueError("archivo vacío")
    except Exception as e:
        print(f"No se pudo leer la música para los parlantes {ruta_abs}: {e}")
        _soltar(est, None)
        return
    terminado = threading.Event()
    with _lock:
        # Si mientras se leía el archivo llegó otro reproducir() o un
        # detener(), esta sesión murió: no se arranca nada (sin sonidos
        # huérfanos).
        if _generacion["n"] != mi_generacion or est["cancelar"].is_set():
            return
        try:
            dispositivo = miniaudio.PlaybackDevice()
        except Exception as e:
            _log(f"miniaudio no pudo abrir la salida de audio: {e}")
            dispositivo = None
    if dispositivo is None:
        if mod_motor_mci.disponible():
            _correr_mci(ruta_abs, est, mi_generacion, inicio_ms)
        else:
            _soltar(est, None)
        return
    with _lock:
        generador = _generador(miniaudio, est, crudo, inicio_ms, terminado)
        try:
            next(generador)
            dispositivo.start(generador)
        except Exception as e:
            print(f"Error reproduciendo la música en la PC: {e}")
            _cerrar_dispositivo(dispositivo)
            _soltar(est, None)
            return
        _sesion["dispositivo"] = dispositivo
    try:
        while not terminado.wait(timeout=0.1):
            if est["cancelar"].is_set():
                break
    except Exception as e:
        print(f"Error reproduciendo la música en la PC: {e}")
    finally:
        _soltar(est, dispositivo)


def _soltar(est, dispositivo):
    """Fin de ESTA sesión (natural, cancelada o con error): limpia el
    registro sólo si todavía es la vigente."""
    with _lock:
        if _sesion.get("est") is est:
            _sesion["est"] = None
            if _sesion.get("dispositivo") is dispositivo:
                _sesion["dispositivo"] = None
        elif _sesion.get("dispositivo") is dispositivo:
            _sesion["dispositivo"] = None
    if dispositivo is not None:
        _cerrar_dispositivo(dispositivo)


def detener(token=None):
    """Corta la música local. Con token sólo si sigue siendo esa sesión."""
    with _lock:
        est = _sesion.get("est")
        if token is not None and (est is None or est.get("token") != token):
            return False
        _generacion["n"] += 1
        _detener_cuerpo()
        return est is not None


def pausar():
    est = _sesion.get("est")
    if est is not None:
        est["pausado"] = True


def reanudar():
    est = _sesion.get("est")
    if est is not None:
        est["pausado"] = False


def buscar_ms(milisegundos):
    """Salta al momento indicado (el generador lo aplica en el próximo
    trozo)."""
    est = _sesion.get("est")
    if est is None:
        return
    try:
        est["seek_ms"] = max(0.0, float(milisegundos))
    except Exception:
        pass


def fijar_ganancia(ganancia_lineal):
    """Cambia el volumen en vivo (0.0 a 1.0)."""
    est = _sesion.get("est")
    if est is None:
        return
    try:
        est["ganancia"] = max(0.0, float(ganancia_lineal))
    except Exception:
        pass


def hay_sesion():
    """True si hay una pista cargada en el motor (sonando o en pausa)."""
    return _sesion.get("est") is not None


def sonando():
    """True si hay una pista cargada y no está en pausa."""
    est = _sesion.get("est")
    return est is not None and not est.get("pausado")
