"""Motor de audio local ALTERNATIVO para Windows (sin dependencias).

Se usa cuando 'miniaudio' no está instalado (típico en Python muy nuevo,
donde pip no encuentra rueda y falla al compilar) o cuando no consigue
abrir la salida de audio. Usa el reproductor MCI que trae Windows
(winmm.dll): reproduce mp3/wav/wma/etc., permite cambiar el volumen EN
VIVO (analógico, 0-1000) y pausar / buscar.

Todas las llamadas MCI de una sesión las hace el MISMO hilo (el que la
abrió), como pide MCI.
"""
import itertools
import sys
import time

_contador = itertools.count(1)
_winmm = None
if sys.platform == "win32":
    try:
        import ctypes
        _winmm = ctypes.windll.winmm
    except Exception:
        _winmm = None


def disponible():
    return _winmm is not None


def _cmd(texto):
    """Ejecuta un comando MCI. Devuelve (codigo_error, respuesta)."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        err = _winmm.mciSendStringW(texto, buf, 255, 0)
        return err, buf.value
    except Exception as e:
        return -1, str(e)


def _texto_error(codigo):
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        _winmm.mciGetErrorStringW(codigo, buf, 255)
        return buf.value
    except Exception:
        return str(codigo)


class Reproductor:
    def __init__(self):
        self.alias = f"consolaobs{next(_contador)}"
        self.abierto = False
        self.error = ""

    def abrir(self, ruta):
        ruta = str(ruta).replace('"', "")
        for tipo in ("", " type mpegvideo"):
            err, _ = _cmd(f'open "{ruta}"{tipo} alias {self.alias}')
            if err == 0:
                self.abierto = True
                _cmd(f"set {self.alias} time format milliseconds")
                return True
            self.error = _texto_error(err)
        return False

    def reproducir(self, desde_ms=0):
        if desde_ms and desde_ms > 0:
            return _cmd(f"play {self.alias} from {int(desde_ms)}")[0] == 0
        return _cmd(f"play {self.alias}")[0] == 0

    def volumen(self, ganancia):
        try:
            v = int(round(max(0.0, min(1.0, float(ganancia))) * 1000))
        except Exception:
            v = 1000
        _cmd(f"setaudio {self.alias} volume to {v}")

    def modo(self):
        return _cmd(f"status {self.alias} mode")[1].strip().lower()

    def pausar(self):
        _cmd(f"pause {self.alias}")

    def reanudar(self):
        _cmd(f"resume {self.alias}")

    def buscar(self, ms, seguir_sonando=True):
        _cmd(f"seek {self.alias} to {int(max(0, ms))}")
        if seguir_sonando:
            _cmd(f"play {self.alias}")

    def cerrar(self):
        if self.abierto:
            _cmd(f"stop {self.alias}")
            _cmd(f"close {self.alias}")
            self.abierto = False
