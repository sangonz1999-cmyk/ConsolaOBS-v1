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
  porque miniaudio no abre en Windows rutas con caracteres raros
  (｜, emojis, etc.), igual que leer_duracion_local.
- Arranque rápido: lo PRIMERO que se hace es averiguar la duración sin
  decodificar (mp3/flac/wav/ogg get_info). Antes se decodificaba el
  tema entero para recién ahí descubrir que era larguísimo: un tema de
  2 horas demoraba ~14 s en arrancar (y OBS ya iba 4 s adelante).
- Tema corto (hasta LIMITE_DECODIFICADO_SEG): se decodifica UNA vez a
  PCM en RAM y el seek es sólo cambiar un índice (instantáneo).
- Tema largo: NO se decodifica entero. Se arma un índice de frames MP3
  (tiempo -> byte, una marca cada MARCA_INDICE_MS; ~0.3 s para 125 MB)
  y se decodifica "en ventana" con miniaudio.stream_any sobre un trozo
  de los bytes que empieza en un frame real. Buscar es abrir otra
  ventana: 0.1-6 ms, sin recorrer el tema.
- Compensación de arranque: si el tema ya venía sonando (OBS manda) y
  tardamos en preparar el motor, se entra en la posición que el tema
  tiene AHORA, no en la que tenía cuando se pidió.
- Informa su posición (posicion_ms) para que musica.py lo mantenga
  sincronizado con OBS (que siempre manda). Mientras aplica un seek
  avisa buscando() para que no lo comparen con la posición vieja.

