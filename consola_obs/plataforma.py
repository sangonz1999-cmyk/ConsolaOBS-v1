import os
import shutil
import struct
import subprocess
import sys

from consola_obs import estado as E
from consola_obs import rutas as R


# ------------------------------------------------------------------
# CONGELADO DE PINTADO DE VENTANA (sólo Windows)
# ------------------------------------------------------------------
# El parpadeo al redimensionar en Windows no se origina (sólo) en
# nuestro código: Windows repinta el fondo de la ventana en cada
# micro-cambio de tamaño ANTES de que Tk llegue a dibujar nada encima,
# y ESE destello es el que se ve como parpadeo, sin importar qué tan
# liviana sea nuestra reconstrucción. La forma correcta de eliminarlo
# es pedirle al sistema operativo, con el mensaje nativo WM_SETREDRAW,
# que deje de repintar la ventana durante el arrastre, y recién forzar
# UN solo repintado limpio (con RedrawWindow) cuando el usuario suelta
# y la interfaz ya está reconstruida. Mientras el repintado está
# apagado, la pantalla se queda mostrando tal cual el último cuadro
# bueno -ni un rectángulo tapando, ni una animación: literalmente lo
# que ya había- hasta que se reactiva.
_ES_WINDOWS = sys.platform.startswith("win")

# ------------------------------------------------------------------
# NITIDEZ REAL (DPI): por qué antes se veía "pixelado"
# ------------------------------------------------------------------
# En Windows, si un programa no declara que entiende de DPI, el sistema
# lo dibuja a la resolución vieja (96 ppp) y después ESTIRA esa imagen
# hasta el tamaño real de la pantalla. En un monitor 1080p con escalado
# al 125/150% -que es como viene configurado casi cualquier equipo hoy-
# eso significa que cada pixel que dibuja Tk se agranda y se interpola:
# bordes con escalones, texto borroso, curvas dentadas. No importa qué
# tan lindo se dibuje adentro: lo que se ve es una foto agrandada.
#
# Declarando "per-monitor v2" ANTES de crear la ventana, Windows nos
# entrega el lienzo a la resolución nativa completa y cada línea que
# dibujamos cae en un pixel físico de verdad. Eso, más el render con
# Pillow de pads y botones (supersampling + LANCZOS), es lo que hace
# que la interfaz se vea "1080" y no ampliada.
if _ES_WINDOWS:
    try:
        import ctypes as _ctypes_dpi
        try:
            # -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Win 10+)
            _ctypes_dpi.windll.user32.SetProcessDpiAwarenessContext(_ctypes_dpi.c_void_p(-4))
        except Exception:
            try:
                _ctypes_dpi.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                _ctypes_dpi.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

