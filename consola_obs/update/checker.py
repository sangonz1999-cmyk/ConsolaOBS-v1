"""Comprobador + descargador de actualizaciones (Fases 2 y 3).

Consulta la API pública de GitHub (sin cuenta ni key), compara la
versión instalada (version.py) con el último tag y, si hay una más
nueva, descarga el asset ConsolaOBS-Consola.zip a %TEMP% (nunca sobre
la instalación: si la descarga falla, lo actual sigue intacto).

Sólo stdlib (urllib): funciona en el .exe sin dependencias nuevas.
Ninguna función lanza hacia la UI: devuelven (dato, error).
"""
import json
import os
import urllib.error
import urllib.request

from consola_obs.update import version as mod_version

REPO = "sangonz1999-cmyk/ConsolaOBS-v1"
URL_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
NOMBRE_ASSET_CONSOLA = "ConsolaOBS-Consola.zip"
TIMEOUT_API_SEG = 15
CHUNK = 1024 * 256


class ErrorUpdate(Exception):
    pass


def _tupla(ver):
    """'v1.1.3' -> (1, 1, 3). Acepta con/sin 'v' y distinto largo."""
    try:
        partes = str(ver or "").strip().lstrip("vV").split(".")
        return tuple(int(p) for p in partes if p != "")
    except Exception:
        return ()


def comparar(instalada, remota):
    """-1 si remota es más nueva, 0 si iguales, 1 si instalada es más
    nueva. Pura y testeable. Nunca lanza."""
    try:
        a, b = _tupla(instalada), _tupla(remota)
        if not a or not b:
            return 0
        n = max(len(a), len(b))
        a += (0,) * (n - len(a))
        b += (0,) * (n - len(b))
        if b > a:
            return -1
        if b < a:
            return 1
        return 0
    except Exception:
        return 0


def _parse_release(datos):
    """Extrae {version, zip_url, tamano, notas} del JSON de
    /releases/latest. Pura y testeable. Lanza ErrorUpdate si falta algo."""
    try:
        tag = str((datos or {}).get("tag_name") or "")
        version = tag.lstrip("vV")
        if not _tupla(version):
            raise ErrorUpdate(f"Tag inválido en GitHub: {tag!r}")
        zip_url, tamano = "", 0
        for asset in (datos or {}).get("assets") or []:
            try:
                if str(asset.get("name") or "") == NOMBRE_ASSET_CONSOLA:
                    zip_url = str(asset.get("browser_download_url") or "")
                    tamano = int(asset.get("size") or 0)
                    break
            except Exception:
                continue
        if not zip_url:
            raise ErrorUpdate(f"La release {tag} no trae {NOMBRE_ASSET_CONSOLA}.")
        return {"version": version, "tag": tag, "zip_url": zip_url,
                "tamano": tamano, "notas": str((datos or {}).get("body") or "")}
    except ErrorUpdate:
        raise
    except Exception as e:
        raise ErrorUpdate(f"Respuesta inesperada de GitHub: {e}")


def ultima_release(timeout=TIMEOUT_API_SEG):
    """(info|None, error|None): info como la de _parse_release."""
    try:
        req = urllib.request.Request(URL_LATEST, headers={"User-Agent": "ConsolaOBS-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            datos = json.loads(resp.read().decode("utf-8"))
        return _parse_release(datos), None
    except urllib.error.HTTPError as e:
        if getattr(e, "code", None) == 404:
            return None, "Todavía no hay releases publicadas en GitHub."
        return None, f"GitHub respondió HTTP {getattr(e, 'code', '?')}."
    except Exception:
        return None, ("Sin conexión con GitHub (revisá Internet). "
                      "El programa sigue funcionando igual.")


def hay_actualizacion():
    """(info|None, error|None): info sólo si la release es más nueva
    que la instalada."""
    info, error = ultima_release()
    if error or not info:
        return None, error
    try:
        if comparar(mod_version.VERSION, info["version"]) == -1:
            return info, None
        return None, None  # iguales (o instalada más nueva: dev)
    except Exception as e:
        return None, str(e)


def carpeta_descarga():
    """%TEMP%\\ConsolaOBS\\update (se crea sola)."""
    try:
        import tempfile
        ruta = os.path.join(tempfile.gettempdir(), "ConsolaOBS", "update")
        os.makedirs(ruta, exist_ok=True)
        return ruta
    except Exception:
        return os.path.abspath(".")


def descargar(url, destino, progreso=None, timeout=60):
    """Baja la URL a 'destino' (.part + replace atómico). progreso =
    f(bajados, total). Devuelve (ruta|None, error|None)."""
    tmp = destino + ".part"
    try:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        req = urllib.request.Request(url, headers={"User-Agent": "ConsolaOBS-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except Exception:
                total = 0
            bajados = 0
            with open(tmp, "wb") as f:
                while True:
                    bloque = resp.read(CHUNK)
                    if not bloque:
                        break
                    f.write(bloque)
                    bajados += len(bloque)
                    try:
                        if progreso:
                            progreso(bajados, total)
                    except Exception:
                        pass
        os.replace(tmp, destino)
        return destino, None
    except Exception as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return None, f"No se pudo descargar: {e} (tu instalación no se tocó)."
