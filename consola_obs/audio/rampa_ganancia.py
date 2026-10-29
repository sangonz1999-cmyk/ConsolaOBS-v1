"""Volumen analógico para el audio local (parlantes de la PC).

RampaGanancia aplica la ganancia a cada trozo de audio recorriendo el
trozo de forma LINEAL desde la ganancia anterior hasta la nueva. Así,
mover una barra en pleno sonido no produce saltos ni "clics": el volumen
sube y baja de forma continua, de 0 a 100, y al volver a 1.0 el audio
sale intacto (sin tocar las muestras).

Con numpy (si está instalado) es casi gratis; sin numpy usa Python puro
(un poco más lento pero igual de correcto).
"""
import array

try:
    import numpy as _np
except Exception:  # sin numpy: camino Python puro
    _np = None

NCANALES = 2


class RampaGanancia:
    def __init__(self):
        self._g = None  # ganancia con la que terminó el trozo anterior

    def aplicar(self, trozo, destino):
        """Devuelve un trozo NUEVO (nunca modifica el original) con la
        ganancia 'destino' (0.0 a 1.0) aplicada con rampa."""
        try:
            destino = max(0.0, min(1.0, float(destino)))
        except Exception:
            destino = 1.0
        previa = destino if self._g is None else self._g
        self._g = destino
        if previa >= 0.9999 and destino >= 0.9999:
            return trozo
        if getattr(trozo, "typecode", None) != "h":
            return trozo
        n = len(trozo)
        if n == 0:
            return trozo
        if previa <= 0.0001 and destino <= 0.0001:
            return array.array("h", bytes(2 * n))
        try:
            if _np is not None:
                return self._con_numpy(trozo, previa, destino)
        except Exception:
            pass
        return self._python_puro(trozo, previa, destino)

    @staticmethod
    def _con_numpy(trozo, previa, destino):
        datos = _np.frombuffer(trozo, dtype=_np.int16).astype(_np.float32)
        if abs(previa - destino) < 1e-4:
            salida = datos * destino
        else:
            frames = max(1, len(datos) // NCANALES)
            rampa = _np.linspace(previa, destino, frames, dtype=_np.float32)
            salida = datos * _np.repeat(rampa, NCANALES)[:len(datos)]
        nuevo = array.array("h")
        nuevo.frombytes(_np.clip(salida, -32768, 32767).astype(_np.int16).tobytes())
        return nuevo

    @staticmethod
    def _python_puro(trozo, previa, destino):
        n = len(trozo)
        if abs(previa - destino) < 1e-4:
            return array.array("h", [int(x * destino) for x in trozo])
        frames = max(1, n // NCANALES)
        paso = (destino - previa) / frames
        salida = array.array("h", bytes(2 * n))
        for i in range(n):
            salida[i] = int(trozo[i] * (previa + paso * (i // NCANALES)))
        return salida
