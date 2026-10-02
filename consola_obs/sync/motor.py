"""Cliente/motor del sync bidireccional (corre al presionar Sincronizar).

Compara carpeta LOCAL vs REMOTA (la otra PC) por nombre + tamaño +
mtime + sha256 y:
  - copia lo faltante en ambas direcciones (nuevo acá -> sube,
    nuevo allá -> baja),
  - propaga borrados (si estaba en el último índice y falta de un
    lado, se borra del otro),
  - resuelve conflictos por fecha (mismo nombre, distinto contenido:
    gana el mtime más nuevo).

El último índice (ultimo_indice.json) distingue 'nuevo' de 'borrado'.
Cliente HTTP con stdlib (urllib): sin dependencias extra. Nunca lanza
hacia la UI: devuelve (ok, resumen) y loguea cada paso.
"""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from consola_obs.sync import configuracion as cfg_sync
from consola_obs.sync import servidor as srv

CHUNK = 1024 * 1024
TOL_MTIME_SEG = 2.0  # mtimes que difieren menos que esto se consideran iguales


class ErrorSync(Exception):
    pass


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            bloque = f.read(CHUNK)
            if not bloque:
                break
            h.update(bloque)
    return h.hexdigest()


def listar_local(raiz, omitidos=None):
    """{relpath: {size, mtime, sha256}} de la carpeta local. Reusa el
    listado del servidor (misma regla: sin .tmp/.part). Si se pasa lista
    `omitidos`, trae los ilegibles para avisar."""
    return {d["name"]: {"size": d["size"], "mtime": d["mtime"], "sha256": d["sha256"]}
            for d in srv.listar_archivos(raiz, omitidos)}


