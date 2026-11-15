"""Puente seguro desde cualquier hilo hacia el hilo de la ventana.

Tkinter no es seguro entre hilos: tocar widgets (o incluso llamar a
ventana.after) desde un hilo secundario funciona casi siempre y falla
de forma rara a veces. Acá los hilos sólo dejan funciones en una cola,
y un temporizador que corre EN el hilo de la ventana las ejecuta.

Sin depender de Tkinter: el que crea la ventana llama a instalar() con
una función 'programar(ms, funcion)' (para Tk, ventana.after). Los
tests usan ejecutar_pendientes() a mano.
"""
import logging
import queue
import threading

_log = logging.getLogger("consola_obs")

INTERVALO_MS = 15
_cola = queue.SimpleQueue()
_estado = {"programar": None, "hilo_ui": None}


def instalar(programar):
    """programar(ms, funcion): agenda 'funcion' en el hilo de la ventana.
    Se llama una vez, desde el hilo de la ventana."""
    _estado["programar"] = programar
    _estado["hilo_ui"] = threading.get_ident()
    _tick()


def es_hilo_ui():
    return _estado["hilo_ui"] is not None and threading.get_ident() == _estado["hilo_ui"]


def en_ui(funcion, *args, **kwargs):
    """Ejecuta funcion(*args) en el hilo de la ventana lo antes posible.
    Desde el propio hilo de la ventana también se encola (nunca corre en
    el momento), así el orden de ejecución es siempre el mismo."""
    _cola.put((funcion, args, kwargs))


def ejecutar_pendientes(maximo=500):
    """Corre lo encolado. La llama el temporizador (o un test)."""
    for _ in range(maximo):
        try:
            funcion, args, kwargs = _cola.get_nowait()
        except queue.Empty:
            return
        try:
            funcion(*args, **kwargs)
        except Exception:
            _log.exception("Error en una tarea de la interfaz")


def _tick():
    ejecutar_pendientes()
    programar = _estado["programar"]
    if programar is None:
        return
    try:
        programar(INTERVALO_MS, _tick)
    except Exception:
        # La ventana se cerró: se deja de programar.
        _estado["programar"] = None
