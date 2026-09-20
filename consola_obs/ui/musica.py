"""Mini player de música (Fase 3) + ventana biblioteca (Fase 4).

La barra vive al pie del panel de fuentes (transporte, título y
progreso clickeable con seek exacto) y se reconstruye con
construir_cuerpo. El botón abre la biblioteca estilo Spotify:
carpetas a la izquierda, temas a la derecha, Recientes arriba,
doble clic reproduce y el tema sonando queda resaltado.
"""
import os
import tkinter as tk
from tkinter import messagebox

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs.audio import musica as mod_musica
from consola_obs.ui import dibujo as mod_ui_dibujo

ALTURA_MINI = 82
INTERVALO_REFRESCO_MS = 250
COLOR_PISTA = "#242d3d"
COLOR_TIEMPO = "#8fa0bd"

_w = {}
_loop = {"en_marcha": False}


def _vivos():
    try:
        return bool(_w.get("marco") and _w["marco"].winfo_exists())
    except Exception:
        return False


def _necesita_conexion():
    if E.conectado:
        return True
    try:
        messagebox.showinfo("Sin conexión", "Conectate a OBS para usar la música.")
    except Exception:
        pass
    return False


def _necesita_tema(snap):
    if snap.get("rel"):
        return True
    try:
            messagebox.showinfo("Sin música", "Elegí un tema en la\n🎵 Biblioteca")
    except Exception:
        pass
    return False


def _icono_barra(nombre):
    """Icono SVG de la barra a 18px (None si no se pudo: se cae al
    emoji de texto). La referencia vive en _w para que Tk no lo
    libere."""
    try:
        foto = mod_ui_dibujo._imagen_svg_menu("menu/" + nombre, 18)
    except Exception:
        foto = None
    if foto is not None:
        _w.setdefault("imgs", []).append(foto)
    return foto


def _boton_transporte(padre, texto, comando, ancho=3):
    boton = tk.Button(
        padre, text=texto, width=ancho, bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 11), cursor="hand2",
        command=comando,
    )
    boton.pack(side="left", padx=1)
    return boton


def _boton_icono(padre, svg, texto_respaldo, comando):
    """Botón solo-icono de 34x28 (o de texto si el SVG faltó)."""
    foto = _icono_barra(svg)
    if foto is None:
        return _boton_transporte(padre, texto_respaldo, comando)
    boton = tk.Button(
        padre, image=foto, width=34, height=28, bg="#242d3d",
        activebackground="#2f3a4d", relief="flat", bd=0, cursor="hand2",
        command=comando,
    )
    boton.pack(side="left", padx=1)
    return boton


def _alternar_playpausa():
    if not _necesita_conexion():
        return
    snap = mod_musica.estado_actual()
    if snap["estado"] == "SONANDO":
        mod_musica.pausar()
    elif snap["estado"] == "PAUSADA" or snap.get("rel"):
        mod_musica.reanudar()
    else:
        _necesita_tema(snap)


def _detener():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.detener()


def _reiniciar():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.reiniciar()


def _anterior():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.anterior()


def _siguiente():
    if not _necesita_conexion():
        return
    if not _necesita_tema(mod_musica.estado_actual()):
        return
    mod_musica.siguiente()


def _alternar_repetir():
    if not _necesita_conexion():
        return
    try:
        mod_musica.alternar_repetir()
    except Exception:
        pass
    _refrescar_mini_player()


def _elegir_tema_provisorio():
    """El botón de la barra abre la biblioteca (Fase 4)."""
    abrir_biblioteca()


def _clic_progreso(event):
    """Clic en la barra = salto al momento exacto (seek en ms)."""
    if not E.conectado:
        return
    try:
        snap = mod_musica.estado_actual()
        dur = float(snap.get("duracion_ms") or 0.0)
        if dur <= 0 or not snap.get("rel"):
            return
        ancho = _w["progreso"].winfo_width()
        if ancho <= 1:
            return
        frac = min(1.0, max(0.0, float(event.x) / float(ancho)))
        mod_musica.seek_ms(frac * dur)
    except Exception:
        pass