class Cliente:
    """HTTP mínimo contra la otra PC (header X-API-Key en todo)."""

    def __init__(self, ip, puerto, api_key, timeout=15):
        self.base = f"http://{ip}:{int(puerto)}"
        self.key = api_key or ""
        self.timeout = timeout

    def _pedir(self, metodo, ruta, query=None, cuerpo=None, headers=None, timeout=None):
        url = self.base + ruta
        if query:
            url += "?" + urllib.parse.urlencode(query)
        h = {"X-API-Key": self.key}
        h.update(headers or {})
        req = urllib.request.Request(url, data=cuerpo, headers=h, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout if timeout is None else timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            raise ErrorSync(f"HTTP {e.code} en {metodo} {ruta}: {e.reason}")
        except Exception as e:
            raise ErrorSync(f"No se pudo hablar con {self.base} ({metodo} {ruta}): {e}")

    def ping(self):
        estado, _h, cuerpo = self._pedir("GET", "/ping")
        return json.loads(cuerpo.decode("utf-8")).get("ok") is True

    def info(self):
        """{"root":..., "archivos":...} del otro lado (None si su versión
        no lo trae). Nunca lanza nada útil: devuelve None si falla."""
        try:
            _e, _h, cuerpo = self._pedir("GET", "/info")
            datos = json.loads(cuerpo.decode("utf-8"))
            if isinstance(datos, dict):
                return datos
            return None
        except Exception:
            return None

    def lista_remota(self):
        _e, _h, cuerpo = self._pedir("GET", "/files")
        datos = json.loads(cuerpo.decode("utf-8"))
        return {d["name"]: {"size": d["size"], "mtime": d["mtime"], "sha256": d["sha256"]}
                for d in datos}

    def descargar(self, nombre, destino_local, timeout=120):
        _e, headers, cuerpo = self._pedir(
            "GET", "/download", {"name": nombre}, timeout=timeout)
        os.makedirs(os.path.dirname(destino_local), exist_ok=True)
        tmp = destino_local + ".part"
        with open(tmp, "wb") as f:
            f.write(cuerpo)
        try:
            mtime = float(headers.get("X-Mtime") or headers.get("x-mtime") or 0)
        except Exception:
            mtime = 0.0
        if mtime > 0:
            os.utime(tmp, (mtime, mtime))
        os.replace(tmp, destino_local)

    def subir(self, ruta_local, nombre, mtime, timeout=120):
        # timeout largo: la música puede pesar cientos de MB.
        with open(ruta_local, "rb") as f:
            cuerpo = f.read()
        self._pedir("POST", "/upload", {"name": nombre}, cuerpo,
                    {"Content-Type": "application/octet-stream",
                     "X-Mtime": str(float(mtime))}, timeout=timeout)

    def borrar(self, nombre):
        try:
            self._pedir("DELETE", "/file", {"name": nombre})
        except ErrorSync as e:
            if "HTTP 404" not in str(e):
                raise


# Alcance del sync: SÓLO contenido (sonidos, imágenes de pads y
# música). Los archivos del programa (iconos, fuentes, fondos, LEEMEs)
# no se tocan nunca: ni se suben ni se borran, existan o no del otro
# lado. Así un índice viejo o una PC con otros archivos jamás puede
# borrar lo del programa.
ALCANCE_SYNC = ("Sondidos_pad/", "Imagenes_pad/", "Musica/")


def _en_alcance(nombre):
    try:
        return any((nombre or "").startswith(p) for p in ALCANCE_SYNC)
    except Exception:
        return False


def comparar(local, remoto, previo):
    """Arma el plan. Puro y testeable (sin red ni disco).
    Devuelve dict con listas de nombres: subir, bajar, borrar_local,
    borrar_remoto y conflictos=[(nombre, ganador)].
    En conflicto gana SIEMPRE lo local: la PC que ejecuta manda."""
    plan = {"subir": [], "bajar": [], "borrar_local": [],
            "borrar_remoto": [], "conflictos": []}
    for nombre in sorted(set(local) | set(remoto)):
        en_l, en_r = nombre in local, nombre in remoto
        en_p = nombre in (previo or {})
        if en_l and not en_r:
            # ¿Lo borraron allá o es nuevo acá?
            if en_p:
                plan["borrar_local"].append(nombre)   # borrado remoto -> se propaga
            else:
                plan["subir"].append(nombre)          # nuevo local -> se sube
        elif en_r and not en_l:
            if en_p:
                plan["borrar_remoto"].append(nombre)  # borrado local -> se propaga
            else:
                plan["bajar"].append(nombre)          # nuevo remoto -> se baja
        else:
            a, b = local[nombre], remoto[nombre]
            if a["sha256"] == b["sha256"]:
                continue
            if abs(float(a.get("mtime", 0)) - float(b.get("mtime", 0))) <= TOL_MTIME_SEG \
                    and int(a.get("size", -1)) == int(b.get("size", -2)):
                continue  # mismo contenido efectivo (redondeo de mtime)
            plan["subir"].append(nombre)
            plan["conflictos"].append((nombre, "local"))
    return plan


def _rel_a_fs(raiz, nombre):
    return os.path.join(os.path.abspath(raiz), *(nombre.replace("\\", "/").split("/")))


def _hacer_log(log):
    def _log(msg):
        try:
            if log:
                log(msg)
            else:
                print(msg, flush=True)
        except Exception:
            pass
    return _log


def _validar_config(config):
    """Devuelve (raiz, ip, puerto, key) o lanza ErrorSync."""
    config = dict(config or cfg_sync.cargar())
    raiz = config.get("carpeta_local") or ""
    ip = (config.get("ip_remota") or "").strip()
    puerto = int(config.get("puerto") or cfg_sync.PUERTO_POR_DEFECTO)
    key = cfg_sync.obtener_api_key(config)
    if not ip:
        raise ErrorSync("Falta la IP remota (Ajustes → Sincronización).")
    try:
        from consola_obs import red as mod_red
        propias = set(mod_red.obtener_todas_ips_locales())
    except Exception:
        propias = set()
    # OJO: loopback explícito (127.0.0.1/localhost) se permite: es la
    # forma deliberada de probar en una sola PC. Lo que se bloquea es la
    # IP LAN propia (el footgun real: creés hablar con la otra PC).
    if ip in propias:
        raise ErrorSync(
            f"Esa IP ({ip}) es ESTA misma PC: sincronizar con uno mismo "
            "siempre da 0 cambios. Poné la IP de LA OTRA PC "
            "(en ella: hostname -I en Linux o ipconfig en Windows).")
    if not os.path.isdir(raiz):
        raise ErrorSync(f"No existe la carpeta local: {raiz}")
    return raiz, ip, puerto, key


def _ayuda_fallo_ping(e, puerto):
    detalle = str(e)
    baja = detalle.lower()
    if ("10061" in detalle or "actively refused" in baja
            or ("deneg" in baja and "expresamente" in baja)):
        return ("Conexión RECHAZADA: la PC existe pero ahí no hay ningún "
                "servidor de sync escuchando. Prendé el programa en la otra "
                "PC (o `python3 sync_server_mini.py --dir assets --port "
                f"{puerto}`) y que el puerto coincida en ambas.")
    if ("10060" in detalle or "timed out" in baja
            or "tiempo de espera" in baja):
        return ("Sin respuesta (timeout): suele ser firewall o red. Misma "
                "WiFi, `sudo ufw allow "
                f"{puerto}/tcp` en la otra PC, y probá hacerle ping.")
    return "Revisá que esté prendida, el programa abierto y el firewall."


def planificar(config=None, log=None):
    """Arma el plan SIN tocar nada. Devuelve (plan, ctx); lanza
    ErrorSync si no se puede (config, red). ctx trae lo necesario para
    ejecutar()."""
    _log = _hacer_log(log)
    raiz, ip, puerto, key = _validar_config(config)
    cli = Cliente(ip, puerto, key)
    try:
        cli.ping()
    except ErrorSync as e:
        raise ErrorSync(
            f"La otra PC no responde en {ip}:{puerto}: {e}. "
            f"{_ayuda_fallo_ping(e, puerto)}")
    _log(f"Sync: conectado con {ip}:{puerto}.")
    _log(f"Sync: raíz local {raiz}.")
    _log("Sync: alcance Sondidos_pad + Imagenes_pad + Musica "
         "(lo demás no se toca).")

    omitidos = []
    local = {n: v for n, v in listar_local(raiz, omitidos).items()
             if _en_alcance(n)}
    for rel in omitidos:
        _log(f"Sync: no se pudo leer {rel} (bloqueado o sin permiso): "
             "no entra al sync hasta poder leerse.")
    try:
        info_remota = cli.info()
        if info_remota:
            _log(f"Sync: raíz remota {info_remota.get('root', '?')} "
                 f"({info_remota.get('archivos', '?')} archivos).")
    except Exception:
        info_remota = None
    try:
        raiz_remota = ((info_remota or {}).get("root") or "").strip()
    except Exception:
        raiz_remota = ""
    remoto = {n: v for n, v in cli.lista_remota().items()
              if _en_alcance(n)}
    previo = cfg_sync.cargar_ultimo_indice()
    plan = comparar(local, remoto, previo)
    _log(f"Sync: {len(local)} locales, {len(remoto)} remotos. "
         f"Plan: {len(plan['subir'])} subir, {len(plan['bajar'])} bajar, "
         f"{len(plan['borrar_local'])} borrar acá, {len(plan['borrar_remoto'])} borrar allá, "
         f"{len(plan['conflictos'])} conflictos.")

    def _nombres(lista, titulo):
        try:
            if not lista:
                return
            muestra = ", ".join(lista[:15])
            extra = f" (+{len(lista) - 15} más)" if len(lista) > 15 else ""
            _log(f"Sync: {titulo}: {muestra}{extra}")
        except Exception:
            pass
    _nombres(plan["subir"], "a subir")
    _nombres(plan["bajar"], "a bajar")
    _nombres(plan["borrar_local"], "a borrar acá")
    _nombres(plan["borrar_remoto"], "a borrar allá")
    ctx = {"raiz": raiz, "cli": cli, "local": local, "previo": previo,
           "raiz_remota": raiz_remota,
           "resumen": {"subidos": 0, "bajados": 0, "borrados_local": 0,
                       "borrados_remoto": 0, "conflictos": [], "errores": []}}
    return plan, ctx


def ejecutar(plan, ctx, incluir_borrados=True, log=None):
    """Aplica el plan de planificar(). Con incluir_borrados=False sólo
    copia lo nuevo (no borra nada de ningún lado). Devuelve (ok, resumen).
    Nunca lanza."""
    _log = _hacer_log(log)
    raiz, cli = ctx["raiz"], ctx["cli"]
    local, previo = ctx["local"], ctx["previo"]
    resumen = ctx["resumen"]
    # Fallos por operación: el índice final sólo refleja lo que quedó
    # CONFIRMADO en ambos lados. Un fallo NO se marca como hecho:
    # si no, una subida fallida haría que el próximo sync tome el
    # archivo nuevo por "borrado del otro lado" y lo borre acá.
    fallidos_subir = set()
    fallidos_borrar_remoto = set()
    for nombre in plan["subir"]:
        try:
            info = local[nombre]
            cli.subir(_rel_a_fs(raiz, nombre), nombre, info["mtime"])
            resumen["subidos"] += 1
            _log(f"Sync: subido {nombre}")
        except Exception as e:
            fallidos_subir.add(nombre)
            resumen["errores"].append(f"Subir {nombre}: {e}")
    for nombre in plan["bajar"]:
        try:
            cli.descargar(nombre, _rel_a_fs(raiz, nombre))
            resumen["bajados"] += 1
            _log(f"Sync: bajado {nombre}")
        except Exception as e:
            resumen["errores"].append(f"Bajar {nombre}: {e}")
    if incluir_borrados:
        for nombre in plan["borrar_local"]:
            try:
                ruta = _rel_a_fs(raiz, nombre)
                if os.path.isfile(ruta):
                    os.remove(ruta)
                resumen["borrados_local"] += 1
                _log(f"Sync: borrado acá (lo borraron allá) {nombre}")
            except Exception as e:
                resumen["errores"].append(f"Borrar local {nombre}: {e}")
        for nombre in plan["borrar_remoto"]:
            try:
                cli.borrar(nombre)
                resumen["borrados_remoto"] += 1
                _log(f"Sync: borrado allá (lo borraste acá) {nombre}")
            except Exception as e:
                fallidos_borrar_remoto.add(nombre)
                resumen["errores"].append(f"Borrar remoto {nombre}: {e}")
    else:
        n = len(plan["borrar_local"]) + len(plan["borrar_remoto"])
        if n:
            _log(f"Sync: se saltean {n} borrados (sólo copiar).")
    resumen["conflictos"] = plan["conflictos"]
    for nombre, ganador in plan["conflictos"]:
        _log(f"Sync: conflicto en {nombre} (distinto contenido): gana esta PC.")
    # Snapshot post-sync: lo listado ahora (sólo alcance), MENOS lo que
    # falló al subir (se reintenta como nuevo) MÁS lo que falló al borrar
    # allá (sigue allá: se reintenta el borrado).
    try:
        final = {n: v for n, v in listar_local(raiz).items() if _en_alcance(n)}
        for nombre in fallidos_subir:
            final.pop(nombre, None)
        for nombre in fallidos_borrar_remoto:
            if nombre in previo:
                final[nombre] = previo[nombre]
        cfg_sync.guardar_ultimo_indice(final)
    except Exception as e:
        resumen["errores"].append(f"Guardar índice: {e}")
    ok = not resumen["errores"]
    _log(f"Sync: listo. Subidos {resumen['subidos']}, bajados {resumen['bajados']}, "
         f"borrados acá {resumen['borrados_local']}, borrados allá {resumen['borrados_remoto']}"
         + (f", ERRORES: {len(resumen['errores'])}" if resumen["errores"] else "."))
    # Ruta automática: la otra PC ya dijo dónde sirve sus assets (/info
    # -> root): se adopta como Carpeta OBS para que el enrutamiento
    # salga solo, sin escribir rutas a mano (vale para .exe, .py, mini
    # y cualquier sistema). Sólo si el sync salió limpio.
    if ok:
        try:
            from consola_obs.audio import rutas_obs as mod_rutas_obs
            raiz_remota = (ctx or {}).get("raiz_remota") or ""
            if raiz_remota and mod_rutas_obs.adoptar_base_desde_sync(raiz_remota):
                _log(f"Sync: Carpeta OBS detectada sola: {raiz_remota.strip()} "
                     "(el OBS buscará los sonidos ahí).")
        except Exception:
            pass
    return ok, resumen


def sincronizar(config=None, log=None):
    """Sync completo (plan + ejecución con borrados). Devuelve (ok,
    resumen). Nunca lanza. Lo usa la UI tras confirmar borrados, y los
    tests."""
    resumen_vacio = {"subidos": 0, "bajados": 0, "borrados_local": 0,
                     "borrados_remoto": 0, "conflictos": [], "errores": []}
    _log = _hacer_log(log)
    try:
        plan, ctx = planificar(config, log)
    except ErrorSync as e:
        return False, {**resumen_vacio, "errores": [str(e)]}
    except Exception as e:
        _log(f"Sync: falló: {e}")
        return False, {**resumen_vacio, "errores": [str(e)]}
    try:
        return ejecutar(plan, ctx, incluir_borrados=True, log=log)
    except Exception as e:
        try:
            _log(f"Sync: falló: {e}")
        except Exception:
            pass
        return False, {**resumen_vacio, "errores": [str(e)]}
