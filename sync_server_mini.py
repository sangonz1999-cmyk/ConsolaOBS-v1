"""Mini servidor de sync para la PC del OBS (stdlib only, sin instalar nada).

Es la contraparte liviana del programa: expone la carpeta de assets por
HTTP con LA MISMA API que el servidor completo, así la consola puede
sincronizar contra esta PC sin que acá corra todo el programa:

  GET  /ping                -> {"ok": true}
  GET  /files               -> [{name, size, mtime, sha256}]
  GET  /download?name=...   -> bytes (+ header X-Mtime)
  POST /upload?name=...     -> guarda el body (+ header X-Mtime)
  DELETE /file?name=...     -> borra

Todo exige header X-API-Key igual a la clave (sólo tus 2 PCs).

Uso (Linux, en la carpeta de los sonidos):
  python3 sync_server_mini.py --dir assets --port 4456
  (la clave sale de CONSOLAOBS_SYNC_KEY, de --key, o de sync.key:
  se genera sola la primera vez y se muestra para copiarla en la consola)

Viaja dentro de ConsolaOBS-OBS.zip: en la PC del OBS no se instala nada
más (ni pip, ni el programa completo).
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CHUNK = 1024 * 1024
RAIZ_SCRIPT = os.path.dirname(os.path.abspath(__file__))


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            bloque = f.read(CHUNK)
            if not bloque:
                break
            h.update(bloque)
    return h.hexdigest()


def _ruta_segura(raiz, nombre):
    try:
        if not nombre or not isinstance(nombre, str):
            return None
        rel = nombre.replace("\\", "/").lstrip("/")
        raiz_abs = os.path.abspath(raiz)
        destino = os.path.abspath(os.path.join(raiz_abs, rel))
        if destino != raiz_abs and not destino.startswith(raiz_abs + os.sep):
            return None
        return destino
    except Exception:
        return None


def _es_temporal(nombre):
    bajo = (nombre or "").lower()
    return bajo.endswith(".tmp") or bajo.endswith(".part")


def listar(raiz):
    items = []
    try:
        raiz_abs = os.path.abspath(raiz)
    except Exception:
        return items
    for dirpath, _dirs, files in os.walk(raiz_abs):
        for fn in files:
            ruta = os.path.join(dirpath, fn)
            try:
                rel = os.path.relpath(ruta, raiz_abs).replace(os.sep, "/")
            except Exception:
                continue
            if _es_temporal(rel):
                continue
            try:
                st = os.stat(ruta)
                items.append({"name": rel, "size": int(st.st_size),
                              "mtime": float(st.st_mtime),
                              "sha256": _sha256(ruta)})
            except Exception:
                continue
    items.sort(key=lambda d: d["name"])
    return items


def resolver_clave(args):
    """CONSOLAOBS_SYNC_KEY -> --key -> sync.key (se genera si falta)."""
    try:
        env = (os.getenv("CONSOLAOBS_SYNC_KEY") or "").strip()
    except Exception:
        env = ""
    if env:
        return env, "entorno"
    if (args.key or "").strip():
        return args.key.strip(), "argumento"
    ruta_key = os.path.join(RAIZ_SCRIPT, "sync.key")
    try:
        if os.path.isfile(ruta_key):
            with open(ruta_key, "r", encoding="utf-8") as f:
                vieja = f.read().strip()
            if vieja:
                return vieja, "sync.key"
    except Exception:
        pass
    nueva = secrets.token_urlsafe(24)
    try:
        with open(ruta_key, "w", encoding="utf-8") as f:
            f.write(nueva)
    except Exception as e:
        print(f"AVISO: no se pudo guardar sync.key ({e}); la clave vale solo por esta sesión.")
    return nueva, "generada"


def crear_handler(raiz, api_key):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "ConsolaOBS-SyncMini/1.0"

        def log_message(self, fmt, *args):
            try:
                print(f"[sync-mini] {self.command} {self.path.split('?')[0]} -> {args[0]}",
                      flush=True)
            except Exception:
                pass

        def _autorizado(self):
            try:
                dada = self.headers.get("X-API-Key") or ""
                return bool(api_key) and hmac.compare_digest(dada, api_key)
            except Exception:
                return False

        def _json(self, codigo, obj, extras=None):
            try:
                cuerpo = json.dumps(obj).encode("utf-8")
            except Exception:
                cuerpo = b"{}"
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            for k, v in (extras or {}).items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(cuerpo)
            except Exception:
                pass

        def _nombre(self):
            try:
                q = parse_qs(urlparse(self.path).query)
                return (q.get("name") or [""])[0]
            except Exception:
                return ""

        def do_GET(self):
            ruta = urlparse(self.path).path
            if not self._autorizado():
                self._json(401, {"detail": "API key inválida"})
                return
            if ruta == "/ping":
                self._json(200, {"ok": True})
            elif ruta == "/files":
                self._json(200, listar(raiz))
            elif ruta == "/download":
                destino = _ruta_segura(raiz, self._nombre())
                if not destino or not os.path.isfile(destino):
                    self._json(404, {"detail": "No existe"})
                    return
                try:
                    mtime = os.stat(destino).st_mtime
                except Exception:
                    mtime = 0.0
                try:
                    with open(destino, "rb") as f:
                        cuerpo = f.read()
                except Exception as e:
                    self._json(500, {"detail": str(e)})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("X-Mtime", str(mtime))
                self.end_headers()
                try:
                    self.wfile.write(cuerpo)
                except Exception:
                    pass
            else:
                self._json(404, {"detail": "No existe"})

        def do_POST(self):
            ruta = urlparse(self.path).path
            if not self._autorizado():
                self._json(401, {"detail": "API key inválida"})
                return
            if ruta != "/upload":
                self._json(404, {"detail": "No existe"})
                return
            destino = _ruta_segura(raiz, self._nombre())
            if not destino:
                self._json(400, {"detail": "Nombre inválido"})
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
            except Exception:
                largo = 0
            try:
                cuerpo = self.rfile.read(largo) if largo > 0 else b""
            except Exception as e:
                self._json(500, {"detail": str(e)})
                return
            try:
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                tmp = destino + ".part"
                with open(tmp, "wb") as f:
                    f.write(cuerpo)
                try:
                    mtime = float(self.headers.get("X-Mtime") or 0)
                except Exception:
                    mtime = 0.0
                if mtime > 0:
                    os.utime(tmp, (mtime, mtime))
                os.replace(tmp, destino)
            except Exception as e:
                self._json(500, {"detail": str(e)})
                return
            self._json(200, {"ok": True})

        def do_DELETE(self):
            ruta = urlparse(self.path).path
            if not self._autorizado():
                self._json(401, {"detail": "API key inválida"})
                return
            if ruta != "/file":
                self._json(404, {"detail": "No existe"})
                return
            destino = _ruta_segura(raiz, self._nombre())
            if not destino or not os.path.isfile(destino):
                self._json(404, {"detail": "No existe"})
                return
            try:
                os.remove(destino)
            except Exception as e:
                self._json(500, {"detail": str(e)})
                return
            self._json(200, {"ok": True})

    return Manejador


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mini servidor de sync (PC del OBS)")
    ap.add_argument("--dir", default="assets")
    ap.add_argument("--port", type=int, default=4456)
    ap.add_argument("--key", default="")
    args = ap.parse_args(argv)

    raiz = args.dir if os.path.isabs(args.dir) else os.path.join(RAIZ_SCRIPT, args.dir)
    if not os.path.isdir(raiz):
        print(f"No existe la carpeta a servir: {raiz}")
        return 1
    api_key, origen = resolver_clave(args)
    print(f"Sirviendo {raiz} en puerto {args.port} (clave: {origen}).")
    if origen in ("generada",):
        print(f"Tu clave es:\n\n{api_key}\n\nPoné LA MISMA en la consola "
              "(Ajustes -> Sincronización).")
    print("Ctrl+C para detener.")
    servidor = ThreadingHTTPServer(("0.0.0.0", int(args.port)),
                                   crear_handler(raiz, api_key))
    servidor.daemon_threads = True
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