def _dibujar_progreso(frac):
    try:
        lienzo = _w["progreso"]
        ancho = lienzo.winfo_width()
        alto = lienzo.winfo_height()
        if ancho <= 1 or alto <= 1:
            return
        lienzo.delete("all")
        lienzo.create_rectangle(0, 0, ancho, alto, fill=COLOR_PISTA, outline="")
        hasta = int(ancho * min(1.0, max(0.0, frac)))
        if hasta > 0:
            lienzo.create_rectangle(0, 0, hasta, alto, fill=E.color_acento(), outline="")
    except Exception:
        pass


def _refrescar_mini_player():
    if not _vivos():
        _loop["en_marcha"] = False
        return
    try:
        snap = mod_musica.estado_actual()
        titulo = snap.get("titulo")
        if titulo:
            texto = ("♪ " + titulo)[:48]
            _w["titulo"].config(text=texto, fg="white")
        else:
            _w["titulo"].config(text="Sin música — abrí la 🎵 Biblioteca", fg="#828da6")
        if snap["estado"] == "SONANDO" and _w.get("img_pause") is not None:
            _w["play"].config(image=_w["img_pause"], text="", width=34, height=28)
        elif _w.get("img_play") is not None:
            _w["play"].config(image=_w["img_play"], text="", width=34, height=28)
        else:
            _w["play"].config(image="", text="▶", width=3, height=28)
        dur = float(snap.get("duracion_ms") or 0.0)
        cur = float(snap.get("cursor_ms") or 0.0)
        _w["tiempos"].config(
            text=f"{mod_musica.formatear_ms(cur)} / {mod_musica.formatear_ms(dur)}"
        )
        _dibujar_progreso(cur / dur if dur > 0 else 0.0)
        _w["repetir"].config(bg=("#3b4a63" if snap.get("repetir") else "#242d3d"))
    except Exception:
        pass
    try:
        E.ventana.after(INTERVALO_REFRESCO_MS, _refrescar_mini_player)
    except Exception:
        _loop["en_marcha"] = False


