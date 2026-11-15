"""Modelo de estado del mezclador: lo que OBS dice de cada fuente.

Una única fuente de verdad para volumen, mute y monitoreo. Antes ese
estado vivía repartido en los diccionarios de widgets de cada tarjeta y
lo escribían a mano los eventos de OBS, los botones, la resincronización
y el refresco de la lista, cada uno a su manera. Ahora todos pasan por
Mezclador.actualizar(), que guarda el valor y avisa ("fuente_cambiada")
SÓLO de lo que cambió de verdad. La interfaz se limita a reflejarlo.

Es seguro entre hilos: los eventos de OBS llegan por el hilo de eventos y
los botones por el de la ventana.

No depende de Tkinter, de Qt ni de OBS: se prueba solo.
"""
import dataclasses
import threading

from consola_obs.nucleo import avisos

MONITOR_APAGADO = "OBS_MONITORING_TYPE_NONE"
MONITOR_SOLO_MONITOREO = "OBS_MONITORING_TYPE_MONITOR_ONLY"
MONITOR_Y_SALIDA = "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT"

MONITOREO_POR_NUMERO = {
    0: MONITOR_APAGADO,
    1: MONITOR_SOLO_MONITOREO,
    2: MONITOR_Y_SALIDA,
}

# Por debajo de esto, el volumen cuenta como silencio (OBS guarda -100,
# el fader su mínimo). Mismo valor que estado.UMBRAL_SILENCIO.
UMBRAL_SILENCIO_DB = -60.0
TOLERANCIA_DB = 0.05


def tipo_monitor_normalizado(valor):
    """El tipo de monitoreo de OBS llega de dos formas y esta app usa una
    sola: el NOMBRE ('OBS_MONITORING_TYPE_...'). Pero el WebSocket a
    veces lo manda como ENTERO (0=apagado, 1=solo monitores,
    2=monitores+stream), y comparar un 2 contra el texto nunca da igual.
    Traduce el número al nombre; lo desconocido se devuelve tal cual."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, int):
        return MONITOREO_POR_NUMERO.get(valor, valor)
    texto = str(valor or "").strip()
    if texto.isdigit():
        return MONITOREO_POR_NUMERO.get(int(texto), texto)
    return texto


def mismo_volumen(a, b, umbral_silencio=UMBRAL_SILENCIO_DB):
    """Dos volúmenes en dB son 'iguales' si difieren menos de 0.05 dB o
    si los dos están en silencio. Un dato ilegible no cuenta como cambio."""
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return True
    if a <= umbral_silencio and b <= umbral_silencio:
        return True
    return abs(a - b) < TOLERANCIA_DB


@dataclasses.dataclass
class EstadoFuente:
    nombre: str
    volumen_db: float = None
    muted: bool = None
    tipo_monitor: str = None


CAMPOS = ("volumen_db", "muted", "tipo_monitor")


class Mezclador:
    def __init__(self, umbral_silencio=UMBRAL_SILENCIO_DB):
        self._lock = threading.Lock()
        self._fuentes = {}
        self.umbral_silencio = umbral_silencio

    def actualizar(self, nombre, origen="obs", avisar=True, forzar=False, **campos):
        """Guarda los campos dados (volumen_db, muted, tipo_monitor) y, si
        alguno cambió, emite "fuente_cambiada"(nombre, cambios, origen).
        origen: "obs" (evento), "local" (botón de la consola), "resync",
        "carga" (lista leída al conectar/actualizar).
        forzar=True avisa con todos los campos dados aunque coincidan con
        lo guardado (lo usa la resincronización cuando la pantalla quedó
        distinta del modelo). Devuelve el diccionario de cambios."""
        cambios = {}
        with self._lock:
            estado = self._fuentes.get(nombre)
            if estado is None:
                estado = self._fuentes[nombre] = EstadoFuente(nombre)
            for campo, valor in campos.items():
                if campo not in CAMPOS or valor is None:
                    continue
                valor = self._normalizar(campo, valor)
                if forzar or not self._iguales(campo, getattr(estado, campo), valor):
                    cambios[campo] = valor
                setattr(estado, campo, valor)
        if cambios and avisar:
            avisos.emitir("fuente_cambiada", nombre, dict(cambios), origen)
        return cambios

    def obtener(self, nombre):
        with self._lock:
            estado = self._fuentes.get(nombre)
            return dataclasses.replace(estado) if estado else None

    def nombres(self):
        with self._lock:
            return list(self._fuentes)

    def quitar(self, nombre):
        with self._lock:
            self._fuentes.pop(nombre, None)

    def renombrar(self, viejo, nuevo):
        with self._lock:
            estado = self._fuentes.pop(viejo, None)
            if estado is not None:
                estado.nombre = nuevo
                self._fuentes[nuevo] = estado

    def limpiar(self):
        with self._lock:
            self._fuentes.clear()

    # -- internos ------------------------------------------------------
    def _normalizar(self, campo, valor):
        if campo == "muted":
            return bool(valor)
        if campo == "tipo_monitor":
            return tipo_monitor_normalizado(valor)
        if campo == "volumen_db":
            try:
                return float(valor)
            except (TypeError, ValueError):
                return None
        return valor

    def _iguales(self, campo, a, b):
        if a is None:
            return False
        if campo == "volumen_db":
            return mismo_volumen(a, b, self.umbral_silencio)
        return a == b


# Instancia única que usa el programa.
mezclador = Mezclador()