Nunca lanza hacia afuera: si falla, avisa una vez y la música sigue
saliendo por OBS como siempre.
"""
import array
import bisect
import struct
import threading
import time

from consola_obs.audio import rampa_ganancia as mod_rampa_ganancia
from consola_obs.audio import motor_mci as mod_motor_mci

SAMPLE_RATE = 44100
NCANALES = 2
FRAMES_POR_DEFECTO = 1024

# Tope de lo que se decodifica entero a RAM: 6 min de PCM 16 bit estéreo
# a 44,1 kHz = 6*60*44100*2*2 bytes = unos 64 MB (0.7 s de CPU). Más
# largo -> streaming con índice de frames (seek instantáneo igual).
LIMITE_DECODIFICADO_SEG = 6 * 60
LIMITE_DECODIFICADO_FRAMES = LIMITE_DECODIFICADO_SEG * SAMPLE_RATE
FRAMES_POR_TROZO_DECODIFICACION = 65536
# Cada cuánto se guarda una marca (offset de byte) del índice MP3. Más
# fino = seek más exacto, pero más RAM y más tiempo de índice: 500 ms
# son ~15.000 marcas en un tema de 2 horas y el resto se descarta al
# abrir la ventana (medio segundo de decodificación, imperceptible).
MARCA_INDICE_MS = 500.0
# Buffer de salida del dispositivo. Chico = menor retraso entre lo que se
# entrega y lo que se oye (y la posición que se informa queda más cerca
# de la real). 100 ms x 2 períodos se decodifica de sobra en cada callback.
BUFFER_SALIDA_MS = 100
PERIODOS_SALIDA = 2
# Estimación de lo que tarda en sonar lo ya entregado al dispositivo
# (su buffer de salida): la posición "audible" va esto por detrás de lo
# entregado. Sólo sirve para comparar contra OBS sin falsas correcciones.
LATENCIA_SALIDA_MS = float(BUFFER_SALIDA_MS * PERIODOS_SALIDA)

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


def _frames_desde_ms(milisegundos):
    try:
        return max(0, int(float(milisegundos) / 1000.0 * SAMPLE_RATE))
    except Exception:
        return 0


def _parece_mp3(crudo):
    """True si los bytes arrancan como un MP3 (ID3 o sincronismo de
    frame). Sólo sirve para decidir si vale la pena armar el índice."""
    if not crudo:
        return False
    if crudo[:3] == b"ID3":
        return True
    return len(crudo) >= 2 and crudo[0] == 0xFF and (crudo[1] & 0xE0) == 0xE0


def _probar_info(miniaudio, crudo):
    """Duración/formato SIN decodificar (mp3, flac, wav u ogg), o None si
    no se puede. Así se decide RAM vs streaming en el acto: antes se
    decodificaba el tema entero para recién ahí descubrir que era
    larguísimo (14 s en un tema de 2 horas)."""
    if not crudo:
        return None
    cab = crudo[:4]
    if _parece_mp3(crudo):
        nombres = ("mp3_get_info",)
    elif cab == b"fLaC":
        nombres = ("flac_get_info",)
    elif cab == b"RIFF":
        nombres = ("wav_get_info",)
    elif cab == b"OggS":
        nombres = ("vorbis_get_info",)
    else:
        nombres = ("mp3_get_info", "flac_get_info", "wav_get_info", "vorbis_get_info")
    for nombre in nombres:
        funcion = getattr(miniaudio, nombre, None)
        if funcion is None:
            continue
        try:
            info = funcion(crudo)
        except Exception:
            continue
        try:
            if float(getattr(info, "duration", 0.0) or 0.0) > 0.0:
                return info
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------
# Índice de frames MP3: tiempo -> byte (para abrir una "ventana" del
# archivo en el frame que corresponde y decodificar sólo desde ahí).
# ---------------------------------------------------------------------
_V1L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_V2L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_RATES = {
    3: (44100, 48000, 32000, 0),
    2: (22050, 24000, 16000, 0),
    0: (11025, 12000, 8000, 0),
}


def _cabecera_mp3(datos, pos):
    """(bytes del frame, sample rate, muestras por frame) del frame MP3
    que empieza en 'pos', o None si ahí no hay una cabecera válida."""
    if pos + 4 > len(datos):
        return None
    h = struct.unpack_from(">I", datos, pos)[0]
    if (h & 0xFFE00000) != 0xFFE00000:
        return None
    version = (h >> 19) & 3
    capa = (h >> 17) & 3
    idx_bitrate = (h >> 12) & 0xF
    idx_rate = (h >> 10) & 3
    relleno = (h >> 9) & 1
    # versión 1 = reservada; layer 1 = Layer III; bitrate 0/15 y rate 3
    # no existen. Todo lo demás (incluidos los "free format") se ignora.
    if version == 1 or capa != 1 or idx_bitrate in (0, 15) or idx_rate == 3:
        return None
    bitrate = (_V1L3 if version == 3 else _V2L3)[idx_bitrate] * 1000
    rate = _RATES[version][idx_rate]
    if bitrate <= 0 or rate <= 0:
        return None
    tam = (144 if version == 3 else 72) * bitrate // rate + relleno
    return tam, rate, (1152 if version == 3 else 576)


class _IndiceMp3:
    """Marcas (byte, frame de salida) cada MARCA_INDICE_MS para poder
    decodificar el tema desde la mitad sin recorrerlo. Nunca lanza: si
    el archivo no es un MP3 coherente queda 'ok' en False y el motor
    usa el camino lento (decodificar y descartar)."""

    def __init__(self, datos):
        self.ok = False
        self.offsets = []
        self.marcas = []
        self.total_frames = 0
        try:
            self._escanear(datos)
        except Exception:
            self.ok = False

    def _escanear(self, datos):
        n = len(datos)
        pos = 0
        if datos[:3] == b"ID3" and n >= 10:
            tam = (((datos[6] & 0x7F) << 21) | ((datos[7] & 0x7F) << 14)
                   | ((datos[8] & 0x7F) << 7) | (datos[9] & 0x7F))
            pos = min(n, 10 + tam)
        offsets, marcas = self.offsets, self.marcas
        t_ms = 0.0
        ultima = -MARCA_INDICE_MS
        basura = 0
        while pos + 4 <= n:
            cab = _cabecera_mp3(datos, pos)
            if cab is None:
                basura += 1
                if not offsets and basura > 65536:
                    return
                pos += 1
                continue
            tam, rate, muestras = cab
            if not marcas or t_ms - ultima >= MARCA_INDICE_MS:
                offsets.append(pos)
                marcas.append(int(t_ms * SAMPLE_RATE / 1000.0))
                ultima = t_ms
            t_ms += muestras * 1000.0 / rate
            pos += tam
        self.total_frames = int(t_ms * SAMPLE_RATE / 1000.0)
        self.ok = len(offsets) >= 3 and self.total_frames > SAMPLE_RATE

    def buscar(self, frame):
        """(byte del frame más cercano hacia atrás, su frame de salida)."""
        if not self.ok:
            return 0, 0
        try:
            frame = max(0, int(frame))
        except Exception:
            frame = 0
        i = bisect.bisect_right(self.marcas, frame) - 1
        if i < 0:
            i = 0
        return self.offsets[i], self.marcas[i]


class _FuenteVentana:
    """Fuente para miniaudio.stream_any sobre un trozo de los bytes: su
    posición 0 es 'base' (el byte de un frame MP3 real), así el
    decodificador abre en la mitad del tema sin recorrerlo. Duck-typed
    contra StreamableSource (read/seek/close/ffi_handle)."""

    error_in_readcallback = None
    ffi_handle = None

    def __init__(self, datos, base):
        self.datos = datos
        self.base = max(0, int(base))
        self.pos = 0

    def read(self, num_bytes):
        ini = self.base + self.pos
        fin = min(len(self.datos), ini + max(0, int(num_bytes)))
        if fin <= ini:
            return b""
        trozo = self.datos[ini:fin]
        self.pos += len(trozo)
        return trozo

    def seek(self, offset, origin):
        try:
            nombre = getattr(origin, "name", None)
            if nombre is None:
                valor = getattr(origin, "value", origin)
                nombre = {0: "START", 1: "CURRENT", 2: "END"}.get(valor, "START")
            if nombre == "CURRENT":
                destino = self.pos + int(offset)
            elif nombre == "END":
                destino = (len(self.datos) - self.base) + int(offset)
            else:
                destino = int(offset)
        except Exception:
            return False
        self.pos = max(0, destino)
        return True

    def close(self):
        pass


class _LectorRam:
    """Tema decodificado entero en RAM: leer y buscar son índices."""

    def __init__(self, muestras):
        self.muestras = muestras
        self.total = len(muestras) // NCANALES
        self.pos = 0

    def abrir(self, frame):
        self.pos = max(0, min(self.total, int(frame)))
        return self.pos

    def leer(self, frames):
        if self.pos >= self.total:
            return array.array("h")
        try:
            frames = max(1, int(frames))
        except Exception:
            frames = FRAMES_POR_DEFECTO
        fin = min(self.total, self.pos + frames)
        trozo = self.muestras[self.pos * NCANALES:fin * NCANALES]
        self.pos = fin
        return trozo

    def cerrar(self):
        pass


class _LectorStream:
    """Tema largo: decodifica sólo desde la ventana abierta. Con índice
    MP3, buscar es abrir otra ventana en un frame real (milisegundos);
    sin índice (formato raro) cae al camino lento de decodificar y
    descartar desde el principio."""

    def __init__(self, miniaudio, datos, indice=None):
        self.miniaudio = miniaudio
        self.datos = datos
        self.indice = indice if (indice is not None and indice.ok) else None
        self.flujo = None
        self.fuente = None
        self.pos = 0
        self.sobrante = array.array("h")
        self.total = self.indice.total_frames if self.indice is not None else 0

    # -- interno ------------------------------------------------------
    def _cerrar_flujo(self):
        if self.flujo is not None:
            try:
                self.flujo.close()
            except Exception:
                pass
            self.flujo = None
        self.fuente = None
        self.sobrante = array.array("h")

    def _siguiente(self):
        if self.flujo is None:
            return None
        try:
            trozo = next(self.flujo)
        except StopIteration:
            return None
        except Exception:
            return None
        if getattr(trozo, "typecode", None) != "h" or len(trozo) == 0:
            return None
        resto = len(trozo) % NCANALES
        if resto:
            trozo = trozo[:len(trozo) - resto]
        return trozo

    # -- interfaz del lector -----------------------------------------
    def abrir(self, frame):
        """Abre la decodificación en 'frame'. Devuelve el frame real en
        el que quedó (puede diferir unas décimas por el redondeo de la
        marca y por el propio decodificador)."""
        try:
            frame = max(0, int(frame))
        except Exception:
            frame = 0
        self._cerrar_flujo()
        if self.indice is not None:
            offset, marca = self.indice.buscar(frame)
            self.fuente = _FuenteVentana(self.datos, offset)
            self.flujo = self.miniaudio.stream_any(
                self.fuente, self.miniaudio.FileFormat.MP3,
                output_format=self.miniaudio.SampleFormat.SIGNED16,
                nchannels=NCANALES, sample_rate=SAMPLE_RATE,
                frames_to_read=FRAMES_POR_DEFECTO)
            self.pos = marca
            pendiente = frame - marca
        else:
            self.flujo = self.miniaudio.stream_memory(
                self.datos, output_format=self.miniaudio.SampleFormat.SIGNED16,
                nchannels=NCANALES, sample_rate=SAMPLE_RATE)
            self.pos = 0
            pendiente = frame
        # Lo que falte para el destino exacto se descarta (con índice es
        # medio segundo como mucho; sin índice, todo lo anterior).
        while pendiente > 0:
            trozo = self._siguiente()
            if trozo is None:
                break
            n = len(trozo) // NCANALES
            if n <= pendiente:
                pendiente -= n
                self.pos += n
            else:
                self.sobrante = trozo[pendiente * NCANALES:]
                self.pos += pendiente
                pendiente = 0
        return self.pos

    def leer(self, frames):
        try:
            frames = max(1, int(frames))
        except Exception:
            frames = FRAMES_POR_DEFECTO
        queridas = frames * NCANALES
        salida = self.sobrante
        self.sobrante = array.array("h")
        while len(salida) < queridas:
            trozo = self._siguiente()
            if trozo is None:
                break
            salida.extend(trozo)
        if len(salida) > queridas:
            self.sobrante = salida[queridas:]
            del salida[queridas:]
        return salida

    def cerrar(self):
        self._cerrar_flujo()


def _decodificar_en_memoria(miniaudio, crudo, est):
    """Decodifica el tema ENTERO a PCM 16 bit estéreo en RAM. Devuelve un
    array('h') o None: el tema pasa del límite, la sesión se canceló
    mientras decodificaba, o algo falló. Se decodifica por trozos para
    poder abortar apenas se pasa del límite (sin llegar a ocupar la RAM)
    o se cancela."""
    flujo = None
    try:
        try:
            flujo = miniaudio.stream_memory(
                crudo, output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=NCANALES, sample_rate=SAMPLE_RATE,
                frames_to_read=FRAMES_POR_TROZO_DECODIFICACION)
        except TypeError:
            flujo = miniaudio.stream_memory(
                crudo, output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=NCANALES, sample_rate=SAMPLE_RATE)
        muestras = array.array("h")
        limite_muestras = LIMITE_DECODIFICADO_FRAMES * NCANALES
        while True:
            if est["cancelar"].is_set():
                return None
            try:
                trozo = next(flujo)
            except StopIteration:
                break
            if getattr(trozo, "typecode", None) != "h":
                return None
            muestras.extend(trozo)
            if len(muestras) > limite_muestras:
                _log(f"tema de más de {LIMITE_DECODIFICADO_SEG // 60} min: "
                     "se reproduce por streaming (sin decodificar a RAM)")
                return None
        return muestras if len(muestras) > 0 else None
    except Exception as e:
        _log(f"no se pudo decodificar a memoria ({e}): se usa streaming")
        return None
    finally:
        try:
            if flujo is not None:
                flujo.close()
        except Exception:
            pass


def _generador(est, lector, pos_inicial, terminado):
    """Generador para PlaybackDevice.start. El primer yield vacío es el
    apretón de manos (ver _correr). Lee de 'est' en cada trozo la
    ganancia, la pausa y el pedido de seek; el seek lo aplica el lector
    (RAM: cambiar un índice; streaming: abrir otra ventana)."""
    pedido = yield b""
    rampa = mod_rampa_ganancia.RampaGanancia()
    pos = int(pos_inicial)
    try:
        est["pos_frames"] = pos
        est["listo"] = True
        while True:
            if est["cancelar"].is_set():
                break
            destino = est.get("seek_ms")
            if destino is not None:
                est["seek_ms"] = None
                try:
                    pos = lector.abrir(_frames_desde_ms(destino))
                except Exception as e:
                    _log(f"seek local falló ({e}): se vuelve al principio")
                    try:
                        pos = lector.abrir(0)
                    except Exception:
                        est["buscando"] = False
                        break
                est["pos_frames"] = pos
                est["buscando"] = False
            if est.get("pausado"):
                try:
                    pedido = yield _silencio(pedido)
                except GeneratorExit:
                    break
                continue
            try:
                frames = int(pedido) if pedido else FRAMES_POR_DEFECTO
            except Exception:
                frames = FRAMES_POR_DEFECTO
            trozo = lector.leer(frames)
            if len(trozo) == 0:
                break
            pos += len(trozo) // NCANALES
            est["pos_frames"] = pos
            saliente = rampa.aplicar(trozo, est.get("ganancia", 1.0))
            try:
                pedido = yield saliente
            except GeneratorExit:
                break
    finally:
        est["buscando"] = False
        try:
            lector.cerrar()
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
        # Posición (frames ya entregados al dispositivo) y si el motor ya
        # está sonando/listo (terminó de decodificar y arrancó).
        "pos_frames": _frames_desde_ms(inicio_ms), "listo": False,
        "buscando": False,
        # Instante en que se pidió el arranque: si el tema ya venía
        # sonando (OBS manda), al terminar de preparar el motor se entra
        # en la posición que tiene AHORA, no en la que tenía al pedirlo.
        "pedido_t": time.monotonic(),
    }
    _log(f"reproducir inicio={float(inicio_ms or 0):.0f} ms pausado={bool(pausado)} "
         f"desde: {_quien_llama()}")
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


def _quien_llama():
    """Cadena corta de funciones que llegaron hasta acá (diagnóstico):
    sirve para saber QUIÉN pidió un reproducir/buscar/detener."""
    try:
        import traceback
        pila = traceback.extract_stack(limit=7)[:-2]
        return " <- ".join(f.name for f in reversed(pila[-4:]))
    except Exception:
        return "?"


def _avisar_usando_mci(error):
    """Una sola vez: la música local va por el reproductor de Windows
    (MCI), cuya búsqueda (seek) no es confiable con mp3. Con miniaudio el
    seek es exacto."""
    if _aviso_miniaudio.get("mci_mostrado"):
        return
    _aviso_miniaudio["mci_mostrado"] = True
    _log(f"MOTOR = MCI (miniaudio no se pudo cargar: {error})")
    try:
        from tkinter import messagebox
        from consola_obs import estado as E
        E.ventana.after(0, lambda: messagebox.showwarning(
            "Audio local con reproductor de Windows",
            "La música de los parlantes está usando el reproductor de "
            "Windows (MCI), porque no se pudo cargar 'miniaudio'.\n\n"
            "Con ese reproductor, adelantar o retroceder en la barra puede "
            "fallar y dejar el audio local desincronizado de OBS.\n\n"
            "Solución: abrí una consola y ejecutá\n"
            "    pip install --upgrade miniaudio\n"
            "y reiniciá el programa.\n\n"
            f"(Detalle: {error})"))
    except Exception:
        pass


def _buscar_mci(rep, destino, pausado, est=None):
    """Seek por MCI VERIFICADO: salta, espera un instante y comprueba
    en la posición real que quedó cerca del destino. Si no, reintenta
    y, como último recurso, reabre el tema en esa posición. Así el
    audio local no se queda atrás (ni vuelve al principio) cuando OBS
    sí saltó. Devuelve True si quedó en el destino."""
    destino = float(destino)
    if est is not None:
        est["buscando"] = True
    try:
        for _intento in range(3):
            if not rep.buscar(destino, seguir_sonando=True):
                time.sleep(0.05)
                continue
            if pausado:
                rep.pausar()
            time.sleep(0.12)
            pos = rep.posicion()
            if pos is None or abs(pos - destino) < 1500.0:
                _log(f"seek MCI aplicado: destino {destino:.0f} ms, MCI informa "
                     f"{'?' if pos is None else format(pos, '.0f')} ms")
                return True
            _log(f"seek MCI no prendió (pos={pos:.0f}, destino={destino:.0f}): "
                 "reintento")
        _log(f"seek MCI falló 3 veces: se reabre el tema en {destino:.0f} ms")
        ok = rep.reabrir_en(destino)
        if ok and pausado:
            rep.pausar()
        return ok
    finally:
        if est is not None:
            est["buscando"] = False


def _correr_mci(ruta_abs, est, mi_generacion, inicio_ms):
    """Música por los parlantes con el reproductor de Windows (MCI):
    volumen en vivo, pausa y búsqueda. Todo desde este mismo hilo.
    La posición que se informa es la REAL de MCI (si no la da, se
    estima con el reloj)."""
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
        # Estimación de respaldo: base + tiempo corrido sonando.
        try:
            base_ms = float(inicio_ms)
        except Exception:
            base_ms = 0.0
        t_ref = time.time()
        est["listo"] = True
        while not est["cancelar"].is_set():
            destino = est.get("seek_ms")
            if destino is not None:
                est["seek_ms"] = None
                pausado = bool(est.get("pausado"))
                _buscar_mci(rep, destino, pausado, est)
                t0 = time.time()
                base_ms = float(destino)
                t_ref = time.time()
            quiere_pausa = bool(est.get("pausado"))
            if quiere_pausa != pausado:
                pausado = quiere_pausa
                rep.pausar() if pausado else rep.reanudar()
                if pausado:
                    base_ms += (time.time() - t_ref) * 1000.0
                else:
                    t_ref = time.time()
            real = rep.posicion()
            if real is not None:
                actual_ms = real
                base_ms = real
                t_ref = time.time()
            else:
                actual_ms = base_ms if pausado else base_ms + (time.time() - t_ref) * 1000.0
            est["pos_frames"] = _frames_desde_ms(actual_ms)
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
            _avisar_usando_mci(e)
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
    # 1) Duración SIN decodificar: decide RAM vs streaming en el acto.
    info = _probar_info(miniaudio, crudo)
    duracion_s = 0.0
    try:
        duracion_s = float(getattr(info, "duration", 0.0) or 0.0)
    except Exception:
        duracion_s = 0.0
    lector = None
    muestras = None
    if duracion_s <= 0 or duracion_s <= LIMITE_DECODIFICADO_SEG:
        # Corto (o duración desconocida: se prueba a RAM con tope).
        muestras = _decodificar_en_memoria(miniaudio, crudo, est)
        if est["cancelar"].is_set():
            _soltar(est, None)
            return
    if muestras is not None:
        crudo = None  # ya no hace falta el archivo comprimido
        duracion_s = len(muestras) // NCANALES / SAMPLE_RATE
        lector = _LectorRam(muestras)
        descripcion = f"tema en RAM, {duracion_s:.0f} s"
    else:
        indice = _IndiceMp3(crudo) if _parece_mp3(crudo) else None
        lector = _LectorStream(miniaudio, crudo, indice)
        if indice is not None and indice.ok:
            descripcion = (f"streaming con índice MP3, {len(indice.offsets)} marcas, "
                           f"{duracion_s:.0f} s")
        else:
            descripcion = "streaming sin índice (seek lento)"
    terminado = threading.Event()
    # 2) Compensación de arranque: si el tema ya venía sonando, se entra
    # donde está AHORA (preparar el motor tardó unos ms/segundos).
    inicio = float(inicio_ms or 0.0)
    if not est.get("pausado"):
        try:
            pedido_t = float(est.get("pedido_t") or 0.0)
            if pedido_t > 0.0:
                inicio += max(0.0, (time.monotonic() - pedido_t) * 1000.0)
        except Exception:
            pass
    if duracion_s > 0:
        inicio = min(inicio, max(0.0, duracion_s * 1000.0 - 1000.0))
    # Un seek que llegó mientras se preparaba el motor: se arranca ahí.
    previo = est.get("seek_ms")
    if previo is not None:
        est["seek_ms"] = None
        est["buscando"] = False
        inicio = max(0.0, float(previo))
    with _lock:
        # Si mientras se leía/decodificaba el archivo llegó otro
        # reproducir() o un detener(), esta sesión murió: no se arranca
        # nada (sin sonidos huérfanos).
        if _generacion["n"] != mi_generacion or est["cancelar"].is_set():
            return
        try:
            try:
                dispositivo = miniaudio.PlaybackDevice(
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=NCANALES, sample_rate=SAMPLE_RATE,
                    buffersize_msec=BUFFER_SALIDA_MS,
                    callback_periods=PERIODOS_SALIDA)
            except TypeError:
                # miniaudio viejo sin esos parámetros: se usa el default.
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
        # Abrir la decodificación acá (y no en el callback de audio) y
        # recién después arrancar el dispositivo.
        try:
            pos_inicial = lector.abrir(_frames_desde_ms(inicio))
        except Exception as e:
            _log(f"no se pudo abrir el audio en {inicio:.0f} ms ({e})")
            _cerrar_dispositivo(dispositivo)
            _soltar(est, None)
            return
        _log(f"MOTOR = miniaudio ({descripcion}); arranca en {pos_inicial / SAMPLE_RATE * 1000.0:.0f} ms")
        generador = _generador(est, lector, pos_inicial, terminado)
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
    if _sesion.get("est") is not None:
        _log(f"detener desde: {_quien_llama()}")
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
    """Salta al momento indicado. El destino se aplica en el próximo
    trozo del generador: en RAM es cambiar un índice y en streaming es
    abrir otra ventana del archivo (milisegundos, sin recorrer el tema).
    La posición informada salta ya, así quien consulta no ve la vieja."""
    est = _sesion.get("est")
    if est is None:
        _log(f"buscar_ms({float(milisegundos):.0f}) SIN sesión local (se ignora) "
             f"desde: {_quien_llama()}")
        return
    try:
        destino = max(0.0, float(milisegundos))
    except Exception:
        return
    est["seek_ms"] = destino
    est["buscando"] = True
    est["pos_frames"] = _frames_desde_ms(destino)


def fijar_ganancia(ganancia_lineal):
    """Cambia el volumen en vivo (0.0 a 1.0)."""
    est = _sesion.get("est")
    if est is None:
        return
    try:
        est["ganancia"] = max(0.0, float(ganancia_lineal))
    except Exception:
        pass


def posicion_ms():
    """Posición AUDIBLE estimada del tema (ms) o None si no hay sesión.
    Sonando se descuenta la latencia de salida (lo ya entregado al
    dispositivo todavía no se oyó); en pausa es la posición exacta."""
    est = _sesion.get("est")
    if est is None:
        return None
    try:
        ms = float(est.get("pos_frames", 0)) / SAMPLE_RATE * 1000.0
        if est.get("listo") and not est.get("pausado"):
            ms -= LATENCIA_SALIDA_MS
        return max(0.0, ms)
    except Exception:
        return None


def buscando():
    """True mientras hay un seek en curso (pedido y todavía sin aplicar,
    o verificándose en MCI): la posición informada puede ser transitoria
    y quien la compare debe esperar."""
    est = _sesion.get("est")
    return est is not None and (est.get("seek_ms") is not None
                                or bool(est.get("buscando")))


def listo():
    """True si el motor ya arrancó (terminó de decodificar y está
    entregando audio o pausa)."""
    est = _sesion.get("est")
    return est is not None and bool(est.get("listo"))


def pausado():
    est = _sesion.get("est")
    return est is not None and bool(est.get("pausado"))


def hay_sesion():
    """True si hay una pista cargada en el motor (sonando o en pausa)."""
    return _sesion.get("est") is not None


def sonando():
    """True si hay una pista cargada y no está en pausa."""
    est = _sesion.get("est")
    return est is not None and not est.get("pausado")
