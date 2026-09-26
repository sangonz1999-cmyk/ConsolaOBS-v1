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


def listar_local(raiz):
    """{relpath: {size, mtime, sha256}} de la carpeta local. Reusa el
    listado del servidor (misma regla: sin .tmp/.part)."""
    return {d["name"]: {"size": d["size"], "mtime": d["mtime"], "sha256": d["sha256"]}
            for d in srv.listar_archivos(raiz)}


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


def comparar(local, remoto, previo):
    """Arma el plan. Puro y testeable (sin red ni disco).
    Devuelve dict con listas de nombres: subir, bajar, borrar_local,
    borrar_remoto y conflictos=[(nombre, ganador)] donde ganador es
    'local' o 'remoto'."""
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
            if float(a.get("mtime", 0)) >= float(b.get("mtime", 0)):
                plan["subir"].append(nombre)
                plan["conflictos"].append((nombre, "local"))
            else:
                plan["bajar"].append(nombre)
                plan["conflictos"].append((nombre, "remoto"))
    return plan


def _rel_a_fs(raiz, nombre):
    return os.path.join(os.path.abspath(raiz), *(nombre.replace("\\", "/").split("/")))


def sincronizar(config=None, log=None):
    """Sync completo. Devuelve (ok, resumen). Nunca lanza."""
    resumen = {"subidos": 0, "bajados": 0, "borrados_local": 0,
               "borrados_remoto": 0, "conflictos": [], "errores": []}

    def _log(msg):
        try:
            if log:
                log(msg)
            else:
                print(msg, flush=True)
        except Exception:
            pass

    try:
        config = dict(config or cfg_sync.cargar())
        raiz = config.get("carpeta_local") or ""
        ip = (config.get("ip_remota") or "").strip()
        puerto = int(config.get("puerto") or cfg_sync.PUERTO_POR_DEFECTO)
        key = cfg_sync.obtener_api_key(config)
        if not ip:
            return False, {**resumen, "errores": ["Falta la IP remota (Ajustes → Sincronización)."]}
        if not os.path.isdir(raiz):
            return False, {**resumen, "errores": [f"No existe la carpeta local: {raiz}"]}

        cli = Cliente(ip, puerto, key)
        try:
            cli.ping()
        except ErrorSync as e:
            return False, {**resumen, "errores": [
                f"La otra PC no responde en {ip}:{puerto}: {e}. "
                "Revisá que esté prendida, el programa abierto y el firewall."]}
        _log(f"Sync: conectado con {ip}:{puerto}.")

        local = listar_local(raiz)
        remoto = cli.lista_remota()
        previo = cfg_sync.cargar_ultimo_indice()
        plan = comparar(local, remoto, previo)
        _log(f"Sync: {len(local)} locales, {len(remoto)} remotos. "
             f"Plan: {len(plan['subir'])} subir, {len(plan['bajar'])} bajar, "
             f"{len(plan['borrar_local'])} borrar acá, {len(plan['borrar_remoto'])} borrar allá, "
             f"{len(plan['conflictos'])} conflictos.")

        for nombre in plan["subir"]:
            try:
                info = local[nombre]
                cli.subir(_rel_a_fs(raiz, nombre), nombre, info["mtime"])
                resumen["subidos"] += 1
                _log(f"Sync: subido {nombre}")
            except Exception as e:
                resumen["errores"].append(f"Subir {nombre}: {e}")
        for nombre in plan["bajar"]:
            try:
                cli.descargar(nombre, _rel_a_fs(raiz, nombre))
                resumen["bajados"] += 1
                _log(f"Sync: bajado {nombre}")
            except Exception as e:
                resumen["errores"].append(f"Bajar {nombre}: {e}")
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
                resumen["errores"].append(f"Borrar remoto {nombre}: {e}")
        resumen["conflictos"] = plan["conflictos"]
        for nombre, ganador in plan["conflictos"]:
            _log(f"Sync: conflicto en {nombre} (distinto contenido): "
                 f"gana el más nuevo ({'esta PC' if ganador == 'local' else 'la otra PC'}).")

        # Snapshot post-sync: lo que quedó de cada lado tras aplicar el plan.
        try:
            final = listar_local(raiz)
            cfg_sync.guardar_ultimo_indice(final)
        except Exception as e:
            resumen["errores"].append(f"Guardar índice: {e}")

        ok = not resumen["errores"]
        _log(f"Sync: listo. Subidos {resumen['subidos']}, bajados {resumen['bajados']}, "
             f"borrados acá {resumen['borrados_local']}, borrados allá {resumen['borrados_remoto']}"
             + (f", ERRORES: {len(resumen['errores'])}" if resumen["errores"] else "."))
        return ok, resumen
    except Exception as e:
        resumen["errores"].append(str(e))
        try:
            _log(f"Sync: falló: {e}")
        except Exception:
            pass
        return False, resumen
