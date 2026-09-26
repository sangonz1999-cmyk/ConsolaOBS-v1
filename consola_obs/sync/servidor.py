"""Servidor de sync (corre en AMBAS PCs, una instancia por PC).

Expone la carpeta local de assets por HTTP para la otra PC:
  GET  /ping                -> {"ok": true} (con API key, diagnóstico)
  GET  /files               -> [{name, size, mtime, sha256}]
  GET  /download?name=...   -> bytes del archivo (+ header X-Mtime)
  POST /upload?name=...     -> guarda el body (+ header X-Mtime)
  DELETE /file?name=...     -> borra el archivo

Todo (salvo nada) exige header X-API-Key igual a la key local: sólo
tus 2 PCs pueden pedir/subir/borrar. Los nombres son rutas relativas
a la raíz sincronizada; se rechaza cualquier intento de salir de la
raíz (.. o ruta absoluta). Se corre en hilo daemon al iniciar el
programa (ver iniciar_en_hilo).
"""
import hashlib
import os
import threading

CHUNK = 1024 * 1024


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
    """Resuelve 'nombre' dentro de 'raiz' o devuelve None si intenta
    escapar (.., absoluta, etc.). Nunca lanza."""
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


def listar_archivos(raiz):
    """[{name, size, mtime, sha256}] recursivo bajo raíz, con rutas
    relativas en formato con /. Pura (testeable sin FastAPI)."""
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
                items.append({
                    "name": rel,
                    "size": int(st.st_size),
                    "mtime": float(st.st_mtime),
                    "sha256": _sha256(ruta),
                })
            except Exception:
                continue
    items.sort(key=lambda d: d["name"])
    return items


def crear_app(raiz, api_key):
    """Arma la app FastAPI. Import diferido: si FastAPI no está
    instalado, lanza ImportError (el llamador lo maneja)."""
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI(title="ConsolaOBS Sync")

    def _autorizar(key):
        if not api_key or (key or "") != api_key:
            raise HTTPException(status_code=401, detail="API key inválida")

    @app.get("/ping")
    def ping(x_api_key: str = Header(default="", alias="X-API-Key")):
        _autorizar(x_api_key)
        return {"ok": True}

    @app.get("/files")
    def files(x_api_key: str = Header(default="", alias="X-API-Key")):
        _autorizar(x_api_key)
        return listar_archivos(raiz)

    @app.get("/download")
    def download(name: str = "", x_api_key: str = Header(default="", alias="X-API-Key")):
        _autorizar(x_api_key)
        destino = _ruta_segura(raiz, name)
        if not destino or not os.path.isfile(destino):
            raise HTTPException(status_code=404, detail="No existe")
        try:
            mtime = os.stat(destino).st_mtime
        except Exception:
            mtime = 0.0
        return FileResponse(destino, headers={"X-Mtime": str(mtime)})

    @app.post("/upload")
    async def upload(request: Request, name: str = "",
                     x_api_key: str = Header(default="", alias="X-API-Key"),
                     x_mtime: str = Header(default="", alias="X-Mtime")):
        _autorizar(x_api_key)
        destino = _ruta_segura(raiz, name)
        if not destino:
            raise HTTPException(status_code=400, detail="Nombre inválido")
        try:
            cuerpo = await request.body()
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            tmp = destino + ".part"
            with open(tmp, "wb") as f:
                f.write(cuerpo)
            try:
                mtime = float(x_mtime) if x_mtime else 0.0
            except Exception:
                mtime = 0.0
            if mtime > 0:
                os.utime(tmp, (mtime, mtime))
            os.replace(tmp, destino)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"ok": True, "name": name}

    @app.delete("/file")
    def borrar(name: str = "", x_api_key: str = Header(default="", alias="X-API-Key")):
        _autorizar(x_api_key)
        destino = _ruta_segura(raiz, name)
        if not destino or not os.path.isfile(destino):
            raise HTTPException(status_code=404, detail="No existe")
        try:
            os.remove(destino)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"ok": True, "name": name}

    @app.exception_handler(404)
    async def _not_found(_request, _exc):
        return JSONResponse(status_code=404, content={"detail": "No existe"})

    return app


_estado = {"en_marcha": False, "puerto": None}


def iniciar_en_hilo(raiz, puerto, api_key, log=None):
    """Levanta uvicorn en un hilo daemon (no frena el arranque ni el
    cierre). Devuelve True si quedó escuchando. Nunca lanza."""
    def _log(msg):
        try:
            if log:
                log(msg)
            else:
                print(msg, flush=True)
        except Exception:
            pass

    if _estado.get("en_marcha"):
        return True
    try:
        import uvicorn  # noqa: F401
        import fastapi  # noqa: F401
    except Exception:
        _log("Sync: falta fastapi/uvicorn (pip install -r requirements.txt); "
             "el servidor local no se inicia, pero Sincronizar igual puede pedir a la otra PC.")
        return False

    def _correr():
        try:
            import uvicorn
            app = crear_app(raiz, api_key)
            _estado["en_marcha"] = True
            _estado["puerto"] = puerto
            _log(f"Sync: servidor escuchando en puerto {puerto}.")
            uvicorn.run(app, host="0.0.0.0", port=int(puerto),
                        loop="asyncio", http="h11", log_level="warning")
        except Exception as e:
            _estado["en_marcha"] = False
            _log(f"Sync: no se pudo levantar el servidor (puerto {puerto}): {e}")
        finally:
            _estado["en_marcha"] = False

    try:
        hilo = threading.Thread(target=_correr, daemon=True)
        hilo.start()
        return True
    except Exception as e:
        _log(f"Sync: no se pudo iniciar el hilo del servidor: {e}")
        return False
