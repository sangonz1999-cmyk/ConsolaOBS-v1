"""Servicio de pedidos a OBS con hilo propio.

Antes la ventana llamaba a OBS directamente: mover un fader, mutear o
cambiar el auricular hacía el pedido de red en el hilo de la ventana, y
cualquier demora de OBS (hasta el timeout de 5 s) congelaba todo el
programa. Ahora la interfaz sólo ENCOLA el pedido y sigue; un único hilo
trabajador los manda a OBS en orden y devuelve el resultado al hilo de
la ventana (vía hilo_ui).

Pedidos con 'clave': si llega uno nuevo con la misma clave mientras el
anterior todavía espera en la cola, el nuevo REEMPLAZA al viejo. Es lo
que hace fluido al fader: al arrastrarlo se generan decenas de valores
por segundo y sólo hace falta mandar el último.

'una_a_la_vez' resuelve los sondeos periódicos (ganancia, estado de
pads): si el anterior todavía no terminó, el nuevo se descarta en vez de
apilar hilos cuando OBS tarda en contestar.

Este módulo no conoce a OBS ni a Tkinter: recibe funciones. Por eso se
prueba con un OBS simulado (tests/test_servicio_obs.py).
"""
import collections
import logging
import threading

from consola_obs.nucleo import hilo_ui

_log = logging.getLogger("consola_obs")


class ServicioPedidos:
    def __init__(self, nombre="servicio-obs"):
        self._nombre = nombre
        self._cond = threading.Condition()
        self._orden = collections.deque()     # claves en orden de llegada
        self._pedidos = {}                    # clave -> (funcion, ok, error)
        self._sin_clave = 0
        self._hilo = None
        self._parar = False
        self._en_curso = set()

    # -- ciclo de vida -------------------------------------------------
    def iniciar(self):
        with self._cond:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._parar = False
            self._hilo = threading.Thread(target=self._bucle, name=self._nombre, daemon=True)
            self._hilo.start()

    def detener(self, vaciar=True):
        with self._cond:
            self._parar = True
            if vaciar:
                self._orden.clear()
                self._pedidos.clear()
            self._cond.notify_all()

    def vaciar(self):
        """Descarta lo que todavía no se mandó (por ejemplo al perder la
        conexión: no tiene sentido mandar pedidos viejos al reconectar)."""
        with self._cond:
            self._orden.clear()
            self._pedidos.clear()

    def pendientes(self):
        with self._cond:
            return len(self._orden)

    # -- pedidos -------------------------------------------------------
    def encolar(self, funcion, clave=None, al_terminar=None, al_fallar=None):
        """Agenda funcion() en el hilo del servicio. al_terminar(resultado)
        y al_fallar(error) corren en el hilo de la ventana."""
        with self._cond:
            if clave is None:
                self._sin_clave += 1
                clave = ("__sin_clave__", self._sin_clave)
            if clave not in self._pedidos:
                self._orden.append(clave)
            self._pedidos[clave] = (funcion, al_terminar, al_fallar)
            self._cond.notify()
        self.iniciar()

    def una_a_la_vez(self, clave, funcion, al_terminar=None, al_fallar=None):
        """Como encolar(), pero si ya hay uno con esa clave esperando o
        corriendo, éste se descarta. Devuelve True si se agendó."""
        with self._cond:
            if clave in self._pedidos or clave in self._en_curso:
                return False
        self.encolar(funcion, clave=clave, al_terminar=al_terminar, al_fallar=al_fallar)
        return True

    # -- hilo trabajador -----------------------------------------------
    def _bucle(self):
        while True:
            with self._cond:
                while not self._orden and not self._parar:
                    self._cond.wait()
                if self._parar:
                    return
                clave = self._orden.popleft()
                funcion, al_terminar, al_fallar = self._pedidos.pop(clave)
                self._en_curso.add(clave)
            try:
                resultado = funcion()
            except Exception as e:
                if al_fallar is not None:
                    hilo_ui.en_ui(al_fallar, e)
                else:
                    _log.warning("Pedido a OBS falló: %s: %s", type(e).__name__, e)
            else:
                if al_terminar is not None:
                    hilo_ui.en_ui(al_terminar, resultado)
            finally:
                with self._cond:
                    self._en_curso.discard(clave)


# Instancia única que usa el programa.
servicio = ServicioPedidos()


_sondeos_en_curso = set()
_lock_sondeos = threading.Lock()


def sondeo_si_libre(clave, funcion):
    """Para sondeos periódicos que hacen VARIOS pedidos seguidos (ganancia
    de todas las fuentes, estado del pad): corren en un hilo propio para
    no ocupar al servicio (así un fader nunca espera detrás de veinte
    consultas), pero nunca dos a la vez con la misma clave. Antes cada
    ciclo lanzaba un hilo nuevo sin mirar si el anterior había terminado
    y, con OBS lento, se apilaban. Devuelve True si arrancó."""
    with _lock_sondeos:
        if clave in _sondeos_en_curso:
            return False
        _sondeos_en_curso.add(clave)

    def _correr():
        try:
            funcion()
        except Exception:
            _log.exception("Error en el sondeo %s", clave)
        finally:
            with _lock_sondeos:
                _sondeos_en_curso.discard(clave)

    threading.Thread(target=_correr, name=f"sondeo-{clave}", daemon=True).start()
    return True
