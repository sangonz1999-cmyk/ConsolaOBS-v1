"""Arma los dos ZIP de la Release (stdlib only, doble clic vía armar_release.bat).

  ConsolaOBS-Consola.zip -> carpeta `ConsolaOBS/`: exes + código + assets
      completos (PC del sonidista).
  ConsolaOBS-OBS.zip     -> carpeta `OBS/`: sólo `assets/` con sonidos +
      música (PC del OBS, ahí no se instala nada).

Reglas (iguales a las Releases anteriores):
  - Sin `config/` (cada instalación genera la suya), sin `*.log`,
    sin `*.zip`, sin temporales (`_build_*`, `*.spec`, `__pycache__`,
    `.git/`, `.venv/`).
  - El ZIP de OBS lleva Sondidos_pad + Musica (sin imágenes ni iconos:
    allá sólo hacen falta los audios).
  - Los LEEME.txt de raíz no existen en el repo: se generan acá con la
    versión incluida, igual que antes.
"""
import os
import re
import sys
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
ZIP_CONSOLA = os.path.join(RAIZ, "ConsolaOBS-Consola.zip")
ZIP_OBS = os.path.join(RAIZ, "ConsolaOBS-OBS.zip")

TOP_CONSOLA = [
    "ConsolaOBS.exe",
    "updater.exe",
    "main.py",
    "updater.py",
    "requirements.txt",
    "compilar.bat",
    "armar_release.bat",
    "armar_release.py",
    "instalar.bat",
    "instalar.sh",
    "sincronizar_assets.bat",
    "version_info.txt",
    "updater_version.txt",
    "README.md",
]
IGNORAR_DIRS = {".git", ".venv", "__pycache__", "_build_tmp", "_build_upd_tmp"}
IGNORAR_EXT = (".pyc", ".pyo", ".log", ".zip", ".spec", ".tmp", ".part")
IGNORAR_BASE = {"Thumbs.db", ".DS_Store"}

LEEME_CONSOLA = """CONSOLAOBS - PC DEL SONIDISTA (consola/laptop)
===============================================
Versión incluida: {version}

1. Descomprimí esta carpeta donde quieras (ej: C:\\ConsolaOBS).
2. Abrí ConsolaOBS.exe con doble clic.
3. En OBS (puede estar en otra PC): Herramientas -> WebSocket ->
   habilitar, puerto 4455.
4. En la consola: engranaje -> Conexión -> CONECTAR.

Las versiones nuevas llegan solas con la actualización automática
(engranaje -> Actualización).

Si Windows SmartScreen avisa por ser un .exe sin firma:
Más información -> Ejecutar de todos modos.
"""

LEEME_OBS = """CONSOLAOBS - PC DEL OBS (la principal)
=====================================
Esta carpeta tiene SOLO los sonidos (.mp3 de efectos y música).
Acá no se instala nada: solo OBS + esta carpeta.

REGLA DE ORO: esta carpeta tiene que quedar en la MISMA RUTA que la
carpeta assets de la PC del sonidista (ej: las dos en C:\\ConsolaOBS,
o sea que esta carpeta sea C:\\ConsolaOBS\\assets).
Cuando el sonidista dispara un efecto, el OBS lo busca EN SU PROPIO
DISCO: si el archivo no está acá, el stream queda en silencio.
"""


def version_incluida():
    try:
        with open(os.path.join(RAIZ, "consola_obs", "update", "version.py"),
                  encoding="utf-8") as f:
            m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', f.read())
            if m:
                return m.group(1)
    except Exception:
        pass
    return "?"


def _ignorado(ruta_abs):
    partes = os.path.relpath(ruta_abs, RAIZ).split(os.sep)
    if partes[0] in ("config",):
        return True
    if any(p in IGNORAR_DIRS for p in partes):
        return True
    base = partes[-1]
    if base in IGNORAR_BASE or base.endswith(IGNORAR_EXT):
        return True
    return False


def _agregar_archivo(z, ruta_abs, arcname):
    z.write(ruta_abs, arcname, compress_type=zipfile.ZIP_DEFLATED, compresslevel=1)


def _agregar_texto(z, arcname, texto):
    z.writestr(arcname, texto.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED,
               compresslevel=9)


