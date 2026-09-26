"""UI del sync bidireccional: sección en el menú Ajustes + ventana de log.

Todo corre en hilos daemon para no congelar la interfaz. Si algo de
Tk falla, no se rompe el resto del programa (todo va en try/except).
"""
import threading
import tkinter as tk
from tkinter import messagebox

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import red as mod_red
from consola_obs.sync import configuracion as cfg_sync
from consola_obs.sync import motor as motor_sync
from consola_obs.sync import servidor as srv_sync


def iniciar_servidor(log=None):
    """Levanta el servidor de sync al arrancar (hilo daemon) y asegura
    la regla de firewall del puerto. Nunca lanza."""
    def _log(msg):
        try:
            if log:
                log(msg)
            else:
                mod_red.log_conexion("SYNC", msg)
        except Exception:
            pass

    try:
        cfg = cfg_sync.cargar()
        raiz = cfg.get("carpeta_local") or ""
        puerto = int(cfg.get("puerto") or cfg_sync.PUERTO_POR_DEFECTO)
        key = cfg_sync.obtener_api_key(cfg)
    except Exception as e:
        _log(f"Sync: config inválida ({e}).")
        return False
    try:
        import os
        if not os.path.isdir(raiz):
            _log(f"Sync: no existe la carpeta local ({raiz}).")
            return False
    except Exception:
        return False
    try:
        ok_fw, admin_fw, msg_fw = mod_red.asegurar_regla_firewall(puerto)
        _log(f"Sync: firewall puerto {puerto}: {msg_fw}")
        if admin_fw:
            _log("Sync: para crear la regla de firewall, abrí el programa "
                 "como administrador una vez y apretá Sincronizar.")
    except Exception:
        pass
    return srv_sync.iniciar_en_hilo(raiz, puerto, key, log=_log)


def _agregar_log(texto_widget, linea):
    try:
        texto_widget.config(state="normal")
        texto_widget.insert("end", linea.rstrip() + "\n")
        texto_widget.see("end")
        texto_widget.config(state="disabled")
    except Exception:
        pass


def abrir_ventana_log():
    """Ventana con el registro de la sincronización. Una sola a la vez."""
    try:
        existente = getattr(E, "_ventana_sync_log", None)
        if existente is not None:
            try:
                existente.lift()
                return existente
            except Exception:
                pass
        win = tk.Toplevel(E.ventana, bg=C.COLOR_MENU_FONDO)
        win.title("Sincronización con la otra PC")
        win.geometry("560x380")
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        texto = tk.Text(win, bg="#0e1219", fg="#c3cee5", relief="flat",
                        font=(E.FUENTE_UI, 9), state="disabled")
        texto.pack(fill="both", expand=True, padx=10, pady=10)
        E._ventana_sync_log = win

        def _al_cerrar():
            try:
                E._ventana_sync_log = None
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass
        win.protocol("WM_DELETE_WINDOW", _al_cerrar)
        return win
    except Exception:
        return None


def _log_a_ventana(linea):
    try:
        win = getattr(E, "_ventana_sync_log", None)
        if win is None:
            return
        for hijo in win.winfo_children():
            if isinstance(hijo, tk.Text):
                E.ventana.after(0, lambda h=hijo, l=linea: _agregar_log(h, l))
                return
    except Exception:
        pass


def sincronizar_ahora():
    """Handler del botón: guarda IP/puerto, abre el log y sincroniza
    en hilo daemon (la UI nunca se congela)."""
    try:
        ip = (E.entrada_sync_ip.get() or "").strip()
        puerto_txt = (E.entrada_sync_puerto.get() or "").strip() or str(cfg_sync.PUERTO_POR_DEFECTO)
        try:
            puerto = int(puerto_txt)
        except ValueError:
            messagebox.showerror("Puerto inválido", "El puerto de sync debe ser un número.")
            return
        cfg_sync.guardar({"ip_remota": ip, "puerto": puerto})
        try:
            E.etiqueta_sync_estado.config(text="Sincronizando…", fg="#ffb84d")
            E.boton_sync.config(state="disabled", text="SINCRONIZANDO…")
        except Exception:
            pass
        abrir_ventana_log()
        _log_a_ventana(f"--- Sync con {ip}:{puerto} ---")
    except Exception as e:
        try:
            messagebox.showerror("Sync", f"No se pudo iniciar: {e}")
        except Exception:
            pass
        return

    def _correr():
        def _log(linea):
            _log_a_ventana(linea)
            try:
                mod_red.log_conexion("SYNC", linea)
            except Exception:
                pass
        try:
            ok, resumen = motor_sync.sincronizar(log=_log)
        except Exception as e:
            ok, resumen = False, {"errores": [str(e)]}

        def _terminar():
            try:
                E.boton_sync.config(state="normal", text="🔄 SINCRONIZAR CON LA OTRA PC")
            except Exception:
                pass
            try:
                if ok:
                    E.etiqueta_sync_estado.config(text="Sincronizado ✓", fg="#2fd693")
                else:
                    E.etiqueta_sync_estado.config(text="Con errores (ver registro)", fg="#ff5d6c")
            except Exception:
                pass
            try:
                errores = (resumen or {}).get("errores") or []
                if errores and not ok and not (resumen or {}).get("subidos") \
                        and not (resumen or {}).get("bajados"):
                    messagebox.showwarning("Sincronización", "\n".join(errores[:4]))
            except Exception:
                pass
        try:
            E.ventana.after(0, _terminar)
        except Exception:
            pass

    threading.Thread(target=_correr, daemon=True).start()


