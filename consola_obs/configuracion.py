import json
import os
import time

from consola_obs import estado as E
from consola_obs import rutas as R
from consola_obs import secretos


# ------------------------------------------------------------------
# Lectura y escritura seguras de JSON
# ------------------------------------------------------------------
def escribir_json_atomico(ruta, datos, indent=2):
    """Escribe a un archivo temporal y lo renombra encima del real: si
    el programa se cierra o se corta la luz a mitad de la escritura, el
    archivo viejo queda intacto en vez de quedar truncado. Con
    reintentos, porque en Windows el reemplazo puede chocar un instante
    con el antivirus o con Google Drive (WinError 5 / Errno 13).
    Devuelve True si quedó guardado. Nunca lanza."""
    ruta_tmp = ruta + ".tmp"
    ultimo_error = None
    for intento in range(6):
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta_tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=indent)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(ruta_tmp, ruta)
            return True
        except Exception as e:
            ultimo_error = e
            time.sleep(0.05 * (2 ** intento))
    print(f"No se pudo guardar {os.path.basename(ruta)}: {ultimo_error}")
    return False


def leer_json(ruta):
    """Devuelve (estado, datos). estado es "ok", "no_existe" o "error".
    Distinguir "error" de "no_existe" importa: ante un error de lectura
    pasajero NO hay que tratar el archivo como vacío y pisarlo."""
    if not os.path.exists(ruta):
        return "no_existe", None
    ultimo_error = None
    for intento in range(4):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return "ok", json.load(f)
        except Exception as e:
            ultimo_error = e
            time.sleep(0.05 * (2 ** intento))
    print(f"No se pudo leer {os.path.basename(ruta)}: {ultimo_error}")
    return "error", None


# ------------------------------------------------------------------
# Conexión
# ------------------------------------------------------------------
def cargar_config_conexion():
    estado, datos = leer_json(R.ARCHIVO_CONEXION)
    if estado == "ok" and isinstance(datos, dict):
        # La contraseña se guarda cifrada (ver secretos.py); las
        # configuraciones viejas en texto plano se siguen leyendo.
        datos["password"] = secretos.desproteger(datos.get("password") or "")
        return datos
    return {"host": "localhost", "puerto": "4455", "password": ""}


def hay_config_conexion_guardada():
    """¿Existe un host/puerto guardados de una conexión anterior? Si no hay
    archivo (o está vacío/viene con los valores por defecto sin host), no
    hay nada con qué reconectar y conviene abrir Ajustes en vez de
    intentar adivinar."""
    if not os.path.exists(R.ARCHIVO_CONEXION):
        return False
    datos = cargar_config_conexion()
    if not isinstance(datos, dict):
        return False
    return bool(str(datos.get("host") or "").strip())


def guardar_config_conexion(host, puerto, password):
    escribir_json_atomico(R.ARCHIVO_CONEXION, {
        "host": host, "puerto": str(puerto),
        "password": secretos.proteger(password or ""),
    }, indent=None)


# ------------------------------------------------------------------
# Soundboard
# ------------------------------------------------------------------
# Las rutas de los pads se guardan RELATIVAS a la carpeta del programa
# (antes eran absolutas: al mover o copiar el programa a otra carpeta u
# otra PC, todos los pads apuntaban a archivos que ya no existían). En
# memoria siguen siendo absolutas, así el resto del código no cambia.
_CAMPOS_RUTA_PAD = ("archivo", "imagen", "nivel_archivo")


def _ruta_a_relativa(ruta):
    try:
        if not ruta or not isinstance(ruta, str) or not os.path.isabs(ruta):
            return ruta
        relativa = os.path.relpath(ruta, R.CARPETA_SCRIPT)
        if relativa.startswith(".."):
            return ruta  # está fuera de la carpeta del programa
        return relativa.replace(os.sep, "/")
    except Exception:
        return ruta


