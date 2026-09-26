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
from consola_obs.sync import descubrir as mod_descubrir
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
    ok = srv_sync.iniciar_en_hilo(raiz, puerto, key, log=_log)
    # Escucha de discovery/pairing en LAN (hilo aparte): así la otra PC
    # nos encuentra y puede pedir vinculación. No frena nada si falla.
    try:
        mod_descubrir.iniciar_escucha(puerto, False, al_par=_al_pedido_vinculo,
                                      log=_log)
    except Exception:
        pass
    return ok


def _al_pedido_vinculo(ip, msg, pto=None):
    """Llega un pedido de vinculación (hilo de red): se pregunta en la
    UI. Al aceptar se adopta SU clave y se guarda su IP (una sola vez)."""
    try:
        E.ventana.after(0, lambda: _preguntar_vinculo(ip, msg, pto))
    except Exception:
        pass


def _preguntar_vinculo(ip, msg, pto=None):
    try:
        host = str((msg or {}).get("host") or ip)
        key = str((msg or {}).get("key") or "")
        if not key:
            return
        if not messagebox.askyesno(
                "Vinculación",
                f"La PC '{host}' ({ip}) quiere vincularse para sincronizar.\n\n"
                "Al aceptar se adopta SU clave (vale para las dos) y queda "
                "guardada: es una sola vez.\n\n¿Aceptar?"):
            mod_descubrir.rechazar_vinculo(ip, pto)
            return
        cfg_sync.guardar({"api_key": key, "ip_remota": ip})
        try:
            E.entrada_sync_ip.delete(0, "end")
            E.entrada_sync_ip.insert(0, ip)
            E.etiqueta_sync_estado.config(
                text=f"Vinculada con {host} ✓ (clave guardada)", fg="#2fd693")
        except Exception:
            pass
        mod_descubrir.responder_vinculo(ip, pto)
        mod_red.log_conexion("SYNC", f"vinculada con {host} ({ip})")
    except Exception:
        pass


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


def _ip_parece_clave(texto):
    """True si el campo IP trae pinta de clave (token largo sin puntos:
    el error típico de pegar la clave donde va la IP). Pura."""
    try:
        t = (texto or "").strip()
        if not t or t.lower() == "localhost":
            return False
        if t.startswith("http://") or t.startswith("https://"):
            return True
        return "." not in t and ":" not in t and len(t) > 20
    except Exception:
        return False


def sincronizar_ahora():
    """Handler del botón: guarda IP/puerto, abre el log y sincroniza
    en hilo daemon (la UI nunca se congela)."""
    try:
        ip = (E.entrada_sync_ip.get() or "").strip()
        if _ip_parece_clave(ip):
            messagebox.showwarning(
                "Revisá el campo",
                "Eso que pegaste en 'PC remota' parece la CLAVE, no la IP.\n\n"
                "En 'PC remota' va la IP de la otra PC (ej: 192.168.1.53).\n"
                "La clave no se escribe: con las 2 PCs abiertas usá 🔗 VINCULAR.")
            return
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
        # Si bajaron audios nuevos, se convierten en pads solos (igual
        # que al arrancar): si no, el archivo llega pero el pad recién
        # aparece al reiniciar.
        try:
            if (resumen or {}).get("bajados"):
                from consola_obs.ui import soundboard as mod_ui_soundboard
                E.ventana.after(
                    0, lambda: mod_ui_soundboard.detectar_sonidos_carpeta(avisar=False))
                _log("Sync: buscando pads nuevos entre lo bajado…")
        except Exception:
            pass

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


