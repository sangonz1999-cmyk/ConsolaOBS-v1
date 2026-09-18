"""Punto de entrada: python main.py (equivalente al .py unico original).

Chequeo previo con la stdlib solamente: en una PC recien clonada
(sin pip install hecho) el error pasa a ser una guia en espanol
con el comando exacto, en vez de un traceback crudo de
ModuleNotFoundError que no dice que hacer.
"""
import sys

PYTHON_MINIMA = (3, 9)


def _preflight():
    """True si se puede arrancar. Solo usa la stdlib, nunca muestra
    la contrasena ni toca la red."""
    ok = True
    if sys.version_info < PYTHON_MINIMA:
        print(
            "ERROR: se necesita Python 3.9 o mas nuevo "
            f"(este es {sys.version.split()[0]}).\n"
            "Descargalo de https://www.python.org/downloads/"
        )
        ok = False
    try:
        import tkinter  # noqa: F401
    except Exception:
        print(
            "ERROR: a este Python le falta tkinter (la interfaz grafica).\n"
            "Reinstala Python tildando 'tcl/tk and IDLE' en el instalador."
        )
        ok = False
    try:
        import obsws_python  # noqa: F401
    except Exception:
        print(
            "ERROR: falta la dependencia 'obsws-python' (conexion con OBS).\n"
            "En esta misma carpeta corre:\n"
            "  pip install -r requirements.txt\n"
            "o al menos:\n"
            "  pip install obsws-python"
        )
        ok = False
    # Opcionales: el programa anda igual sin ellos (con menos calidad
    # o sin audio local), asi que solo avisan.
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
                "Se instala con: pip install -r requirements.txt"
            )
    return ok


if __name__ == "__main__":
    if not _preflight():
        sys.exit(1)
    from consola_obs.app import main
    main()
