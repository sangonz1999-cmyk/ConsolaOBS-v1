"""Botón 'Probar parlantes' de Ajustes > Audio: un tono de 5 segundos
por el mismo motor de audio local que usan los pads y la música
(miniaudio o, si falta, el reproductor de Windows). Mientras suena, la
barra 'Volumen parlantes (PC)' lo cambia en vivo."""
import math
import os
import struct
import tempfile
import wave

from consola_obs import estado as E
from consola_obs.audio import motor_local as mod_motor_local
from consola_obs.audio import volumen_salida as mod_volumen_salida

DURACION_S = 5
_TOKEN = "prueba-parlantes"


def _ruta_tono():
    ruta = os.path.join(tempfile.gettempdir(), "consolaobs_tono_prueba.wav")
    if os.path.exists(ruta):
        return ruta
    frames = bytearray()
    for i in range(44100 * DURACION_S):
        # tono de 440 Hz con un leve vibrato para que se note bien
        v = int(14000 * math.sin(2 * math.pi * 440 * i / 44100))
        frames += struct.pack("<hh", v, v)
    with wave.open(ruta, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(bytes(frames))
    return ruta


def probar():
    """Devuelve (ok, mensaje)."""
    if mod_motor_local.hay_sesion():
        return False, ("Hay música sonando por la PC: si la escuchás, los "
                       "parlantes funcionan. Pausala para usar la prueba.")
    try:
        ruta = _ruta_tono()
        mod_motor_local.reproducir(ruta, _TOKEN, mod_volumen_salida.factor_pc())
    except Exception as e:
        return False, f"No se pudo iniciar la prueba: {e}"

    def _seguir(restan=int(DURACION_S * 1000 / 50)):
        if restan <= 0 or not mod_motor_local.hay_sesion():
            return
        try:
            mod_motor_local.fijar_ganancia(mod_volumen_salida.factor_pc())
            E.ventana.after(50, lambda: _seguir(restan - 1))
        except Exception:
            pass

    _seguir()
    return True, "Sonando… mové 'Volumen parlantes (PC)' para oírlo cambiar."