def buscar_pcs_ahora():
    """Busca PCs con el programa abierto en la red (hilo) y completa la
    IP: 1 hallada → directo; varias → lista para elegir."""
    try:
        cfg = cfg_sync.cargar()
        puerto = int(cfg.get("puerto") or cfg_sync.PUERTO_POR_DEFECTO)
    except Exception:
        puerto = cfg_sync.PUERTO_POR_DEFECTO
    try:
        E.etiqueta_sync_estado.config(text="Buscando PCs en la red…", fg="#ffb84d")
    except Exception:
        pass

    def _correr():
        halladas = mod_descubrir.buscar_pcs(puerto)

        def _terminar():
            try:
                if not halladas:
                    E.etiqueta_sync_estado.config(
                        text="Nada encontrado (misma red, programa abierto, firewall).",
                        fg="#ffb84d")
                    messagebox.showinfo(
                        "Buscar PCs",
                        "No se encontró ninguna PC con el programa abierto.\n\n"
                        "Revisá: misma WiFi/red, programa abierto en la otra PC, "
                        "y firewall (puerto 4456).")
                    return
                if len(halladas) == 1:
                    _usar_pc(halladas[0])
                    return
                _elegir_pc(halladas)
            except Exception:
                pass
        try:
            E.ventana.after(0, _terminar)
        except Exception:
            pass

    threading.Thread(target=_correr, daemon=True).start()


def _usar_pc(info):
    """Completa la IP hallada y avisa (la clave va por VINCULAR)."""
    try:
        E.entrada_sync_ip.delete(0, "end")
        E.entrada_sync_ip.insert(0, info.get("ip", ""))
        cfg_sync.guardar({"ip_remota": info.get("ip", "")})
        E.etiqueta_sync_estado.config(
            text=f"PC hallada: {info.get('host', '')} ({info.get('ip', '')}). "
                 "Falta la clave: usá 🔗 VINCULAR.",
            fg="#ffb84d")
    except Exception:
        pass


def _elegir_pc(halladas):
    try:
        win = tk.Toplevel(E.ventana)
    except Exception:
        return
    win.title("Elegí la otra PC")
    win.configure(bg=C.COLOR_MENU_FONDO)
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    tk.Label(win, text="PCs encontradas en tu red:",
             bg=C.COLOR_MENU_FONDO, fg=C.COLOR_MENU_TEXTO,
             font=(E.FUENTE_UI, 9)).pack(anchor="w", padx=14, pady=(12, 4))
    lista = tk.Listbox(win, bg="#0e1219", fg="white", relief="flat",
                       highlightthickness=1, highlightbackground="#2b3548",
                       font=(E.FUENTE_UI, 10), exportselection=False)
    for info in halladas:
        etiqueta = f"{info.get('host', '?')}  ({info.get('ip', '?')})"
        if info.get("mini"):
            etiqueta += "  [mini]"
        lista.insert("end", etiqueta)
    lista.pack(fill="both", expand=True, padx=14, pady=4)
    lista.selection_set(0)

    def _aceptar():
        try:
            sel = lista.curselection()
            info = halladas[sel[0]] if sel else halladas[0]
        except Exception:
            info = halladas[0]
        try:
            win.destroy()
        except Exception:
            pass
        _usar_pc(info)

    tk.Button(win, text="USAR ESTA PC", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
              activebackground="#2f3a4d", activeforeground="white",
              relief="flat", bd=0, pady=6, font=(E.FUENTE_UI, 9, "bold"),
              cursor="hand2", command=_aceptar).pack(fill="x", padx=14, pady=(4, 12))


def vincular_ahora():
    """Pide vinculación a la IP del campo (hilo): la otra PC pregunta
    una vez, acepta, adopta nuestra clave y listo para siempre."""
    try:
        ip = (E.entrada_sync_ip.get() or "").strip()
        if not ip:
            messagebox.showinfo(
                "Vincular",
                "Primero buscá la otra PC con 🔍 BUSCAR PCS (o escribí su IP).")
            return
        if _ip_parece_clave(ip):
            messagebox.showwarning(
                "Revisá el campo",
                "Eso parece la CLAVE, no la IP. Buscá la PC con 🔍 BUSCAR PCS.")
            return
        try:
            E.etiqueta_sync_estado.config(
                text=f"Pidiendo vinculación a {ip}… (aceptá allá)", fg="#ffb84d")
        except Exception:
            pass
        cfg = cfg_sync.cargar()
        key = cfg_sync.obtener_api_key(cfg)
        puerto = int(cfg.get("puerto") or cfg_sync.PUERTO_POR_DEFECTO)
    except Exception as e:
        try:
            messagebox.showerror("Vincular", f"No se pudo iniciar: {e}")
        except Exception:
            pass
        return

    def _correr():
        ok, motivo = mod_descubrir.pedir_vinculo(ip, key, puerto)

        def _terminar():
            try:
                if ok:
                    E.etiqueta_sync_estado.config(
                        text=f"Vinculada con {ip} ✓ (clave guardada, es una sola vez).",
                        fg="#2fd693")
                    messagebox.showinfo(
                        "Vinculada",
                        f"La otra PC aceptó y adoptó tu clave.\n\n"
                        "Ya podés apretar 🔄 SINCRONIZAR cuando quieras.")
                else:
                    E.etiqueta_sync_estado.config(text="No se pudo vincular.", fg="#ff5d6c")
                    messagebox.showwarning("Vincular", motivo)
            except Exception:
                pass
        try:
            E.ventana.after(0, _terminar)
        except Exception:
            pass

    threading.Thread(target=_correr, daemon=True).start()


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


