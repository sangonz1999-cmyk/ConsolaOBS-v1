"""Copia la versión de consola_obs/update/version.py a los archivos de
metadatos de los .exe (version_info.txt y updater_version.txt).

La versión se cambia en UN solo lugar: consola_obs/update/version.py.
compilar.bat corre este script antes de compilar, así los metadatos de
ConsolaOBS.exe y updater.exe nunca quedan con un número distinto.

Uso: python sincronizar_version.py   (sólo stdlib; devuelve 0 si salió bien)
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_VERSION = os.path.join(RAIZ, "consola_obs", "update", "version.py")
ARCHIVOS_METADATOS = ("version_info.txt", "updater_version.txt")


def leer_version():
    with open(ARCHIVO_VERSION, "r", encoding="utf-8") as f:
        m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
    if not m:
        raise ValueError("No se encontró VERSION en version.py")
    version = m.group(1).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"VERSION tiene que ser X.Y.Z (es {version!r})")
    return version


def aplicar(texto, version):
    tupla = "(" + ", ".join(version.split(".") + ["0"]) + ")"
    texto = re.sub(r"(filevers|prodvers)=\([^)]*\)", lambda m: f"{m.group(1)}={tupla}", texto)
    texto = re.sub(r"(StringStruct\('(?:FileVersion|ProductVersion)',\s*')[^']*(')",
                   lambda m: f"{m.group(1)}{version}{m.group(2)}", texto)
    return texto


def main():
    try:
        version = leer_version()
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    for nombre in ARCHIVOS_METADATOS:
        ruta = os.path.join(RAIZ, nombre)
        try:
            with open(ruta, "r", encoding="utf-8", newline="") as f:
                original = f.read()
            nuevo = aplicar(original, version)
            if nuevo != original:
                with open(ruta, "w", encoding="utf-8", newline="") as f:
                    f.write(nuevo)
                print(f"{nombre}: actualizado a {version}")
            else:
                print(f"{nombre}: ya estaba en {version}")
        except Exception as e:
            print(f"ERROR en {nombre}: {e}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