def abrir_firewall_sync():
    """Botón firewall de la sección sync (igual criterio que el de OBS)."""
    try:
        puerto_txt = (E.entrada_sync_puerto.get() or "").strip() or str(cfg_sync.PUERTO_POR_DEFECTO)
        puerto = int(puerto_txt)
    except ValueError:
        messagebox.showerror("Puerto inválido", "El puerto de sync debe ser un número.")
        return
    ok, necesita_admin, mensaje = mod_red.asegurar_regla_firewall(puerto)
    if ok:
        messagebox.showinfo("Firewall", mensaje)
    elif necesita_admin:
        messagebox.showwarning(
            "Hace falta administrador",
            f"{mensaje}\n\nCerrá el programa y abrilo con 'Ejecutar como "
            f"administrador', apretá SINCRONIZAR una vez, y listo.\n"
            f"(Puerto {puerto} TCP entrante).")
    else:
        messagebox.showerror("Firewall", mensaje)


def mostrar_clave():
    """Muestra la API key para copiarla a la otra PC (las 2 tienen que
    usar la misma)."""
    try:
        key = cfg_sync.obtener_api_key()
        messagebox.showinfo(
            "Clave de sincronización",
            f"Tu clave es:\n\n{key}\n\nPoné LA MISMA en la otra PC "
            "(variable CONSOLAOBS_SYNC_KEY o este mismo campo).")
    except Exception as e:
        messagebox.showerror("Sync", f"No se pudo leer la clave: {e}")


def construir_seccion_sync():
    """Agrega la sección SINCRONIZACIÓN al menú Ajustes. La llama app.py
    al armar el menú; si algo falla, no frena el arranque."""
    from consola_obs.ui import cabecera as mod_ui_cabecera

    cfg = cfg_sync.cargar()
    mod_ui_cabecera._seccion_menu("SINCRONIZACIÓN")

    E.entrada_sync_ip = mod_ui_cabecera._entrada_menu(mod_ui_cabecera._fila_menu("PC remota"))
    E.entrada_sync_ip.insert(0, cfg.get("ip_remota", ""))
    E.entrada_sync_puerto = mod_ui_cabecera._entrada_menu(mod_ui_cabecera._fila_menu("Puerto"))
    E.entrada_sync_puerto.insert(0, str(cfg.get("puerto") or cfg_sync.PUERTO_POR_DEFECTO))

    E.etiqueta_sync_estado = tk.Label(
        E.barra,
        text="Copia efectos, imágenes y música entre tus 2 PCs (misma WiFi/red).",
        bg=C.COLOR_MENU_FONDO, fg="#8fa0bd", font=(E.FUENTE_UI, 8),
        wraplength=300, justify="left",
    )
    E.etiqueta_sync_estado.pack(fill="x", padx=16, pady=(0, 2))

    E.boton_sync = tk.Button(
        E.barra, text="🔄 SINCRONIZAR CON LA OTRA PC", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=7, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=sincronizar_ahora
    )
    E.boton_sync.pack(fill="x", padx=16, pady=(6, 2))

    fila = tk.Frame(E.barra, bg=C.COLOR_MENU_FONDO)
    fila.pack(fill="x", padx=16, pady=(4, 2))
    tk.Button(
        fila, text="🛡 FIREWALL", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=abrir_firewall_sync
    ).pack(side="left", fill="x", expand=True, padx=(0, 4))
    tk.Button(
        fila, text="🔑 VER CLAVE", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=mostrar_clave
    ).pack(side="left", fill="x", expand=True, padx=(4, 0))