def construir_mini_player():
    """Crea la barra al pie del panel de fuentes (se llama al final de
    construir_cuerpo, así sobrevive a cambios de tema/diseño)."""
    try:
        viejo = _w.get("marco")
        if viejo is not None:
            try:
                viejo.destroy()
            except Exception:
                pass
        _w.clear()
        _loop["en_marcha"] = False
    except Exception:
        pass

    marco = tk.Frame(E.marco_fuentes, bg=E.color_barra_titulo(), height=ALTURA_MINI)
    marco.pack(side="bottom", fill="x")
    marco.pack_propagate(False)
    _w["marco"] = marco

    tk.Frame(marco, bg=E.color_acento(), height=2).pack(side="top", fill="x")

    fila = tk.Frame(marco, bg=E.color_barra_titulo())
    fila.pack(side="top", fill="x", padx=8, pady=(6, 2))

    # Play/pausa con iconos SVG: pausa sonando, triángulo en pausa.
    _w["play"] = _boton_transporte(fila, "▶", _alternar_playpausa)
    _w["img_pause"] = _icono_barra("menu_barra_pause.svg")
    _w["img_play"] = _icono_barra("menu_barra_play.svg")
    _boton_icono(fila, "menu_barra_stop.svg", "⏹", _detener)
    _boton_icono(fila, "menu_barra_reiniciar.svg", "↻", _reiniciar)
    _boton_icono(fila, "menu_barra_anterior.svg", "⏮", _anterior)
    _boton_icono(fila, "menu_barra_siguiente.svg", "⏭", _siguiente)
    # Repetir usa el shuffle del set (el motor no tiene aleatorio).
    _w["repetir"] = _boton_icono(fila, "menu_barra_repetir.svg", "🔁", _alternar_repetir)

    _w["titulo"] = tk.Label(
        fila, text="Sin música — abrí la 🎵 Biblioteca", bg=E.color_barra_titulo(),
        fg="#828da6", font=(E.FUENTE_UI, 10, "bold"), anchor="w",
    )
    _w["titulo"].pack(side="left", fill="x", expand=True, padx=(8, 4))

    _w["tiempos"] = tk.Label(
        fila, text="00:00 / 00:00", bg=E.color_barra_titulo(),
        fg=COLOR_TIEMPO, font=(E.FUENTE_UI, 8, "bold"),
    )
    _w["tiempos"].pack(side="left", padx=(0, 6))

    _foto_nota = _icono_barra("menu_barra_nota.svg")
    if _foto_nota is None:
        texto_biblio, img_biblio = "🎵 Biblioteca", ""
    else:
        texto_biblio, img_biblio = "Biblioteca", _foto_nota
    tk.Button(
        fila, text=texto_biblio, image=img_biblio, compound="left",
        bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=_elegir_tema_provisorio,
    ).pack(side="left")

    _w["progreso"] = tk.Canvas(
        marco, height=12, bg=COLOR_PISTA, highlightthickness=0, cursor="hand2"
    )
    _w["progreso"].pack(side="top", fill="x", padx=10, pady=(2, 6))
    _w["progreso"].bind("<Button-1>", _clic_progreso)

    if not _loop["en_marcha"]:
        _loop["en_marcha"] = True
        try:
            E.ventana.after(INTERVALO_REFRESCO_MS, _refrescar_mini_player)
        except Exception:
            _loop["en_marcha"] = False


# ------------------------------------------------------------------
# Ventana biblioteca estilo Spotify (Fase 4)
# ------------------------------------------------------------------
# Un solo Toplevel: si ya está abierta se trae al frente y se
# reescanea (los temas nuevos aparecen solos). Carpetas a la
# izquierda (Recientes primero), temas a la derecha, doble clic o
# Enter reproduce, y el tema sonando queda resaltado.
_biblio = {"ventana": None, "carpeta": None, "temas": [],
           "loop": False}
COLOR_RESALTADO_TEMA = "#31435c"


def _biblio_viva():
    try:
        return bool(_biblio.get("ventana") and _biblio["ventana"].winfo_exists())
    except Exception:
        return False


def _titulo_rel(rel):
    try:
        return os.path.splitext(os.path.basename(rel))[0]
    except Exception:
        return rel


def _temas_recientes_existentes():
    try:
        from consola_obs import rutas as _R
        return [r for r in mod_musica.recientes()
                if os.path.isfile(os.path.join(_R.CARPETA_MUSICA, r))]
    except Exception:
        return []


def _pintar_carpetas(biblioteca):
    lista = _biblio["lista_carpetas"]
    lista.delete(0, "end")
    _biblio["nombres_carpetas"] = ["Recientes"] + sorted(biblioteca)
    for nombre in _biblio["nombres_carpetas"]:
        if nombre == "Recientes":
            lista.insert("end", f"🕘 Recientes ({len(_temas_recientes_existentes())})")
        else:
            lista.insert("end", f"📁 {nombre} ({len(biblioteca[nombre])})")
    actual = _biblio.get("carpeta")
    if actual in _biblio["nombres_carpetas"]:
        lista.selection_clear(0, "end")
        lista.selection_set(_biblio["nombres_carpetas"].index(actual))
        lista.see(_biblio["nombres_carpetas"].index(actual))
    else:
        _biblio["carpeta"] = "Recientes"
        lista.selection_clear(0, "end")
        lista.selection_set(0)


def _temas_de_carpeta(biblioteca, carpeta):
    if carpeta == "Recientes":
        return _temas_recientes_existentes()
    return list(biblioteca.get(carpeta, []))


