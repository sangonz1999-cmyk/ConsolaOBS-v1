"""Registro de errores a archivo.

En el .exe (--windowed) no hay consola: todo lo que se imprimía con
print() y cualquier error no capturado se perdía. Este módulo:

  - escribe un archivo rotativo config/consola.log (1 MB x 3 copias);
  - captura los errores no manejados del hilo principal, de los hilos
    secundarios y de los callbacks de la ventana;
  - redirige print()/stderr al mismo archivo, sin dejar de mostrarlos
    en la terminal cuando la hay.

Nada de acá lanza excepciones: si el registro falla, el programa sigue.
"""
import logging
import logging.handlers
import os
import sys
import threading

NOMBRE_LOG = "consola.log"
NOMBRE_LOG_CONEXION = "conexion.log"
_TAMANO_MAXIMO = 1024 * 1024
_COPIAS = 3

_configurado = {"hecho": False}
log = logging.getLogger("consola_obs")


class _SalidaALog:
    """Reemplazo de sys.stdout/sys.stderr: manda cada línea al registro
    y, si había una salida real (terminal), también la escribe ahí."""

    def __init__(self, original, nivel):
        self._original = original
        self._nivel = nivel
        self._resto = ""
        self._local = threading.local()

    def write(self, texto):
        try:
            if self._original is not None:
                self._original.write(texto)
        except Exception:
            pass
        # Evita recursión si el propio logging imprime un error.
        if getattr(self._local, "dentro", False):
            return len(texto or "")
        self._local.dentro = True
        try:
            self._resto += str(texto or "")
            while "\n" in self._resto:
                linea, self._resto = self._resto.split("\n", 1)
                if linea.strip():
                    log.log(self._nivel, linea.rstrip())
        except Exception:
            pass
        finally:
            self._local.dentro = False
        return len(texto or "")

    def flush(self):
        try:
            if self._original is not None:
                self._original.flush()
        except Exception:
            pass

    def isatty(self):
        return False


def _manejador_rotativo(carpeta, nombre, formato):
    manejador = logging.handlers.RotatingFileHandler(
        os.path.join(carpeta, nombre), maxBytes=_TAMANO_MAXIMO,
        backupCount=_COPIAS, encoding="utf-8", delay=True)
    manejador.setFormatter(logging.Formatter(formato, "%Y-%m-%d %H:%M:%S"))
    return manejador


def configurar():
    """Deja el registro funcionando. Se puede llamar más de una vez."""
    if _configurado["hecho"]:
        return
    _configurado["hecho"] = True
    try:
        from consola_obs import rutas as R
        carpeta = R.CARPETA_CONFIG
        os.makedirs(carpeta, exist_ok=True)
        log.setLevel(logging.INFO)
        log.propagate = False
        log.addHandler(_manejador_rotativo(
            carpeta, NOMBRE_LOG, "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
        # El log de conexión conserva su archivo propio (lo nombra el
        # README y los mensajes de error), ahora con rotación.
        conexion = logging.getLogger("consola_obs.conexion")
        # Sin propagar: la misma línea ya llega a consola.log por el
        # print() de red.log_conexion.
        conexion.propagate = False
        conexion.addHandler(_manejador_rotativo(
            carpeta, NOMBRE_LOG_CONEXION, "%(asctime)s %(message)s"))
    except Exception:
        return

    try:
        sys.stdout = _SalidaALog(sys.stdout, logging.INFO)
        sys.stderr = _SalidaALog(sys.stderr, logging.ERROR)
    except Exception:
        pass

    def _error_no_manejado(tipo, valor, traza):
        if issubclass(tipo, KeyboardInterrupt):
            return
        try:
            log.critical("Error no manejado", exc_info=(tipo, valor, traza))
        except Exception:
            pass

    def _error_en_hilo(args):
        if issubclass(args.exc_type, SystemExit):
            return
        try:
            nombre = getattr(args.thread, "name", "?")
            log.error("Error no manejado en el hilo %s", nombre,
                      exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        except Exception:
            pass

    try:
        sys.excepthook = _error_no_manejado
        threading.excepthook = _error_en_hilo
    except Exception:
        pass

    try:
        from consola_obs.update.version import VERSION
        log.info("=== ConsolaOBS v%s iniciado (Python %s) ===",
                 VERSION, sys.version.split()[0])
    except Exception:
        pass


def instalar_en_ventana(ventana):
    """Tkinter traga en silencio los errores de los callbacks (botones,
    after, eventos): acá se los manda al registro."""
    def _error_en_callback(tipo, valor, traza):
        try:
            log.error("Error en un callback de la interfaz",
                      exc_info=(tipo, valor, traza))
        except Exception:
            pass
    try:
        ventana.report_callback_exception = _error_en_callback
    except Exception:
        pass


def registrar_conexion(paso, detalle=""):
    """Línea del log de conexión (archivo conexion.log + consola.log)."""
    try:
        configurar()
        logging.getLogger("consola_obs.conexion").info(
            "[%s] %s", paso, str(detalle).rstrip())
    except Exception:
        pass