if _ES_WINDOWS:
    import ctypes

    _user32 = ctypes.windll.user32
    _gdi32 = ctypes.windll.gdi32
    _GA_ROOT = 2
    _WM_SETREDRAW = 0x000B
    _RDW_INVALIDATE = 0x0001
    _RDW_ERASE = 0x0004
    _RDW_ALLCHILDREN = 0x0080
    _RDW_UPDATENOW = 0x0100
    _GCLP_HBRBACKGROUND = -10

    # Los handles de Windows (HWND, HBRUSH) son del tamaño de un
    # puntero: en Windows de 64 bits eso es 8 bytes. Si no se le avisa
    # a ctypes, asume que estas funciones devuelven un entero de 32
    # bits (el tipo por defecto) y puede llegar a truncar el valor real
    # -handles grandes que dejan de coincidir con la ventana de
    # verdad-, haciendo que estas llamadas fallen en silencio o, peor,
    # actúen sobre la ventana equivocada. Declarar los tipos correctos
    # (c_void_p) es lo que evita ese problema en 64 bits.
    _user32.GetAncestor.restype = ctypes.c_void_p
    _user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _user32.SendMessageW.restype = ctypes.c_void_p
    _user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    _user32.RedrawWindow.restype = ctypes.c_int
    _user32.RedrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    _user32.SetClassLongPtrW.restype = ctypes.c_void_p
    _user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    _gdi32.CreateSolidBrush.restype = ctypes.c_void_p
    _gdi32.CreateSolidBrush.argtypes = [ctypes.c_uint]
    _gdi32.AddFontResourceExW.restype = ctypes.c_int
    _gdi32.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_void_p]

    def _hwnd_ventana_real():
        """winfo_id() en Tk devuelve el HWND del widget, que en el caso
        de la ventana principal ya suele ser el HWND de nivel superior
        de verdad; GetAncestor(..., GA_ROOT) sube por la jerarquía hasta
        ese HWND raíz de todos modos, por las dudas, para asegurarnos
        de mandarle los mensajes de pintado a la ventana que Windows
        administra (título, bordes) y no a un widget interno."""
        try:
            return _user32.GetAncestor(E.ventana.winfo_id(), _GA_ROOT)
        except Exception:
            return None

    def _fijar_color_fondo_nativo(hex_color):
        """Reemplaza el PINCEL DE FONDO de la clase de ventana (lo que
        Windows usa, por su cuenta, para 'borrar' cualquier franja nueva
        que se destapa al agrandar la ventana -ver WM_ERASEBKGND-) por
        uno del mismo color oscuro que el resto de la interfaz.

        Este es el verdadero origen del parpadeo/flash al redimensionar
        en Windows con temas oscuros: el pincel de fondo por defecto de
        la clase de ventana que usa Tk es más claro (blanco/gris), así
        que Windows pinta esa franja nueva con ESE color un instante
        antes de que Tk llegue a dibujar encima con el color correcto.
        Frenar el repintado (ver _congelar_pintado_ventana) no alcanza
        para esto, porque no cambia qué color usaría Windows para esa
        franja la próxima vez que sí repinte: hay que cambiar el pincel
        en sí, una sola vez, para que hasta el propio borrado del
        sistema operativo ya sea del color correcto."""
        hwnd = _hwnd_ventana_real()
        if not hwnd:
            return
        try:
            hex_color = hex_color.lstrip("#")
            r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            colorref = r | (g << 8) | (b << 16)  # Windows usa 0x00BBGGRR
            pincel = _gdi32.CreateSolidBrush(colorref)
            if pincel:
                _user32.SetClassLongPtrW(hwnd, _GCLP_HBRBACKGROUND, pincel)
        except Exception:
            pass

    def _congelar_pintado_ventana():
        hwnd = _hwnd_ventana_real()
        if hwnd:
            try:
                _user32.SendMessageW(hwnd, _WM_SETREDRAW, 0, 0)
            except Exception:
                pass

    def _descongelar_pintado_ventana():
        hwnd = _hwnd_ventana_real()
        if hwnd:
            try:
                _user32.SendMessageW(hwnd, _WM_SETREDRAW, 1, 0)
                _user32.RedrawWindow(
                    hwnd, None, None,
                    _RDW_INVALIDATE | _RDW_ERASE | _RDW_ALLCHILDREN | _RDW_UPDATENOW
                )
            except Exception:
                pass

    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _VK_LBUTTON = 0x01

    def _boton_izquierdo_presionado():
        """True si el botón izquierdo del mouse está físicamente
        presionado AHORA (lectura directa al sistema, funciona aunque
        el arrastre lo haya iniciado el borde de la ventana, cuyos
        eventos no pasan por Tk). Se usa para salir del modo
        super-optimizador SÓLO al soltar de verdad."""
        try:
            return bool(_user32.GetAsyncKeyState(_VK_LBUTTON) & 0x8000)
        except Exception:
            return False

    _FR_PRIVATE = 0x10  # la fuente sólo queda disponible para ESTE
    # proceso (no se "instala" en Windows ni queda visible para otros
    # programas) y Windows la desregistra solo cuando el programa
    # termina, así que no hace falta ni querido hacer limpieza manual.

    def _registrar_fuente_ttf_windows(ruta):
        try:
            return _gdi32.AddFontResourceExW(ruta, _FR_PRIVATE, None) > 0
        except Exception:
            return False
else:
    def _congelar_pintado_ventana():
        pass

    def _descongelar_pintado_ventana():
        pass

    def _boton_izquierdo_presionado():
        return False

    def _fijar_color_fondo_nativo(hex_color):
        pass

    def _registrar_fuente_ttf_windows(ruta):
        return False


def _escribir_readme_assets(ruta, contenido):
    """Deja una guía corta dentro de cada carpeta de recursos, sólo la
    primera vez (si el archivo ya existe, no lo pisa), explicando qué
    archivos reconoce el programa ahí."""
    if os.path.exists(ruta):
        return
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
    except Exception:
        pass


