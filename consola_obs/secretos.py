"""Guardado cifrado de secretos (contraseña de OBS, clave de sync).

En Windows usa DPAPI (CryptProtectData): el dato queda cifrado con la
cuenta de Windows del usuario, así que el archivo de config ya no
muestra la contraseña en texto plano ni sirve copiado a otra PC u otro
usuario. En otros sistemas no hay DPAPI y el valor se guarda tal cual
(igual que antes).

Formato guardado: "dpapi:<base64>". Un valor sin ese prefijo se lee
como texto plano, para aceptar las configuraciones viejas.
"""
import base64
import sys

PREFIJO = "dpapi:"
_ES_WINDOWS = sys.platform.startswith("win")


def _dpapi(datos, cifrar):
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    bufer = ctypes.create_string_buffer(datos, len(datos))
    entrada = _Blob(len(datos), ctypes.cast(bufer, ctypes.POINTER(ctypes.c_char)))
    salida = _Blob()
    funcion = crypt32.CryptProtectData if cifrar else crypt32.CryptUnprotectData
    # 0x01 = CRYPTPROTECT_UI_FORBIDDEN: nunca abrir un diálogo.
    if not funcion(ctypes.byref(entrada), None, None, None, None, 0x01,
                   ctypes.byref(salida)):
        raise OSError("DPAPI falló")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def proteger(texto):
    """Devuelve el texto listo para guardar. Vacío queda vacío. Si no
    se puede cifrar, devuelve el texto tal cual. Nunca lanza."""
    texto = "" if texto is None else str(texto)
    if not texto or not _ES_WINDOWS:
        return texto
    try:
        cifrado = _dpapi(texto.encode("utf-8"), True)
        return PREFIJO + base64.b64encode(cifrado).decode("ascii")
    except Exception:
        return texto


def desproteger(valor):
    """Inversa de proteger(). Un valor cifrado que no se puede abrir
    (otra PC, otro usuario de Windows) devuelve "": el programa lo
    trata como 'sin dato' y lo vuelve a pedir. Nunca lanza."""
    valor = "" if valor is None else str(valor)
    if not valor.startswith(PREFIJO):
        return valor
    try:
        crudo = base64.b64decode(valor[len(PREFIJO):])
        return _dpapi(crudo, False).decode("utf-8")
    except Exception:
        return ""


def esta_protegido(valor):
    return isinstance(valor, str) and valor.startswith(PREFIJO)
