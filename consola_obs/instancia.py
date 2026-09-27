"""Una sola instancia: si el programa ya está abierto y se lo abre de
nuevo, avisa con [Cancelar] [Ejecutar de todas maneras].

En Windows se usa un mutex con nombre (atómico del sistema: no deja
archivos colgados ni hay carrera si se abre dos veces rapidísimo). En
Linux/macOS, un archivo con el PID + chequeo de si sigue vivo.
`marcar_en_ejecucion` devuelve True si YA había otra (y hay que
preguntar); `liberar` suelta al salir (con atexit en main.py).
"""
import os
import sys

_NOMBRE_MUTEX = "ConsolaOBS_SingleInstance_v1"
_testigo = {"mutexes": [], "archivo": None}


def _ruta_lock():
    try:
        from consola_obs import rutas as R
        base = R.CARPETA_CONFIG
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, "instancia.lock")


def _proceso_vivo(pid):
    if not pid or pid == os.getpid():
        return pid == os.getpid()
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True  # existe, sin permiso para señalizarlo
    except OSError:
        return False
    except Exception:
        return False


def marcar_en_ejecucion():
    """True si ya hay otra instancia corriendo (preguntar); False si
    esta es la primera (toma el testigo). Nunca lanza."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [
                ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            h = kernel32.CreateMutexW(None, False, _NOMBRE_MUTEX)
            if not h:
                return False
            try:
                _testigo["mutexes"].append(h)
            except Exception:
                pass
            return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        except Exception:
            pass
    try:
        ruta = _ruta_lock()
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
        except Exception:
            pass
        if os.path.isfile(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    pid_viejo = int((f.read() or "").strip())
            except Exception:
                pid_viejo = None
            if _proceso_vivo(pid_viejo):
                return True
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        _testigo["archivo"] = ruta
        return False
    except Exception:
        return False


def liberar():
    """Suelta el testigo al salir (sólo si es el dueño). Nunca lanza."""
    try:
        for h in list(_testigo.get("mutexes") or []):
            try:
                import ctypes
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(h)
            except Exception:
                pass
        _testigo["mutexes"] = []
    except Exception:
        pass
    try:
        ruta = _testigo.get("archivo")
        if ruta and os.path.isfile(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    dueno = int((f.read() or "").strip())
            except Exception:
                dueno = None
            if dueno == os.getpid():
                try:
                    os.remove(ruta)
                except Exception:
                    pass
        _testigo["archivo"] = None
    except Exception:
        pass


def preguntar_otra_instancia():
    """Ventana de aviso con [Cancelar] [Ejecutar de todas maneras].
    Devuelve True si ejecuta igual. Ante cualquier fallo, ejecuta (no
    bloquea por un cartel roto). Cancelar/X/Escape = no ejecuta."""
    decision = {"ejecutar": False}
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
    except Exception:
        return True
    try:
        win = tk.Toplevel(root)
        win.title("ConsolaOBS ya está en ejecución")
        win.configure(bg="#121722")
        win.resizable(False, False)
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        def _cancelar(event=None):
            decision["ejecutar"] = False
            try:
                win.destroy()
            except Exception:
                pass

        def _ejecutar(event=None):
            decision["ejecutar"] = True
            try:
                win.destroy()
            except Exception:
                pass

        tk.Label(
            win, text="ConsolaOBS ya se está ejecutando.",
            bg="#121722", fg="white",
            font=("TkDefaultFont", 11, "bold"), justify="left",
        ).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(
            win, text="Abrir otra instancia puede duplicar sonidos y hacer que\n"
                      "las dos consolas se peleen por el mismo OBS.",
            bg="#121722", fg="#8fa0bd",
            font=("TkDefaultFont", 9), justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 12))
        fila = tk.Frame(win, bg="#121722")
        fila.pack(fill="x", padx=18, pady=(0, 16))
        b_no = tk.Button(
            fila, text="Cancelar", bg="#242d3d", fg="white",
            activebackground="#2f3a4d", activeforeground="white",
            relief="flat", bd=0, padx=20, pady=7, cursor="hand2",
            command=_cancelar)
        b_no.pack(side="left", expand=True, fill="x", padx=(0, 6))
        tk.Button(
            fila, text="Ejecutar de todas maneras", bg="#242d3d", fg="white",
            activebackground="#2f3a4d", activeforeground="white",
            relief="flat", bd=0, padx=20, pady=7, cursor="hand2",
            command=_ejecutar).pack(side="left", expand=True, fill="x", padx=(6, 0))
        win.protocol("WM_DELETE_WINDOW", _cancelar)
        win.bind("<Escape>", _cancelar)
        win.bind("<Return>", _cancelar)
        try:
            win.update_idletasks()
            ancho = max(win.winfo_width(), win.winfo_reqwidth())
            alto = max(win.winfo_height(), win.winfo_reqheight())
            x = (win.winfo_screenwidth() - ancho) // 2
            y = (win.winfo_screenheight() - alto) // 2
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        try:
            b_no.focus_set()
            win.grab_set()
        except Exception:
            pass
        try:
            root.wait_window(win)
        except Exception:
            pass
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass
    return bool(decision["ejecutar"])