def _pintar_temas():
    if not _biblio_viva():
        return
    biblioteca = _biblio.get("biblioteca", {})
    carpeta = _biblio.get("carpeta") or "Recientes"
    filtro = (_biblio.get("busqueda", "").strip().lower()
              if isinstance(_biblio.get("busqueda"), str) else "")
    temas = _temas_de_carpeta(biblioteca, carpeta)
    if filtro:
        temas = [t for t in temas if filtro in _titulo_rel(t).lower()]
    _biblio["temas"] = temas
    lista = _biblio["lista_temas"]
    lista.delete(0, "end")
    if not temas:
        if not biblioteca:
            lista.insert("end", "Poné mp3 en assets/Musica/<carpeta>/")
        elif carpeta == "Recientes":
            lista.insert("end", "Todavía no hay recientes.")
        else:
            lista.insert("end", "Carpeta vacía.")
    for rel in temas:
        lista.insert("end", "♪ " + _titulo_rel(rel))
    _resaltar_tema_actual()


def _resaltar_tema_actual():
    if not _biblio_viva():
        return
    try:
        lista = _biblio["lista_temas"]
        actual = mod_musica.estado_actual().get("rel")
        for i in range(lista.size()):
            try:
                lista.itemconfig(i, bg="#10141b", fg="white")
            except Exception:
                pass
        if actual and actual in _biblio.get("temas", []):
            idx = _biblio["temas"].index(actual)
            try:
                lista.itemconfig(idx, bg=COLOR_RESALTADO_TEMA)
            except Exception:
                pass
        snap = mod_musica.estado_actual()
        titulo = snap.get("titulo") or "—"
        _biblio["actual"].config(text=f"♪ {titulo}  ·  {snap.get('estado', '')}")
    except Exception:
        pass


def _refrescar_biblioteca():
    if not _biblio_viva():
        _biblio["loop"] = False
        return
    _resaltar_tema_actual()
    try:
        E.ventana.after(500, _refrescar_biblioteca)
    except Exception:
        _biblio["loop"] = False


def _cargar_biblioteca():
    if not _biblio_viva():
        return
    _biblio["biblioteca"] = mod_musica.escanear_biblioteca()
    _pintar_carpetas(_biblio["biblioteca"])
    _pintar_temas()


def _al_elegir_carpeta(event=None):
    if not _biblio_viva():
        return
    try:
        sel = _biblio["lista_carpetas"].curselection()
        if not sel:
            return
        _biblio["carpeta"] = _biblio["nombres_carpetas"][sel[0]]
    except Exception:
        return
    _pintar_temas()


def _al_buscar(event=None):
    if not _biblio_viva():
        return
    try:
        _biblio["busqueda"] = _biblio["entrada_busqueda"].get()
    except Exception:
        _biblio["busqueda"] = ""
    _pintar_temas()


def _reproducir_seleccionado():
    if not _necesita_conexion():
        return
    if not _biblio_viva():
        return
    try:
        sel = _biblio["lista_temas"].curselection()
        temas = _biblio.get("temas", [])
        if not sel or not temas or sel[0] >= len(temas):
            messagebox.showinfo("Biblioteca", "Elegí un tema de la lista.")
            return
        mod_musica.reproducir_lista(list(temas), int(sel[0]))
    except Exception:
        return
    _resaltar_tema_actual()


def _cerrar_biblioteca():
    _biblio["loop"] = False
    try:
        if _biblio.get("ventana") is not None:
            _biblio["ventana"].destroy()
    except Exception:
        pass
    _biblio["ventana"] = None