def construir_seccion_sync(padre=None):
    """Agrega la sección SINCRONIZACIÓN a su pestaña de Ajustes. La llama
    app.py al armar la ventana; si algo falla, no frena el arranque."""
    from consola_obs.ui import cabecera as mod_ui_cabecera

    base = padre if padre is not None else E.barra
    cfg = cfg_sync.cargar()

    E.entrada_sync_ip = mod_ui_cabecera._entrada_menu(
        mod_ui_cabecera._fila_menu("PC remota", padre=base))
    E.entrada_sync_ip.insert(0, cfg.get("ip_remota", ""))
    E.entrada_sync_puerto = mod_ui_cabecera._entrada_menu(
        mod_ui_cabecera._fila_menu("Puerto", padre=base))
    E.entrada_sync_puerto.insert(0, str(cfg.get("puerto") or cfg_sync.PUERTO_POR_DEFECTO))
    mod_ui_cabecera._ayuda_menu(
        base, "Con las 2 PCs abiertas: 🔍 BUSCAR PCS y después 🔗 VINCULAR "
              "(la clave viaja sola y queda guardada: es una sola vez). "
              "A mano: IP de la otra PC + puerto 4456 + la misma clave "
              "en ambas (🔑 VER CLAVE).")

    E.etiqueta_sync_estado = tk.Label(
        base,
        text="Copia efectos, imágenes y música entre tus 2 PCs (misma WiFi/red).",
        bg=C.COLOR_MENU_FONDO, fg="#8fa0bd", font=(E.FUENTE_UI, 8),
        wraplength=420, justify="left",
    )
    E.etiqueta_sync_estado.pack(fill="x", padx=16, pady=(0, 2))

    E.boton_sync = tk.Button(
        base, text="🔄 SINCRONIZAR CON LA OTRA PC", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=7, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=sincronizar_ahora
    )
    E.boton_sync.pack(fill="x", padx=16, pady=(6, 2))
    mod_ui_cabecera._ayuda_menu(
        base, "Sincroniza en ambas direcciones: lo nuevo viaja, lo borrado se "
              "propaga y en conflictos gana el archivo más nuevo.")

    fila = tk.Frame(base, bg=C.COLOR_MENU_FONDO)
    fila.pack(fill="x", padx=16, pady=(4, 2))
    tk.Button(
        fila, text="🔍 BUSCAR PCS", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=buscar_pcs_ahora
    ).pack(side="left", fill="x", expand=True, padx=(0, 4))
    tk.Button(
        fila, text="🔗 VINCULAR", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=vincular_ahora
    ).pack(side="left", fill="x", expand=True, padx=(4, 0))

    fila2 = tk.Frame(base, bg=C.COLOR_MENU_FONDO)
    fila2.pack(fill="x", padx=16, pady=(4, 2))
    tk.Button(
        fila2, text="🛡 FIREWALL", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=abrir_firewall_sync
    ).pack(side="left", fill="x", expand=True, padx=(0, 4))
    tk.Button(
        fila2, text="🔑 VER CLAVE", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=mostrar_clave
    ).pack(side="left", fill="x", expand=True, padx=(4, 0))