def _ruta_a_absoluta(ruta):
    try:
        if not ruta or not isinstance(ruta, str):
            return ruta
        if not os.path.isabs(ruta):
            return os.path.normpath(os.path.join(R.CARPETA_SCRIPT, ruta))
        if os.path.exists(ruta):
            return ruta
        # Ruta absoluta vieja de otra instalación: si apuntaba dentro de
        # una carpeta "assets", se busca el mismo archivo en la nuestra.
        partes = ruta.replace(chr(92), "/").split("/")
        indices = [i for i, p in enumerate(partes) if p.lower() == "assets"]
        if indices:
            candidata = os.path.join(R.CARPETA_ASSETS, *partes[indices[-1] + 1:])
            if os.path.exists(candidata):
                return os.path.normpath(candidata)
        return ruta
    except Exception:
        return ruta


def cargar_config_soundboard():
    # OJO: antes esta función cargaba el JSON en una variable local y lo
    # descartaba (los pads asignados se perdían al cerrar el programa).
    # Ahora sí se restaura en E.config_soundboard, validando la forma.
    E.config_soundboard = {}
    estado, datos = leer_json(R.ARCHIVO_SOUNDBOARD)
    E._soundboard_ilegible = (estado == "error")
    if estado == "ok" and isinstance(datos, dict):
        for clave, valor in datos.items():
            if isinstance(valor, dict):
                for campo in _CAMPOS_RUTA_PAD:
                    if valor.get(campo):
                        valor[campo] = _ruta_a_absoluta(valor[campo])
                E.config_soundboard[str(clave)] = valor


def guardar_config_soundboard():
    # Si al arrancar el archivo existía pero no se pudo leer, no se pisa
    # con la config vacía que quedó en memoria.
    if getattr(E, "_soundboard_ilegible", False) and not E.config_soundboard:
        return
    a_guardar = {}
    for clave, valor in E.config_soundboard.items():
        if isinstance(valor, dict):
            valor = dict(valor)
            for campo in _CAMPOS_RUTA_PAD:
                if valor.get(campo):
                    valor[campo] = _ruta_a_relativa(valor[campo])
        a_guardar[clave] = valor
    escribir_json_atomico(R.ARCHIVO_SOUNDBOARD, a_guardar)


# ------------------------------------------------------------------
# Interfaz
# ------------------------------------------------------------------
def cargar_config_interfaz():
    estado, datos = leer_json(R.ARCHIVO_INTERFAZ)
    if estado == "ok" and isinstance(datos, dict):
        return datos
    return {}


def guardar_config_interfaz(datos_nuevos):
    """Actualiza sólo las claves indicadas, conservando el resto de la
    configuración de interfaz ya guardada."""
    estado, actual = leer_json(R.ARCHIVO_INTERFAZ)
    if estado == "error":
        # No se pudo leer lo que hay: guardar ahora borraría todas las
        # demás claves. Se prefiere perder este cambio puntual.
        print("Config de interfaz ilegible: no se guarda para no pisarla.")
        return
    if not isinstance(actual, dict):
        actual = {}
    actual.update(datos_nuevos)
    escribir_json_atomico(R.ARCHIVO_INTERFAZ, actual)


# ------------------------------------------------------------------
# Música
# ------------------------------------------------------------------
def cargar_config_musica():
    """Biblioteca de música: recientes + repetir + playlist actual +
    caché de duraciones. Si no existe o está rota, valores de fábrica."""
    fabrica = {"recientes": [], "repetir": True, "mezclar": False,
               "playlist": [], "duraciones": {}}
    _estado, datos = leer_json(R.ARCHIVO_MUSICA)
    if isinstance(datos, dict):
        fabrica.update(datos)
    if not isinstance(fabrica.get("recientes"), list):
        fabrica["recientes"] = []
    if not isinstance(fabrica.get("repetir"), bool):
        fabrica["repetir"] = True
    if not isinstance(fabrica.get("mezclar"), bool):
        fabrica["mezclar"] = False
    if not isinstance(fabrica.get("playlist"), list):
        fabrica["playlist"] = []
    if not isinstance(fabrica.get("duraciones"), dict):
        fabrica["duraciones"] = {}
    return fabrica


def guardar_config_musica(datos):
    """Escritura atómica con reintentos: el hilo de duraciones y la UI
    escriben este JSON a la vez. Devuelve True si quedó guardado."""
    return escribir_json_atomico(R.ARCHIVO_MUSICA, datos)