def _nombre_familia_ttf(ruta):
    """Lee el nombre de familia tipográfica desde adentro del propio
    archivo (tabla 'name', registro 16 -nombre tipográfico preferido-
    o, si no está, el 1 -nombre de familia clásico-), para no depender
    de que el nombre del ARCHIVO coincida con el nombre interno real
    de la fuente (a veces no coinciden)."""
    try:
        with open(ruta, "rb") as f:
            datos = f.read()
        num_tablas = struct.unpack(">H", datos[4:6])[0]
        offset_name = None
        for i in range(num_tablas):
            entrada = datos[12 + i * 16: 12 + i * 16 + 16]
            if entrada[0:4] == b"name":
                offset_name = struct.unpack(">I", entrada[8:12])[0]
                break
        if offset_name is None:
            return None
        _formato, cuenta, offset_cadenas = struct.unpack(
            ">HHH", datos[offset_name:offset_name + 6]
        )
        base_cadenas = offset_name + offset_cadenas
        candidatos = {}
        for i in range(cuenta):
            base_reg = offset_name + 6 + i * 12
            plataforma_id, _cod_id, _idioma_id, nombre_id, largo, offset = struct.unpack(
                ">HHHHHH", datos[base_reg:base_reg + 12]
            )
            if nombre_id not in (1, 16):
                continue
            crudo = datos[base_cadenas + offset: base_cadenas + offset + largo]
            try:
                texto = crudo.decode("utf-16-be") if plataforma_id in (0, 3) else crudo.decode("latin-1")
            except Exception:
                continue
            texto = texto.strip()
            if texto:
                candidatos[nombre_id] = texto
        return candidatos.get(16) or candidatos.get(1)
    except Exception:
        # Archivo corrupto, con una tabla 'name' rara, etc.: no hay
        # forma segura de saber el nombre, así que mejor no arriesgar
        # a registrar una fuente con un nombre inventado.
        return None


def _registrar_fuente_ttf_macos(ruta):
    try:
        core_text = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreText.framework/CoreText"
        )
        core_foundation = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        core_foundation.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
        ruta_bytes = os.fsencode(ruta)
        url = core_foundation.CFURLCreateFromFileSystemRepresentation(
            None, ruta_bytes, len(ruta_bytes), False
        )
        if not url:
            return False
        # kCTFontManagerScopeProcess = 1: registrada sólo para este
        # proceso, nada queda instalado de forma permanente en el Mac
        # del usuario.
        return bool(core_text.CTFontManagerRegisterFontsForURL(url, 1, None))
    except Exception:
        return False


def _registrar_fuente_ttf_linux(ruta):
    """En Linux (fontconfig) no existe un registro "sólo para este
    proceso" tan directo como en Windows/Mac, así que la forma
    práctica y estándar es copiar el archivo a la carpeta de fuentes
    del usuario (~/.local/share/fonts, no requiere permisos de
    administrador) y refrescar el caché con fc-cache. Si algo de esto
    falla -sin fc-cache instalado, sin permisos, etc.- no se registra
    nada y el programa sigue con la fuente del sistema."""
    try:
        carpeta_usuario = os.path.join(os.path.expanduser("~"), ".local", "share", "fonts")
        os.makedirs(carpeta_usuario, exist_ok=True)
        destino = os.path.join(carpeta_usuario, os.path.basename(ruta))
        if not os.path.exists(destino):
            shutil.copy2(ruta, destino)
        subprocess.run(["fc-cache", "-f", carpeta_usuario], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def _registrar_fuentes_personalizadas():
    if not os.path.isdir(R.CARPETA_FUENTES_TIPOGRAFIA):
        return
    for archivo in sorted(os.listdir(R.CARPETA_FUENTES_TIPOGRAFIA)):
        if not archivo.lower().endswith((".ttf", ".otf")):
            continue
        ruta = os.path.join(R.CARPETA_FUENTES_TIPOGRAFIA, archivo)
        if _ES_WINDOWS:
            registrada = _registrar_fuente_ttf_windows(ruta)
        elif sys.platform == "darwin":
            registrada = _registrar_fuente_ttf_macos(ruta)
        else:
            registrada = _registrar_fuente_ttf_linux(ruta)
        if not registrada:
            continue
        nombre_familia = _nombre_familia_ttf(ruta)
        if nombre_familia and nombre_familia not in E._NOMBRES_FUENTES_PERSONALIZADAS:
            E._NOMBRES_FUENTES_PERSONALIZADAS.append(nombre_familia)
