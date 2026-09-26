"""Actualizador separado de ConsolaOBS (Fases 4 y 5 del auto-update).

Lo lanza el programa principal DESPUÉS de descargar el ZIP y ANTES de
cerrarse; corre con el programa ya cerrado, por eso puede reemplazar
sus archivos sin problemas:

  updater --install-dir <carpeta> --zip <nuevo.zip> --pid <pid_prog>
          --esperada <1.1.3> [--restart <ConsolaOBS.exe>]

Pasos: espera que el programa se cierre -> valida el ZIP (sin tocar
nada) -> lo descomprime en temporal -> valida el contenido (tiene que
traer main.py + la versión esperada) -> hace backup de lo que va a
pisar -> copia lo nuevo preservando config/ del usuario -> valida la
instalación (si falla, restaura el backup) -> inicia la nueva versión
-> limpia temporales.

SÓLO stdlib: se compila como updater.exe con PyInstaller (ver
compilar.bat) y también corre con `python updater.py` en la PC de
desarrollo. Nunca toca config/ (contraseña de OBS, ajustes, pads,
música reciente, clave de sync): actualizar no borra nada del usuario.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

# Lo que NUNCA se pisa con el ZIP (datos del usuario). Rutas relativas
# a la carpeta de instalación, en minúsculas y con /.
PRESERVAR = ("config/",)
# Carpetas gigantes que no se backupean (se reponen con el ZIP o con el
# sync/manual; backupear 1 GB en cada update no tiene sentido).
SIN_BACKUP = ("assets/",)


def _log(linea, log=None):
    texto = f"[{time.strftime('%H:%M:%S')}] {linea}"
    try:
        print(texto, flush=True)
    except Exception:
        pass
    if log:
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(texto + "\n")
        except Exception:
            pass


def _rel_normal(ruta_abs, base_abs):
    return os.path.relpath(ruta_abs, base_abs).replace(os.sep, "/")


def _preservado(rel):
    bajo = rel.lower()
    return any(bajo == p.rstrip("/") or bajo.startswith(p) for p in PRESERVAR)


def _sin_backup(rel):
    bajo = rel.lower()
    return any(bajo == p.rstrip("/") or bajo.startswith(p) for p in SIN_BACKUP)


def esperar_pid(pid, timeout_seg=90, log=None):
    """Espera a que el proceso pid termine (el programa cerrándose).
    pid 0 = no esperar. Devuelve True si ya no existe."""
    try:
        pid = int(pid or 0)
    except Exception:
        pid = 0
    if pid <= 0:
        return True
    if pid == os.getpid():
        return True
    inicio = time.monotonic()
    while time.monotonic() - inicio < timeout_seg:
        try:
            os.kill(pid, 0)
        except OSError:
            return True  # ya no existe
        except Exception:
            return True
        time.sleep(0.5)
    try:
        os.kill(pid, 0)
        _log(f"AVISO: el programa (pid {pid}) no se cerró en {timeout_seg}s; sigo igual.", log)
        return False
    except OSError:
        return True


def validar_zip(ruta_zip, log=None):
    """El ZIP tiene que abrir y estar íntegro. No toca nada."""
    try:
        with zipfile.ZipFile(ruta_zip) as z:
            malo = z.testzip()
            if malo:
                return False, f"ZIP corrupto (archivo dañado: {malo})."
            nombres = z.namelist()
        if not nombres:
            return False, "ZIP vacío."
        return True, ""
    except Exception as e:
        return False, f"No se pudo leer el ZIP: {e}"


def validar_contenido(carpeta_suelta, version_esperada, log=None):
    """Lo descomprimido tiene que ser una instalación válida: main.py +
    consola_obs/app.py + versión EXACTA a la esperada (leída del
    version.py nuevo, no del instalado)."""
    main = os.path.join(carpeta_suelta, "main.py")
    app = os.path.join(carpeta_suelta, "consola_obs", "app.py")
    ver_py = os.path.join(carpeta_suelta, "consola_obs", "update", "version.py")
    if not os.path.isfile(main):
        return False, "El ZIP no trae main.py (no es una release válida)."
    if not os.path.isfile(app):
        return False, "El ZIP no trae consola_obs/app.py."
    version_nueva = ""
    try:
        with open(ver_py, "r", encoding="utf-8") as f:
            for linea in f.read().splitlines():
                linea = linea.strip()
                if linea.startswith("VERSION"):
                    version_nueva = linea.split("=", 1)[1].strip().strip("\"'")
                    break
    except Exception:
        pass
    if version_esperada and version_nueva != version_esperada:
        return False, (f"El ZIP trae la versión {version_nueva or '?'} pero se "
                       f"esperaba la {version_esperada}. No se toca nada.")
    return True, version_nueva


def _es_propio_en_ejecucion(destino_abs):
    """True si 'destino' es este mismo ejecutable corriendo (en Windows
    no se puede pisar un .exe en uso: se saltea y se avisa)."""
    try:
        propio = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
        return os.path.abspath(destino_abs) == propio
    except Exception:
        return False


def aplicar(carpeta_nueva, install_dir, backup_dir, log=None):
    """Copia lo nuevo sobre la instalación (salvo PRESERVAR), guardando
    antes en backup_dir lo que pisa (salvo SIN_BACKUP). Devuelve
    ([copiados], [preservados], [salteados])."""
    copiados, preservados, salteados = [], [], []
    for dirpath, _dirs, files in os.walk(carpeta_nueva):
        for fn in files:
            origen = os.path.join(dirpath, fn)
            rel = _rel_normal(origen, carpeta_nueva)
            if _preservado(rel):
                preservados.append(rel)
                continue
            destino = os.path.join(install_dir, *rel.split("/"))
            if _es_propio_en_ejecucion(destino):
                salteados.append(rel + " (en ejecución)")
                continue
            try:
                if os.path.isfile(destino) and not _sin_backup(rel):
                    bkp = os.path.join(backup_dir, *rel.split("/"))
                    os.makedirs(os.path.dirname(bkp), exist_ok=True)
                    shutil.copy2(destino, bkp)
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.copy2(origen, destino)
                copiados.append(rel)
            except Exception as e:
                salteados.append(f"{rel} (error: {e})")
    return copiados, preservados, salteados


def restaurar(backup_dir, install_dir, log=None):
    """Vuelve atrás lo copiado con el backup. Nunca lanza."""
    try:
        for dirpath, _dirs, files in os.walk(backup_dir):
            for fn in files:
                origen = os.path.join(dirpath, fn)
                rel = _rel_normal(origen, backup_dir)
                destino = os.path.join(install_dir, *rel.split("/"))
                try:
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    shutil.copy2(origen, destino)
                except Exception as e:
                    _log(f"Rollback parcial en {rel}: {e}", log)
    except Exception as e:
        _log(f"Rollback falló: {e}", log)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Actualizador de ConsolaOBS")
    ap.add_argument("--install-dir", required=True)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--pid", default="0")
    ap.add_argument("--esperada", default="")
    ap.add_argument("--restart", default="")
    ap.add_argument("--log", default="")
    args = ap.parse_args(argv)

    install_dir = os.path.abspath(args.install_dir)
    ruta_zip = os.path.abspath(args.zip)
    log = args.log or os.path.join(tempfile.gettempdir(), "ConsolaOBS", "update", "update.log")
    try:
        os.makedirs(os.path.dirname(log), exist_ok=True)
    except Exception:
        pass

    _log(f"Updater: instalación={install_dir} zip={ruta_zip} esperada={args.esperada or '?'}", log)
    if not os.path.isdir(install_dir):
        _log("ERROR: no existe la carpeta de instalación.", log)
        return 1
    if not os.path.isfile(ruta_zip):
        _log("ERROR: no existe el ZIP descargado.", log)
        return 1

    esperar_pid(args.pid, log=log)

    ok, detalle = validar_zip(ruta_zip, log)
    if not ok:
        _log(f"ERROR: {detalle} Tu instalación no se tocó.", log)
        return 1

    tmp_suelto = tempfile.mkdtemp(prefix="consolaobs_update_")
    try:
        with zipfile.ZipFile(ruta_zip) as z:
            z.extractall(tmp_suelto)
        # La release puede venir con una subcarpeta raíz única
        # (ConsolaOBS-v1/...): si lo suelto no tiene main.py pero hay
        # una sola subcarpeta que sí, se usa esa.
        if not os.path.isfile(os.path.join(tmp_suelto, "main.py")):
            try:
                subs = [d for d in os.listdir(tmp_suelto)
                        if os.path.isdir(os.path.join(tmp_suelto, d))]
                if len(subs) == 1 and os.path.isfile(
                        os.path.join(tmp_suelto, subs[0], "main.py")):
                    tmp_suelto = os.path.join(tmp_suelto, subs[0])
            except Exception:
                pass
        ok, detalle = validar_contenido(tmp_suelto, args.esperada, log)
        if not ok:
            _log(f"ERROR: {detalle} Tu instalación no se tocó.", log)
            return 1
        _log(f"Contenido válido (versión {detalle}).", log)

        backup_dir = os.path.join(os.path.dirname(log), f"backup_{detalle or 'prev'}")
        try:
            if os.path.isdir(backup_dir):
                shutil.rmtree(backup_dir, ignore_errors=True)
            os.makedirs(backup_dir, exist_ok=True)
        except Exception:
            pass

        copiados, preservados, salteados = aplicar(tmp_suelto, install_dir, backup_dir, log)
        _log(f"Copiados {len(copiados)} archivos; preservados del usuario: {len(preservados)}; "
             f"salteados: {len(salteados)}.", log)
        for s in salteados[:10]:
            _log(f"  salteado: {s}", log)

        # Validación post-copia sobre lo YA instalado: si quedó rota,
        # se restaura el backup.
        ok, detalle2 = validar_contenido(install_dir, args.esperada or detalle, log)
        if not ok:
            _log(f"ERROR post-instalación: {detalle2} Restauro backup.", log)
            restaurar(backup_dir, install_dir, log)
            return 2
        _log("Instalación verificada.", log)

        if args.restart:
            arranque = os.path.abspath(args.restart)
            if os.path.isfile(arranque):
                try:
                    subprocess.Popen([arranque], cwd=install_dir,
                                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
                    _log(f"Nueva versión iniciada: {arranque}", log)
                except Exception as e:
                    _log(f"No se pudo iniciar la nueva versión ({e}): abrila a mano.", log)
        try:
            os.remove(ruta_zip)
        except Exception:
            pass
        _log("Listo.", log)
        return 0
    finally:
        try:
            shutil.rmtree(tmp_suelto, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