def abrir_biblioteca():
    """Abre la ventana biblioteca (o la trae al frente reescaneada si
    ya estaba abierta)."""
    if _biblio_viva():
        try:
            _cargar_biblioteca()
            _biblio["ventana"].lift()
            _biblio["ventana"].focus_force()
        except Exception:
            pass
        return

    ventana = tk.Toplevel(E.ventana)
    ventana.title("🎵 Música en el stream")
    ventana.configure(bg="#10141b")
    ventana.geometry("560x480")
    _biblio["ventana"] = ventana
    _biblio["carpeta"] = "Recientes"
    _biblio["temas"] = []
    _biblio["busqueda"] = ""
    ventana.protocol("WM_DELETE_WINDOW", _cerrar_biblioteca)

    tk.Label(
        ventana, text="🎵 Música en el stream", bg="#10141b", fg="white",
        font=(E.FUENTE_UI, 12, "bold"),
    ).pack(anchor="w", padx=12, pady=(12, 2))
    tk.Label(
        ventana, text="Doble clic o Enter reproduce al stream",
        bg="#10141b", fg="#828da6", font=(E.FUENTE_UI, 9),
    ).pack(anchor="w", padx=12, pady=(0, 8))

    fila_busqueda = tk.Frame(ventana, bg="#10141b")
    fila_busqueda.pack(fill="x", padx=12, pady=(0, 8))
    _biblio["entrada_busqueda"] = tk.Entry(
        fila_busqueda, bg="#1b2230", fg="white", insertbackground="white",
        relief="flat", highlightthickness=1, highlightbackground="#2b3548",
        font=(E.FUENTE_UI, 10),
    )
    _biblio["entrada_busqueda"].pack(side="left", fill="x", expand=True, ipady=4)
    _biblio["entrada_busqueda"].bind("<KeyRelease>", _al_buscar)
    tk.Button(
        fila_busqueda, text="↻", bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 10, "bold"), cursor="hand2",
        command=_cargar_biblioteca,
    ).pack(side="left", padx=(6, 0))

    cuerpo = tk.Frame(ventana, bg="#10141b")
    cuerpo.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    _biblio["lista_carpetas"] = tk.Listbox(
        cuerpo, width=22, bg="#151a24", fg="white",
        selectbackground="#2f3a4d", selectforeground="white",
        relief="flat", highlightthickness=1, highlightbackground="#2b3548",
        font=(E.FUENTE_UI, 10), exportselection=False,
    )
    _biblio["lista_carpetas"].pack(side="left", fill="y", padx=(0, 8))
    _biblio["lista_carpetas"].bind("<<ListboxSelect>>", _al_elegir_carpeta)

    _biblio["lista_temas"] = tk.Listbox(
        cuerpo, bg="#151a24", fg="white",
        selectbackground="#2f3a4d", selectforeground="white",
        relief="flat", highlightthickness=1, highlightbackground="#2b3548",
        font=(E.FUENTE_UI, 10), exportselection=False,
    )
    _biblio["lista_temas"].pack(side="left", fill="both", expand=True)
    _biblio["lista_temas"].bind("<Double-Button-1>", lambda e: _reproducir_seleccionado())
    _biblio["lista_temas"].bind("<Return>", lambda e: _reproducir_seleccionado())

    pie = tk.Frame(ventana, bg="#10141b")
    pie.pack(fill="x", padx=12, pady=(0, 12))
    _biblio["actual"] = tk.Label(
        pie, text="♪ —", bg="#10141b", fg="#8fa0bd",
        font=(E.FUENTE_UI, 9, "bold"), anchor="w",
    )
    _biblio["actual"].pack(side="left", fill="x", expand=True)
    tk.Button(
        pie, text="▶ Reproducir", bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=_reproducir_seleccionado,
    ).pack(side="left", padx=(0, 6))
    tk.Button(
        pie, text="Cerrar", bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 9), cursor="hand2",
        command=_cerrar_biblioteca,
    ).pack(side="left")

    _cargar_biblioteca()
    if not _biblio["loop"]:
        _biblio["loop"] = True
        try:
            E.ventana.after(500, _refrescar_biblioteca)
        except Exception:
            _biblio["loop"] = False