def _agregar_arbol(z, subcarpeta, prefijo_zip):
    n = 0
    base = os.path.join(RAIZ, subcarpeta)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORAR_DIRS)
        for fn in sorted(filenames):
            ruta = os.path.join(dirpath, fn)
            if _ignorado(ruta):
                continue
            rel = os.path.relpath(ruta, RAIZ).replace(os.sep, "/")
            _agregar_archivo(z, ruta, prefijo_zip + rel)
            n += 1
            if n % 100 == 0:
                # Nombres con unicode raro (ej FF5C) rompen la consola
                # cp1252: sólo el contador.
                print(f"  ... {n} archivos", flush=True)
    return n


def main():
    version = version_incluida()
    print(f"Armando zips de la v{version} ...", flush=True)

    faltan = [f for f in ("ConsolaOBS.exe", "updater.exe")
              if not os.path.isfile(os.path.join(RAIZ, f))]
    if faltan:
        print(f"FALTA(N): {', '.join(faltan)}: corre compilar.bat primero.")
        return 1

    # 1) Consola (programa + todo).
    try:
        if os.path.exists(ZIP_CONSOLA):
            os.remove(ZIP_CONSOLA)
    except Exception:
        pass
    n = 0
    with zipfile.ZipFile(ZIP_CONSOLA, "w") as z:
        for fn in TOP_CONSOLA:
            ruta = os.path.join(RAIZ, fn)
            if not os.path.isfile(ruta):
                print(f"  AVISO: no existe {fn}, se saltea.")
                continue
            _agregar_archivo(z, ruta, "ConsolaOBS/" + fn)
            n += 1
        _agregar_texto(z, "ConsolaOBS/LEEME.txt",
                       LEEME_CONSOLA.format(version=version))
        n += 1
        n += _agregar_arbol(z, "consola_obs", "ConsolaOBS/")
        n += _agregar_arbol(z, "assets", "ConsolaOBS/")
    print(f"Consola: {n} entradas -> {os.path.getsize(ZIP_CONSOLA) / 1e9:.2f} GB",
          flush=True)

    # 2) OBS (sólo audios).
    try:
        if os.path.exists(ZIP_OBS):
            os.remove(ZIP_OBS)
    except Exception:
        pass
    m = 0
    with zipfile.ZipFile(ZIP_OBS, "w") as z:
        for sub in ("assets/Sondidos_pad", "assets/Musica"):
            m += _agregar_arbol(z, sub, "OBS/")
        _agregar_texto(z, "OBS/LEEME.txt", LEEME_OBS)
        m += 1
    print(f"OBS: {m} entradas -> {os.path.getsize(ZIP_OBS) / 1e9:.2f} GB", flush=True)

    # 3) Verificación mínima de lo armado.
    errores = []
    with zipfile.ZipFile(ZIP_CONSOLA) as z:
        nombres = set(z.namelist())
        for clave in ("ConsolaOBS/ConsolaOBS.exe", "ConsolaOBS/updater.exe",
                      "ConsolaOBS/main.py", "ConsolaOBS/LEEME.txt",
                      "ConsolaOBS/consola_obs/update/version.py",
                      "ConsolaOBS/assets/Sondidos_pad"):
            if not any(x == clave or x.startswith(clave + "/") for x in nombres):
                errores.append(f"Consola sin {clave}")
        with z.open("ConsolaOBS/consola_obs/update/version.py") as f:
            if version not in f.read().decode("utf-8"):
                errores.append("version.py del zip no coincide")
    with zipfile.ZipFile(ZIP_OBS) as z:
        nombres = set(z.namelist())
        for clave in ("OBS/LEEME.txt", "OBS/assets/Sondidos_pad", "OBS/assets/Musica"):
            if not any(x == clave or x.startswith(clave + "/") for x in nombres):
                errores.append(f"OBS sin {clave}")
        if any("/config/" in x or x.endswith(".exe") for x in nombres):
            errores.append("OBS trae cosas de más (config o exe)")
    if errores:
        print("VERIFICACIÓN FALLIDA:")
        for e in errores:
            print("  -", e)
        return 1
    print("Verificación OK: estructura + versión adentro correctas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
