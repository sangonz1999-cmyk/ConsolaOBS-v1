"""Punto de entrada: python main.py (o doble clic en este archivo).

Chequeo previo con la stdlib solamente: en una PC recien clonada
(sin pip install hecho) el error pasa a ser una guia en espanol
con el comando exacto, en vez de un traceback crudo de
ModuleNotFoundError que no dice que hacer.

Pensado tambien para doble clic (sin terminal): el error se muestra
en una ventana y la consola no se cierra sola antes de poder leerlo.
"""
import sys

PYTHON_MINIMA = (3, 9)


def _preflight():
    """Devuelve (ok, errores). Solo usa la stdlib, nunca muestra
    la contrasena ni toca la red. Los opcionales solo avisan por
    consola (el programa anda igual sin ellos)."""
    errores = []
    if sys.version_info < PYTHON_MINIMA:
        errores.append(
            "Se necesita Python 3.9 o mas nuevo "
            f"(este es {sys.version.split()[0]}).\n"
            "Descargalo de https://www.python.org/downloads/"
        )
    try:
        import tkinter  # noqa: F401
    except Exception:
        errores.append(
            "A este Python le falta tkinter (la interfaz grafica).\n"
            "Reinstala Python tildando 'tcl/tk and IDLE' en el instalador."
        )
    try:
        import obsws_python  # noqa: F401
    except Exception:
        errores.append(
            "Falta la dependencia 'obsws-python' (conexion con OBS).\n"
            "Opcion facil: doble clic en instalar.bat (hace todo solo).\n"
            "O en una terminal, en esta misma carpeta:\n"
            "  pip install -r requirements.txt"
        )
    # Opcionales: el programa anda igual sin ellos (con menos calidad
    # o sin audio local), asi que solo avisan por consola.
    opcionales = (
        ("PIL", "Pillow", "imagenes de pads mas nitidas"),
        ("miniaudio", "miniaudio", "escuchar los efectos en esta PC"),
        ("pymupdf", "pymupdf", "iconos SVG originales de OBS"),
    )
    for modulo, paquete, para_que in opcionales:
        try:
            __import__(modulo)
        except Exception:
            print(
                f"AVISO: falta {paquete} (opcional, para {para_que}). "
                "Se instala con instalar.bat o pip install -r requirements.txt"
            )
    return (not errores, errores)


def _mostrar_error_arranque(errores):
    """Hace visible el error aunque no haya terminal (doble clic):
    ventana emergente + la consola queda esperando una tecla."""
    texto = "\n\n".join(errores)
    try:
        print(texto)
    except Exception:
        pass
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror("ConsolaOBS no puede arrancar", texto)
        try:
            _root.destroy()
        except Exception:
            pass
    except Exception:
        pass
    try:
        input("Presiona Enter para cerrar...")
    except Exception:
        pass


if __name__ == "__main__":
    _ok, _errores = _preflight()
    if not _ok:
        _mostrar_error_arranque(_errores)
        sys.exit(1)
    from consola_obs.app import main
    main()
