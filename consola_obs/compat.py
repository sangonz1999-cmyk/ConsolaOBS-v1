import subprocess


try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk, ImageFile, ImageFilter, ImageChops
    HAY_PILLOW = True
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    Image.MAX_IMAGE_PIXELS = None
except ImportError:
    HAY_PILLOW = False
    try:
        import subprocess
        import sys as _sys
        subprocess.check_call(
            [_sys.executable, "-m", "pip", "install", "--quiet", "Pillow"]
        )
        from PIL import Image, ImageDraw, ImageOps, ImageTk, ImageFile, ImageFilter, ImageChops
        HAY_PILLOW = True
        Image.MAX_IMAGE_PIXELS = None
        ImageFile.LOAD_TRUNCATED_IMAGES = True
    except Exception:
        HAY_PILLOW = False

# ImageGrab es un submódulo aparte de Pillow (y en Linux depende además
# de que el sistema tenga soporte de captura de pantalla, por ejemplo
# python3-xlib): puede faltar aunque Pillow sí esté instalado. Se
# importa por separado y con su propio try/except para que, si no está
# disponible, el programa siga funcionando igual, sólo que sin la foto
# congelada de la ventana durante el redimensionado (ver
# _capturar_snapshot_ventana más abajo).
try:
    from PIL import ImageGrab
except Exception:
    ImageGrab = None
