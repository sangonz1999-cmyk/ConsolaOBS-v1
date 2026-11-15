"""Avisos internos (publicar / suscribir) entre el núcleo y la interfaz.

Antes la capa de OBS llamaba directamente a funciones de la interfaz
(pintar el botón de mute, refrescar el título de la escena, apagar un
pad…). Eso ataba todo con todo: obs/cliente importaba ui/tarjeta_fuente,
que a su vez importaba obs/cliente. Ahora el núcleo sólo EMITE un aviso
("fuente_cambiada", "escena_cambiada", …) y la interfaz se suscribe. Una
interfaz nueva (Qt) se suscribe a los mismos avisos sin tocar el núcleo.

Los suscriptores SIEMPRE corren en el hilo de la ventana: si se emite
desde otro hilo, el aviso viaja por hilo_ui.
"""
import collections
import logging
import threading

from consola_obs.nucleo import hilo_ui

_log = logging.getLogger("consola_obs")
_suscriptores = collections.defaultdict(list)
_lock = threading.Lock()

# Temas que usa el programa (la lista documenta el contrato; emitir un
# tema que no está acá también funciona).
TEMAS = {
    "fuente_cambiada":          "(nombre, cambios: dict, origen) volumen_db / muted / tipo_monitor",
    "fuente_renombrada":        "(nombre_viejo, nombre_nuevo)",
    "filtros_cambiados":        "(nombre) se creó/borró/prendió/apagó/reordenó un filtro",
    "lista_fuentes_cambio":     "() hay que volver a leer la lista de fuentes",
    "escena_cambiada":          "() cambió qué fuentes están en la escena al aire",
    "coleccion_cambiada":       "() cambió la colección de escenas",
    "conectado":                "() la conexión con OBS quedó lista",
    "aviso_conexion":           "(tipo, texto, fijo) aviso no bloqueante de conexión",
    "aviso_conexion_cerrar":    "()",
    "pedir_ajustes_conexion":   "() abrir Ajustes en la pestaña Conexión",
    "musica_estado_cambio":     "() refrescar el mini reproductor",
    "pad_terminado":            "(indice, token) apagar el pad si sigue vigente",
}


def suscribir(tema, funcion):
    with _lock:
        if funcion not in _suscriptores[tema]:
            _suscriptores[tema].append(funcion)


def desuscribir(tema, funcion):
    with _lock:
        if funcion in _suscriptores[tema]:
            _suscriptores[tema].remove(funcion)


def limpiar():
    """Sólo para tests."""
    with _lock:
        _suscriptores.clear()


def emitir(tema, *args):
    """Avisa a los suscriptores de 'tema'. Desde el hilo de la ventana
    corre en el acto; desde otro hilo, apenas la ventana pueda."""
    if hilo_ui.es_hilo_ui():
        _despachar(tema, args)
    else:
        hilo_ui.en_ui(_despachar, tema, args)


def _despachar(tema, args):
    with _lock:
        funciones = list(_suscriptores.get(tema, ()))
    for funcion in funciones:
        try:
            funcion(*args)
        except Exception:
            _log.exception("Error atendiendo el aviso %r en %s", tema,
                           getattr(funcion, "__name__", funcion))
