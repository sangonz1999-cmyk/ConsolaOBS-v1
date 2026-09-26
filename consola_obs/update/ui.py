"""UI del auto-update: sección en Ajustes + chequeo al arranque.

Flujo (Fase 6): al arrancar se consulta GitHub en hilo daemon (nunca
frena nada); si hay release más nueva se pregunta [Actualizar]
[Más tarde]; al aceptar se descarga el ZIP a %TEMP% con progreso y se
lanza updater.exe/updater.py pasando el pid propio, y recién ahí se
cierra el programa para que el updater reemplace los archivos.

Todo en try/except: si algo falla, el programa sigue funcionando con
su versión actual (un error de update nunca deja nada inutilizable).
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import rutas as R
from consola_obs import red as mod_red
from consola_obs.update import checker as mod_checker
from consola_obs.update import version as mod_version

_ya_preguntado = {"esta_sesion": False}


def _log_sync(paso, detalle=""):
    try:
        mod_red.log_conexion(paso, detalle)
    except Exception:
        pass


def construir_seccion_actualizacion(padre=None):
    """Agrega la sección ACTUALIZACIÓN a su pestaña de Ajustes. La llama
    app.py; si falla, el resto se arma igual."""
    from consola_obs.ui import cabecera as mod_ui_cabecera

    base = padre if padre is not None else E.barra
    E.etiqueta_update_estado = tk.Label(
        base,
        text=f"Versión instalada: {mod_version.VERSION} (se busca sola al arrancar).",
        bg=C.COLOR_MENU_FONDO, fg="#8fa0bd", font=(E.FUENTE_UI, 8),
        wraplength=420, justify="left",
    )
    E.etiqueta_update_estado.pack(fill="x", padx=16, pady=(0, 2))
    E.boton_update = tk.Button(
        base, text="🔍 BUSCAR ACTUALIZACIONES", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=7, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=lambda: buscar_actualizaciones(manual=True)
    )
    E.boton_update.pack(fill="x", padx=16, pady=(6, 2))
    mod_ui_cabecera._ayuda_menu(
        base, "Consulta las Releases de GitHub y, si hay versión nueva, descarga el "
              "ZIP y actualiza con el updater separado (preserva tu config).")


def _set_estado(texto, color="#8fa0bd"):
    try:
        E.etiqueta_update_estado.config(text=texto, fg=color)
    except Exception:
        pass


def verificar_al_arranque(demora_ms=8000):
    """Chequeo automático poco después de arrancar (hilo daemon)."""
    try:
        E.ventana.after(demora_ms, lambda: buscar_actualizaciones(manual=False))
    except Exception:
        pass


def buscar_actualizaciones(manual=True):
    """Consulta GitHub en hilo daemon. Si hay algo más nuevo, pregunta
    en el hilo de UI (una sola vez por sesión en modo automático)."""
    try:
        E.boton_update.config(state="disabled", text="BUSCANDO…")
    except Exception:
        pass
    if manual:
        _set_estado("Consultando GitHub…")

    def _correr():
        info, error = mod_checker.hay_actualizacion()

        def _terminar():
            try:
                E.boton_update.config(state="normal", text="🔍 BUSCAR ACTUALIZACIONES")
            except Exception:
                pass
            if error:
                if manual:
                    _set_estado(error, "#ffb84d")
                    messagebox.showinfo("Actualizaciones", error)
                return
            if not info:
                if manual:
                    _set_estado(f"Ya tenés la última ({mod_version.VERSION}). ✓", "#2fd693")
                    messagebox.showinfo("Actualizaciones",
                                        f"Ya tenés la última versión ({mod_version.VERSION}).")
                else:
                    _set_estado(f"Versión {mod_version.VERSION} al día. ✓", "#2fd693")
                return
            _set_estado(f"Hay una versión nueva: {info['version']} (tenés {mod_version.VERSION}).",
                        "#ffb84d")
            if not manual and _ya_preguntado["esta_sesion"]:
                return
            _ya_preguntado["esta_sesion"] = True
            preguntar_actualizar(info)

        try:
            E.ventana.after(0, _terminar)
        except Exception:
            pass

    threading.Thread(target=_correr, daemon=True).start()


def preguntar_actualizar(info):
    """[Actualizar] [Más tarde] con las notas de la release."""
    try:
        notas = (info.get("notas") or "").strip().replace("\r", "")
        if len(notas) > 800:
            notas = notas[:800] + "…"
        tamano = ""
        try:
            mb = float(info.get("tamano") or 0) / (1024 * 1024)
            if mb > 0:
                tamano = f" (descarga ~{mb:.0f} MB)"
        except Exception:
            pass
        texto = (f"Nueva versión disponible: {info['version']}{tamano}\n"
                 f"Versión actual: {mod_version.VERSION}\n\n"
                 f"{notas}\n\n¿Actualizar ahora?")
        if messagebox.askyesno("Actualización disponible", texto):
            descargar_e_instalar(info)
    except Exception:
        pass


def descargar_e_instalar(info):
    """Descarga el ZIP con progreso y lanza el updater. Ventana propia
    (no congela el resto: la descarga corre en hilo)."""
    win = tk.Toplevel(E.ventana, bg=C.COLOR_MENU_FONDO)
    win.title(f"Descargando v{info['version']}…")
    win.geometry("380x130")
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    tk.Label(win, text=f"Bajando ConsolaOBS-Consola.zip (v{info['version']})…",
             bg=C.COLOR_MENU_FONDO, fg="white",
             font=(E.FUENTE_UI, 9)).pack(pady=(14, 6))
    barra = ttk.Progressbar(win, mode="determinate", maximum=100)
    barra.pack(fill="x", padx=20)
    etiqueta = tk.Label(win, text="Conectando…", bg=C.COLOR_MENU_FONDO,
                        fg="#8fa0bd", font=(E.FUENTE_UI, 8))
    etiqueta.pack(pady=6)

    try:
        destino = os.path.join(mod_checker.carpeta_descarga(),
                               f"ConsolaOBS-{info['version']}.zip")
    except Exception:
        try:
            win.destroy()
        except Exception:
            pass
        return

    def _progreso(bajados, total):
        def _pintar():
            try:
                if total > 0:
                    barra["value"] = bajados * 100.0 / total
                    etiqueta.config(
                        text=f"{bajados // (1024*1024)} / {total // (1024*1024)} MB")
                else:
                    etiqueta.config(text=f"{bajados // (1024*1024)} MB…")
            except Exception:
                pass
        try:
            E.ventana.after(0, _pintar)
        except Exception:
            pass

    def _correr():
        ruta, error = mod_checker.descargar(info["zip_url"], destino, _progreso)

        def _terminar():
            try:
                win.destroy()
            except Exception:
                pass
            if error or not ruta:
                _set_estado(error or "Falló la descarga.", "#ff5d6c")
                messagebox.showerror("Actualización", error or "Falló la descarga.")
                return
            lanzar_updater_y_cerrar(info, ruta)

        try:
            E.ventana.after(0, _terminar)
        except Exception:
            pass

    threading.Thread(target=_correr, daemon=True).start()


def _comando_updater():
    """(ejecutable, es_exe): updater.exe junto a la instalación si está
    compilado; si no, `python updater.py` (PC de desarrollo)."""
    try:
        cand_exe = os.path.join(R.CARPETA_SCRIPT, "updater.exe")
        if os.path.isfile(cand_exe):
            return [cand_exe], True
        cand_py = os.path.join(R.CARPETA_SCRIPT, "updater.py")
        if os.path.isfile(cand_py):
            return [sys.executable, cand_py], False
    except Exception:
        pass
    return None, False


def lanzar_updater_y_cerrar(info, ruta_zip):
    """Lanza el updater (que espera a que este pid se cierre) y cierra
    el programa por el camino normal (guarda todo, vacía la fuente de
    efectos)."""
    comando, _es_exe = _comando_updater()
    if not comando:
        messagebox.showerror(
            "Actualización",
            "Se descargó el ZIP pero no se encontró updater.exe junto al "
            "programa. Descargá la release a mano desde GitHub.")
        return
    try:
        reinicio = ""
        if getattr(sys, "frozen", False):
            cand = os.path.join(R.CARPETA_SCRIPT, "ConsolaOBS.exe")
            if os.path.isfile(cand):
                reinicio = cand
        args = (comando + ["--install-dir", R.CARPETA_SCRIPT,
                           "--zip", ruta_zip,
                           "--pid", str(os.getpid()),
                           "--esperada", str(info.get("version") or "")])
        if reinicio:
            args += ["--restart", reinicio]
        _log_sync("UPDATE", f"lanzo updater v{info.get('version')} y cierro.")
        # Consola PROPIA a propósito (no heredada ni suprimida): es la
        # ventana de progreso del updater, no un parpadeo.
        subprocess.Popen(args, cwd=R.CARPETA_SCRIPT,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except Exception as e:
        messagebox.showerror("Actualización", f"No se pudo lanzar el updater: {e}")
        return
    # Cierre normal: guarda configs, vacía efectos/música y destruye.
    try:
        from consola_obs.ui import ventana as mod_ui_ventana
        mod_ui_ventana.al_cerrar()
    except Exception:
        pass
    try:
        E.ventana.destroy()
    except Exception:
        pass
