"""Mini player de música + panel biblioteca/playlist expandible.

La barra vive al pie del panel de fuentes (transporte, título y
progreso clickeable con seek exacto) y se reconstruye con
construir_cuerpo. El botón Biblioteca expande un panel sobre la
barra (nada de popup): a la izquierda la playlist actual, a la
derecha la biblioteca (carpetas en pestañas + buscador), con drag &
drop entre lados y menú de clic derecho.
"""
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs.audio import musica as mod_musica
from consola_obs.ui import dibujo as mod_ui_dibujo

ALTURA_MINI = 82
ALTURA_PANEL = 300
INTERVALO_REFRESCO_MS = 250
COLOR_PISTA = "#242d3d"
COLOR_TIEMPO = "#8fa0bd"
COLOR_FILA_SONANDO = "#31435c"
COLOR_FONDO_TABLA = "#151a24"

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
    elif mod_musica.playlist_actual():
        _guardar_pos_carpeta()
        mod_musica.reproducir_playlist(0)
        _p["fuente"] = "playlist"
        _marcar_fuente()
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


def _alternar_modo():
    """El botón recorre repetir -> mezclar -> apagado -> repetir."""
    if not _necesita_conexion():
        return
    try:
        mod_musica.alternar_modo()
    except Exception:
        pass
    _refrescar_mini_player()


def _actualizar_flecha_biblio():
    """▲ colapsada (se abre) / ▼ expandida (se oculta)."""
    try:
        boton = _w.get("boton_biblio")
        if boton is None:
            return
        flecha = " ▼" if _p.get("visible") else " ▲"
        if _w.get("biblio_con_icono"):
            boton.config(text="Biblioteca" + flecha)
        else:
            boton.config(text="🎵 Biblioteca" + flecha)
    except Exception:
        pass


def _alternar_panel_biblioteca():
    """El botón Biblioteca expande/colapsa el panel sobre la barra."""
    if not _panel_vivo():
        return
    if _p.get("visible"):
        try:
            _p["marco"].pack_forget()
        except Exception:
            pass
        _p["visible"] = False
        try:
            mod_musica._flush_duraciones(forzar=True)
        except Exception:
            pass
    else:
        try:
            _p["marco"].pack(side="bottom", fill="x")
        except Exception:
            return
        _p["visible"] = True
        _recargar_panel()
    _actualizar_flecha_biblio()


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
            # OJO: height en píxeles solo vale con imagen; en texto va
            # en líneas (28 serían 28 renglones: el botón gigante).
            _w["play"].config(image="", text="▶", width=3, height=1)
        dur = float(snap.get("duracion_ms") or 0.0)
        cur = float(snap.get("cursor_ms") or 0.0)
        _w["tiempos"].config(
            text=f"{mod_musica.formatear_ms(cur)} / {mod_musica.formatear_ms(dur)}"
        )
        _dibujar_progreso(cur / dur if dur > 0 else 0.0)
        modo = snap.get("modo") or ("repetir" if snap.get("repetir") else "off")
        # Un solo icono para los 3 estados: apagado oscuro, repetir
        # gris seleccionado, mezclar con el acento del diseño.
        if _w.get("img_mezclar") is not None:
            _w["repetir"].config(image=_w["img_mezclar"], text="",
                                 width=34, height=28,
                                 bg={"mezclar": E.color_acento(),
                                     "repetir": "#3b4a63"}.get(modo, "#242d3d"))
        elif modo == "mezclar":
            _w["repetir"].config(image="", text="🔀", width=3, height=1,
                                 bg=E.color_acento(), fg="white")
        else:
            _w["repetir"].config(image="", text="🔁", width=3, height=1,
                                 bg=(E.color_acento() if modo == "repetir" else "#242d3d"),
                                 fg="white")
    except Exception:
        pass
    try:
        _refrescar_panel()
    except Exception:
        pass
    try:
        E.ventana.after(INTERVALO_REFRESCO_MS, _refrescar_mini_player)
    except Exception:
        _loop["en_marcha"] = False


def construir_mini_player():
    """Crea la barra al pie del panel de fuentes (se llama al final de
    construir_cuerpo, así sobrevive a cambios de tema/diseño). El
    panel biblioteca se construye oculto acá mismo."""
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
    # Modo (repetir/mezclar/off): el icono shuffle es para mezclar;
    # repetir usa el emoji para distinguirse.
    _w["img_mezclar"] = _icono_barra("menu_barra_repetir.svg")
    if _w["img_mezclar"] is None:
        _w["repetir"] = _boton_transporte(fila, "🔁", _alternar_modo)
    else:
        _w["repetir"] = tk.Button(
            fila, image=_w["img_mezclar"], width=34, height=28, bg="#242d3d",
            activebackground="#2f3a4d", relief="flat", bd=0, cursor="hand2",
            command=_alternar_modo,
        )
        _w["repetir"].pack(side="left", padx=1)

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
        texto_biblio, img_biblio = "🎵 Biblioteca ▲", ""
        _w["biblio_con_icono"] = False
    else:
        texto_biblio, img_biblio = "Biblioteca ▲", _foto_nota
        _w["biblio_con_icono"] = True
    _w["boton_biblio"] = tk.Button(
        fila, text=texto_biblio, image=img_biblio, compound="left",
        bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=_alternar_panel_biblioteca,
    )
    _w["boton_biblio"].pack(side="left")

    _w["progreso"] = tk.Canvas(
        marco, height=12, bg=COLOR_PISTA, highlightthickness=0, cursor="hand2"
    )
    _w["progreso"].pack(side="top", fill="x", padx=10, pady=(2, 6))
    _w["progreso"].bind("<Button-1>", _clic_progreso)

    _construir_panel()

    if not _loop["en_marcha"]:
        _loop["en_marcha"] = True
        try:
            E.ventana.after(INTERVALO_REFRESCO_MS, _refrescar_mini_player)
        except Exception:
            _loop["en_marcha"] = False


# ------------------------------------------------------------------
# Panel biblioteca/playlist expandible (sin popup)
# ------------------------------------------------------------------
# Se despliega sobre la mini barra: playlist actual a la izquierda,
# biblioteca (pestañas + buscador) a la derecha. Drag & drop entre
# lados para agregar/sacar/reordenar, o clic derecho. Tablas estilo
# Spotify: # | Título | Álbum (= carpeta) | Agregado | duración.
# Las duraciones las rellena un único obrero de fondo con cola
# persistente (ver _asegurar_duraciones): repintar no lo reinicia.
from collections import deque as _deque

_p = {"marco": None, "visible": False, "tab": "Recientes", "tabs": [],
      "rels_biblio": [], "rels_playlist": [],
      "tree_biblio": None, "tree_playlist": None, "busqueda": "",
      # Fuente en reproducción: "carpeta" (directo desde biblioteca,
      # SIN tocar la playlist) o "playlist" (panel). El contexto de
      # carpeta guarda tab + lista + posición para retomar; el de
      # playlist, solo la posición (la lista persiste en config).
      "fuente": None, "fuente_tab": None,
      "ctx_biblio": {"tab": None, "rels": [], "idx": 0},
      "ctx_playlist_idx": 0}
_cola_dur = _deque()
_en_cola_dur = set()
_fallos_dur = set()
_lock_dur = threading.Lock()
_estado_dur = {"activo": False}
_dnd = {"origen": None, "iid": None, "x0": 0, "y0": 0, "activo": False}

COLUMNAS_TABLA = ("n", "titulo", "album", "fecha", "dur")
COLUMNAS_PLAYLIST = ("n", "titulo", "album")
TITULOS_TABLA = {"n": "#", "titulo": "Título", "album": "Álbum",
                 "fecha": "Agregado", "dur": "🕒"}
ANCHOS_TABLA = {"n": 28, "titulo": 260, "album": 90, "fecha": 92, "dur": 56}


def _panel_vivo():
    try:
        return bool(_p.get("marco") and _p["marco"].winfo_exists())
    except Exception:
        return False


def _titulo_rel(rel):
    try:
        return os.path.splitext(os.path.basename(rel))[0]
    except Exception:
        return rel


def _estilo_tablas():
    try:
        estilo = getattr(E, "_estilo_scrollbar", None)
        if estilo is None:
            return
        estilo.configure("Musica.Treeview", background="#151a24",
                         fieldbackground="#151a24", foreground="white",
                         rowheight=24, borderwidth=0)
        estilo.configure("Musica.Treeview.Heading", background="#1b2230",
                         foreground="#8fa0bd", font=(E.FUENTE_UI, 9, "bold"))
        estilo.map("Musica.Treeview", background=[("selected", "#2f3a4d")],
                   foreground=[("selected", "white")])
    except Exception:
        pass


def _crear_tabla(padre, compacta=False):
    """Tabla estilo Spotify. Compacta (playlist: sin fecha ni duración)
    o completa (biblioteca, con scroll horizontal)."""
    columnas = COLUMNAS_PLAYLIST if compacta else COLUMNAS_TABLA
    tree = ttk.Treeview(padre, columns=columnas, show="headings",
                        style="Musica.Treeview", selectmode="browse")
    for col in columnas:
        tree.heading(col, text=TITULOS_TABLA[col])
        tree.column(col, width=ANCHOS_TABLA[col],
                    stretch=(col == "titulo"),
                    anchor="w" if col == "titulo" else "center")
    tree.tag_configure("sonando", background=COLOR_FILA_SONANDO)
    return tree


def _filas_tabla(tree, rels, compacta=False):
    """Llena la tabla; devuelve la lista tal cual (para mapear iid)."""
    try:
        for iid in tree.get_children():
            tree.delete(iid)
    except Exception:
        return []
    for i, rel in enumerate(rels):
        try:
            if compacta:
                tree.insert("", "end", iid=str(i), values=(
                    i + 1, _titulo_rel(rel), mod_musica.album_de_rel(rel)))
            else:
                dur = mod_musica.duracion_cacheada(rel)
                tree.insert("", "end", iid=str(i), values=(
                    i + 1, _titulo_rel(rel), mod_musica.album_de_rel(rel),
                    mod_musica.fecha_de_archivo(mod_musica.ruta_absoluta(rel)),
                    mod_musica.formatear_ms(dur) if dur else "--:--"))
        except Exception:
            pass
    return list(rels)


def _temas_recientes_existentes():
    try:
        from consola_obs import rutas as _R
        return [r for r in mod_musica.recientes()
                if os.path.isfile(os.path.join(_R.CARPETA_MUSICA, r))]
    except Exception:
        return []


def _pintar_tabs(biblioteca):
    try:
        for w in _p["marco_tabs"].winfo_children():
            w.destroy()
    except Exception:
        return
    tabs = ["Recientes"] + sorted(biblioteca)
    _p["tabs"] = tabs
    if _p.get("tab") not in tabs:
        _p["tab"] = "Recientes"
    for nombre in tabs:
        n = (len(_temas_recientes_existentes()) if nombre == "Recientes"
             else len(biblioteca.get(nombre, [])))
        boton = tk.Button(
            _p["marco_tabs"], text=f"{nombre} ({n})",
            bg=("#3b4a63" if nombre == _p["tab"] else "#242d3d"), fg="white",
            activebackground="#2f3a4d", activeforeground="white",
            relief="flat", bd=0, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
            command=lambda t=nombre: _elegir_tab(t),
        )
        boton.pack(side="left", padx=2)
        # Doble clic en la pestaña = suena toda la carpeta desde el
        # inicio, sin mover nada a la playlist actual.
        boton.bind("<Double-Button-1>",
                   lambda e, t=nombre: _reproducir_tab_completa(t))
    _marcar_fuente()


def _reproducir_tab_completa(nombre):
    """Doble clic en pestaña: suena toda esa carpeta desde el inicio,
    SIN tocar la playlist actual."""
    if not _necesita_conexion():
        return
    try:
        temas = _temas_de_tab(_p.get("biblioteca", {}), nombre)
    except Exception:
        temas = []
    if not temas:
        return
    _guardar_pos_playlist()
    _p["fuente"] = "carpeta"
    _p["fuente_tab"] = nombre
    _p["ctx_biblio"] = {"tab": nombre, "rels": list(temas), "idx": 0}
    mod_musica.reproducir_sesion(list(temas), 0)
    _marcar_fuente()


def _guardar_pos_playlist():
    """Recuerda dónde iba la playlist (para retomar al volver)."""
    try:
        snap = mod_musica.estado_actual()
        pls = mod_musica.playlist_actual()
        if snap.get("rel") in pls:
            _p["ctx_playlist_idx"] = pls.index(snap["rel"])
    except Exception:
        pass


def _guardar_pos_carpeta():
    """Recuerda dónde iba la carpeta (para retomar al volver)."""
    try:
        snap = mod_musica.estado_actual()
        ctx = _p.get("ctx_biblio") or {}
        rels = ctx.get("rels") or []
        if snap.get("rel") in rels:
            ctx["idx"] = rels.index(snap["rel"])
    except Exception:
        pass


def _elegir_tab(nombre):
    _p["tab"] = nombre
    _marcar_fuente()
    _pintar_tabla_biblio()


def _temas_de_tab(biblioteca, tab):
    if tab == "Recientes":
        return _temas_recientes_existentes()
    return list(biblioteca.get(tab, []))


def _mtime_rel(rel):
    try:
        return os.path.getmtime(mod_musica.ruta_absoluta(rel))
    except Exception:
        return 0.0


def _vista_biblio_ordenada(temas):
    """Aplica el orden de la cabecera clickeada (toggle asc/desc)."""
    o = _p.get("orden_biblio") or {"col": None, "desc": False}
    col, desc = o.get("col"), bool(o.get("desc"))
    try:
        if col == "titulo":
            return sorted(temas, key=lambda r: _titulo_rel(r).lower(), reverse=desc)
        if col == "album":
            return sorted(temas, key=lambda r: (mod_musica.album_de_rel(r).lower(),
                                                _titulo_rel(r).lower()), reverse=desc)
        if col == "fecha":
            return sorted(temas, key=_mtime_rel, reverse=desc)
        if col == "n" and desc:
            return list(reversed(temas))
    except Exception:
        pass
    return list(temas)


def _ordenar_biblio(col):
    """Clic en cabecera de la biblioteca: ordena (segundo clic invierte)."""
    o = _p.get("orden_biblio") or {"col": None, "desc": False}
    if o.get("col") == col:
        o["desc"] = not o.get("desc", False)
    else:
        o = {"col": col, "desc": False}
    _p["orden_biblio"] = o
    try:
        tree = _p.get("tree_biblio")
        if tree is not None:
            for c in ("n", "titulo", "album", "fecha"):
                marca = ""
                if o.get("col") == c:
                    marca = " ▼" if o.get("desc") else " ▲"
                tree.heading(c, text=TITULOS_TABLA[c] + marca)
    except Exception:
        pass
    _pintar_tabla_biblio()


def _pintar_tabla_biblio():
    if not _panel_vivo():
        return
    biblioteca = _p.get("biblioteca", {})
    filtro = (_p.get("busqueda", "").strip().lower()
              if isinstance(_p.get("busqueda"), str) else "")
    if filtro:
        # Búsqueda GLOBAL por título en toda la biblioteca,
        # no solo la pestaña actual.
        temas = []
        try:
            for carpeta in sorted(biblioteca):
                temas.extend(biblioteca[carpeta])
        except Exception:
            pass
        temas = [t for t in temas if filtro in _titulo_rel(t).lower()]
    else:
        temas = _temas_de_tab(biblioteca, _p.get("tab") or "Recientes")
    _p["rels_biblio"] = _filas_tabla(_p["tree_biblio"], _vista_biblio_ordenada(temas))
    if not temas:
        try:
            if not biblioteca:
                msg = "Poné mp3 en assets/Musica/<carpeta>/"
            elif filtro:
                msg = f"Sin resultados para '{_p.get('busqueda', '').strip()}'."
            elif (_p.get("tab") or "Recientes") == "Recientes":
                msg = "Todavía no hay recientes."
            else:
                msg = "Carpeta vacía."
            _p["tree_biblio"].insert("", "end", iid="vacia",
                                     values=("", msg, "", "", ""))
        except Exception:
            pass


def _pintar_tabla_playlist():
    if not _panel_vivo():
        return
    _p["rels_playlist"] = _filas_tabla(_p["tree_playlist"],
                                       mod_musica.playlist_actual(),
                                       compacta=True)
    _resaltar_actual()


def _marcar_fuente():
    """Pinta qué fuente suena: la pestaña de la carpeta con fondo de
    acento (verde/azul según diseño), o la cabecera de la playlist.
    La pestaña seleccionada (navegación) lleva #3b4a63."""
    try:
        fuente = _p.get("fuente")
        fuente_tab = _p.get("fuente_tab")
        marco = _p.get("marco_tabs")
        if marco is not None:
            for w in marco.winfo_children():
                try:
                    base = w.cget("text").rsplit(" (", 1)[0]
                except Exception:
                    continue
                if not base:
                    continue
                if fuente == "carpeta" and base == fuente_tab:
                    w.config(bg=E.color_acento(), fg="#0c111b")
                elif base == _p.get("tab"):
                    w.config(bg="#3b4a63", fg="white")
                else:
                    w.config(bg="#242d3d", fg="white")
    except Exception:
        pass
    try:
        titulo = _p.get("titulo_playlist")
        if titulo is not None:
            if _p.get("fuente") == "playlist":
                titulo.config(bg=E.color_acento(), fg="#0c111b")
            else:
                titulo.config(bg=E.color_barra_titulo(), fg="white")
    except Exception:
        pass


def _resaltar_actual():
    """Resalta el tema sonando en AMBAS tablas (playlist y biblioteca)."""
    if not _panel_vivo() or not _p.get("visible"):
        return
    try:
        actual = mod_musica.estado_actual().get("rel")
    except Exception:
        actual = None
    for clave, arbol in (("rels_playlist", _p.get("tree_playlist")),
                         ("rels_biblio", _p.get("tree_biblio"))):
        try:
            if arbol is None:
                continue
            rels = _p.get(clave, [])
            for iid in arbol.get_children():
                try:
                    arbol.item(iid, tags=())
                except Exception:
                    pass
            if actual and actual in rels:
                try:
                    arbol.item(str(rels.index(actual)), tags=("sonando",))
                except Exception:
                    pass
        except Exception:
            pass


def _refrescar_panel():
    if not _panel_vivo() or not _p.get("visible"):
        return
    _resaltar_actual()


def _asegurar_duraciones(toda=False):
    """Encola lo que falta y garantiza un único obrero de fondo. Con
    toda=True encola la biblioteca ENTERA (al abrir), no solo la vista:
    así se detectan las duraciones de todas las canciones solas."""
    try:
        rels = list(_p.get("rels_biblio", [])) + list(_p.get("rels_playlist", []))
        if toda:
            try:
                biblio = _p.get("biblioteca", {}) or mod_musica.escanear_biblioteca()
                for temas in biblio.values():
                    rels.extend(temas)
            except Exception:
                pass
    except Exception:
        return
    try:
        with _lock_dur:
            for rel in rels:
                if (rel not in _en_cola_dur and rel not in _fallos_dur
                        and mod_musica.duracion_cacheada(rel) is None):
                    _en_cola_dur.add(rel)
                    _cola_dur.append(rel)
            if not _cola_dur or _estado_dur.get("activo"):
                return
            _estado_dur["activo"] = True
    except Exception:
        return
    threading.Thread(target=_obrero_duraciones, daemon=True).start()


def _obrero_duraciones():
    try:
        while True:
            try:
                with _lock_dur:
                    if not _cola_dur:
                        return
                    rel = _cola_dur.popleft()
            except Exception:
                return
            try:
                ms = mod_musica.duracion_de(rel)
            except Exception:
                ms = None
            with _lock_dur:
                _en_cola_dur.discard(rel)
                if not ms:
                    _fallos_dur.add(rel)
            if ms:
                try:
                    E.ventana.after(0, _actualizar_duracion_fila, rel, ms)
                except Exception:
                    return
    finally:
        try:
            with _lock_dur:
                _estado_dur["activo"] = False
        except Exception:
            pass
        # Por si entró trabajo nuevo al final: reasegura un obrero.
        try:
            _asegurar_duraciones()
        except Exception:
            pass


def _actualizar_duracion_fila(rel, ms):
    if not _panel_vivo():
        return
    texto = mod_musica.formatear_ms(ms)
    for clave, arbol in (("rels_biblio", _p.get("tree_biblio")),
                         ("rels_playlist", _p.get("tree_playlist"))):
        try:
            rels = _p.get(clave, [])
            if rel in rels and arbol is not None:
                iid = str(rels.index(rel))
                vals = list(arbol.item(iid, "values"))
                if len(vals) < 5:
                    continue
                vals[4] = texto
                arbol.item(iid, values=vals)
        except Exception:
            pass


def _recargar_panel():
    """Reescanea y repinta pestañas + ambas tablas. Conserva la tab."""
    if not _panel_vivo():
        return
    try:
        actual = mod_musica.playlist_actual()
        if actual != mod_musica.obtener_playlist():
            mod_musica.definir_playlist(actual)
        elif list(mod_musica._cola) != actual:
            mod_musica.definir_playlist(actual)
    except Exception:
        pass
    _p["biblioteca"] = mod_musica.escanear_biblioteca()
    _pintar_tabs(_p["biblioteca"])
    _pintar_tabla_biblio()
    _pintar_tabla_playlist()
    _asegurar_duraciones(toda=True)


def _al_buscar_panel(event=None):
    if not _panel_vivo():
        return
    try:
        _p["busqueda"] = _p["entrada_busqueda"].get()
    except Exception:
        _p["busqueda"] = ""
    _pintar_tabla_biblio()
    _asegurar_duraciones()


def _reproducir_vista_biblio(indice):
    if not _necesita_conexion():
        return
    vista = list(_p.get("rels_biblio", []))
    try:
        indice = int(indice)
    except Exception:
        return
    if 0 <= indice < len(vista):
        _guardar_pos_playlist()
        _p["fuente"] = "carpeta"
        _p["fuente_tab"] = _p.get("tab")
        _p["ctx_biblio"] = {"tab": _p.get("tab"), "rels": list(vista),
                            "idx": indice}
        mod_musica.reproducir_sesion(vista, indice)
        _marcar_fuente()


def _reproducir_indice_playlist(indice):
    if not _necesita_conexion():
        return
    try:
        _guardar_pos_carpeta()
        _p["fuente"] = "playlist"
        mod_musica.reproducir_playlist(int(indice))
        _marcar_fuente()
    except Exception:
        pass


def _agregar_rel(rel):
    if not isinstance(rel, str) or not rel:
        return
    try:
        if rel in mod_musica.playlist_actual():
            try:
                messagebox.showwarning(
                    "Ya está en la playlist",
                    f"\"{_titulo_rel(rel)}\" ya está en la playlist actual.")
            except Exception:
                pass
            return
        if mod_musica.agregar_a_playlist(rel):
            _pintar_tabla_playlist()
            _asegurar_duraciones()
    except Exception:
        pass


def _menu_biblio(event):
    tree = _p.get("tree_biblio")
    if tree is None:
        return
    try:
        iid = tree.identify_row(event.y)
        if iid in ("", "vacia"):
            return
        idx = int(iid)
        rel = _p.get("rels_biblio", [])[idx]
    except Exception:
        return
    try:
        tree.selection_set(iid)
    except Exception:
        pass
    menu = tk.Menu(E.ventana, tearoff=0, bg="#151a24", fg="white",
                   activebackground="#323b4c", activeforeground="white")
    menu.add_command(label="Agregar a la playlist",
                     command=lambda: _agregar_rel(rel))
    menu.add_command(label="Reproducir ahora",
                     command=lambda: _reproducir_vista_biblio(idx))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _menu_playlist(event):
    tree = _p.get("tree_playlist")
    if tree is None:
        return
    try:
        iid = tree.identify_row(event.y)
        if iid in ("", "vacia"):
            return
        idx = int(iid)
    except Exception:
        return
    try:
        tree.selection_set(iid)
    except Exception:
        pass
    menu = tk.Menu(E.ventana, tearoff=0, bg="#151a24", fg="white",
                   activebackground="#323b4c", activeforeground="white")
    menu.add_command(label="Reproducir",
                     command=lambda: _reproducir_indice_playlist(idx))
    menu.add_command(label="Sacar de la playlist",
                     command=lambda: (_sacar_indice_playlist(idx)))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _alternar_fuente():
    """Botón ⇄: intercambia qué suena (playlist actual <-> carpeta),
    retomando cada lado donde iba."""
    if not _necesita_conexion():
        return
    try:
        if _p.get("fuente") == "carpeta":
            _guardar_pos_carpeta()
            pls = mod_musica.playlist_actual()
            if not pls:
                try:
                    messagebox.showinfo("Playlist vacía",
                                        "La playlist actual está vacía: arrastrá temas desde la biblioteca.")
                except Exception:
                    pass
                return
            try:
                idx = max(0, min(int(_p.get("ctx_playlist_idx", 0)), len(pls) - 1))
            except Exception:
                idx = 0
            _p["fuente"] = "playlist"
            mod_musica.reproducir_playlist(idx)
        else:
            ctx = _p.get("ctx_biblio") or {}
            try:
                rels = [r for r in (ctx.get("rels") or [])
                        if os.path.isfile(mod_musica.ruta_absoluta(r))]
            except Exception:
                rels = []
            if not rels:
                try:
                    messagebox.showinfo("Sin carpeta",
                                        "Primero reproducí una carpeta (doble clic en una pestaña o un tema).")
                except Exception:
                    pass
                return
            _guardar_pos_playlist()
            try:
                idx = max(0, min(int(ctx.get("idx", 0)), len(rels) - 1))
            except Exception:
                idx = 0
            _p["fuente"] = "carpeta"
            _p["fuente_tab"] = ctx.get("tab")
            mod_musica.reproducir_sesion(rels, idx)
        _marcar_fuente()
    except Exception:
        pass


def _sacar_indice_playlist(idx):
    try:
        if mod_musica.sacar_de_playlist(int(idx)):
            _pintar_tabla_playlist()
    except Exception:
        pass


def _dnd_press(cual, event):
    tree = _p["tree_biblio"] if cual == "biblio" else _p["tree_playlist"]
    if tree is None:
        _dnd.update({"origen": None, "iid": None, "activo": False})
        return
    try:
        iid = tree.identify_row(event.y)
    except Exception:
        iid = ""
    if iid in ("", "vacia"):
        _dnd.update({"origen": None, "iid": None, "activo": False})
        return
    _dnd.update({"origen": cual, "iid": iid, "x0": event.x_root,
                 "y0": event.y_root, "activo": False})


def _dnd_move(event):
    if not _dnd.get("origen"):
        return
    try:
        dx = abs(event.x_root - _dnd.get("x0", 0))
        dy = abs(event.y_root - _dnd.get("y0", 0))
        if dx > C.UMBRAL_ARRASTRE_PX or dy > C.UMBRAL_ARRASTRE_PX:
            _dnd["activo"] = True
    except Exception:
        pass


def _arbol_bajo_puntero(x_root, y_root):
    try:
        widget = E.ventana.winfo_containing(x_root, y_root)
    except Exception:
        return None
    while widget is not None:
        if widget is _p.get("tree_biblio"):
            return "biblio"
        if widget is _p.get("tree_playlist"):
            return "playlist"
        widget = widget.master
    return None


def _dnd_release(event):
    origen, iid, activo = _dnd.get("origen"), _dnd.get("iid"), _dnd.get("activo")
    _dnd.update({"origen": None, "iid": None, "activo": False})
    if not origen or not iid:
        return
    try:
        idx_origen = int(iid)
    except Exception:
        return
    if not activo:
        # Clic simple: en playlist reproduce; en biblioteca también
        # SI ya se viene reproduciendo desde una carpeta: así se
        # cambia de tema con un clic. En silencio si no hay conexión,
        # para no naggear al seleccionar.
        destino = _arbol_bajo_puntero(event.x_root, event.y_root)
        if not E.conectado:
            return
        if origen == "playlist" and destino == "playlist":
            _reproducir_indice_playlist(idx_origen)
        elif (origen == "biblio" and destino == "biblio"
              and _p.get("fuente") == "carpeta"):
            _reproducir_vista_biblio(idx_origen)
        return
    destino = _arbol_bajo_puntero(event.x_root, event.y_root)
    if destino is None:
        return
    tree_dest = _p["tree_playlist"] if destino == "playlist" else _p["tree_biblio"]
    try:
        y_dest = event.y_root - tree_dest.winfo_rooty()
        iid_dest = tree_dest.identify_row(y_dest)
        en_encabezado = False
        if iid_dest not in ("", "vacia"):
            idx_dest = int(iid_dest)
        else:
            # Sobre el encabezado = al principio; debajo de todo = al final.
            try:
                caja0 = tree_dest.bbox("0")
            except Exception:
                caja0 = ""
            if caja0 and y_dest < caja0[1]:
                idx_dest, en_encabezado = 0, True
            else:
                idx_dest = None
    except Exception:
        idx_dest, en_encabezado = None, False
    try:
        if origen == "biblio" and destino == "playlist":
            # Agregar es siempre al final (arrastre o clic derecho).
            rels = _p.get("rels_biblio", [])
            if 0 <= idx_origen < len(rels):
                _agregar_rel(rels[idx_origen])
        elif origen == "playlist" and destino == "biblio":
            _sacar_indice_playlist(idx_origen)
        elif origen == "playlist" and destino == "playlist":
            if idx_dest is None:
                idx_dest = len(mod_musica.playlist_actual()) - 1
            if mod_musica.mover_en_playlist(idx_origen, idx_dest):
                _pintar_tabla_playlist()
    except Exception:
        pass


def _atajos_arbol(tree, cual):
    tree.bind("<ButtonPress-1>", lambda e: _dnd_press(cual, e))
    tree.bind("<B1-Motion>", _dnd_move)
    tree.bind("<ButtonRelease-1>", _dnd_release)
    # Ruedita: scroll vertical (en la playlist reemplaza a la
    # scrollbar, que se sacó a pedido).
    tree.bind("<MouseWheel>",
              lambda e, t=tree: t.yview_scroll(int(-1 * (e.delta / 120)), "units"))
    if cual == "biblio":
        tree.bind("<Shift-MouseWheel>",
                  lambda e, t=tree: t.xview_scroll(int(-1 * (e.delta / 120)), "units"))
        tree.bind("<Double-Button-1>",
                  lambda e: _reproducir_vista_biblio(_indice_bajo_puntero(tree, e)))
        tree.bind("<Return>", lambda e: _reproducir_vista_biblio(_indice_foco(tree)))
        tree.bind("<Button-3>", _menu_biblio)
    else:
        # Sin doble clic: el clic simple ya reproduce (ver _dnd_release).
        tree.bind("<Return>", lambda e: _reproducir_indice_playlist(_indice_foco(tree)))
        tree.bind("<Button-3>", _menu_playlist)


def _indice_bajo_puntero(tree, event):
    try:
        iid = tree.identify_row(event.y)
        return int(iid) if iid not in ("", "vacia") else -1
    except Exception:
        return -1


def _indice_foco(tree):
    try:
        return int(tree.focus()) if tree.focus() not in ("", "vacia") else -1
    except Exception:
        return -1


def _construir_panel():
    """Arma el panel oculto (se muestra con el botón Biblioteca). Se
    llama al final de construir_mini_player."""
    try:
        viejo = _p.get("marco")
        if viejo is not None:
            try:
                viejo.destroy()
            except Exception:
                pass
    except Exception:
        pass
    _p.update({"marco": None, "visible": False, "tab": "Recientes",
               "tabs": [], "rels_biblio": [], "rels_playlist": [],
               "tree_biblio": None, "tree_playlist": None,
               "busqueda": "", "orden_biblio": {"col": None, "desc": False}})
    _estilo_tablas()

    marco = tk.Frame(E.marco_fuentes, bg=E.color_barra_titulo(), height=300)
    marco.pack_propagate(False)
    _p["marco"] = marco

    tk.Frame(marco, bg=E.color_acento(), height=2).pack(side="top", fill="x")

    fila_busqueda = tk.Frame(marco, bg=E.color_barra_titulo())
    fila_busqueda.pack(side="top", fill="x", padx=8, pady=(6, 4))
    _foto_buscar = _icono_barra("menu_barra_buscar.svg")
    if _foto_buscar is None:
        tk.Label(fila_busqueda, text="🔍", bg=E.color_barra_titulo(), fg="#8fa0bd",
                 font=(E.FUENTE_UI, 10)).pack(side="left")
    else:
        tk.Label(fila_busqueda, image=_foto_buscar, bg=E.color_barra_titulo()).pack(
            side="left", padx=(0, 4))
    _p["entrada_busqueda"] = tk.Entry(
        fila_busqueda, bg="#1b2230", fg="white", insertbackground="white",
        relief="flat", highlightthickness=1, highlightbackground="#2b3548",
        font=(E.FUENTE_UI, 10),
    )
    _p["entrada_busqueda"].pack(side="left", fill="x", expand=True, ipady=3)
    _p["entrada_busqueda"].bind("<KeyRelease>", _al_buscar_panel)
    _boton_icono(fila_busqueda, "menu_barra_actualizar.svg", "↻", _recargar_panel)

    _p["marco_tabs"] = tk.Frame(marco, bg=E.color_barra_titulo())
    _p["marco_tabs"].pack(side="top", fill="x", padx=8, pady=(0, 4))

    cuerpo = tk.Frame(marco, bg=E.color_barra_titulo())
    cuerpo.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))

    # Divisor movible entre playlist y biblioteca (se arrastra a
    # gusto como el divisor principal de la ventana).
    divisor = tk.PanedWindow(cuerpo, orient="horizontal", bg="#1b2230",
                             sashwidth=8, sashrelief="flat", bd=0,
                             opaqueresize=True)
    divisor.pack(fill="both", expand=True)
    _p["divisor"] = divisor

    col_izq = tk.Frame(divisor, bg=E.color_barra_titulo())
    divisor.add(col_izq, minsize=200, stretch="always")
    cab_pls = tk.Frame(col_izq, bg=E.color_barra_titulo())
    cab_pls.pack(fill="x")
    _p["titulo_playlist"] = tk.Label(cab_pls, text="▶ Playlist actual",
                                     bg=E.color_barra_titulo(),
                                     fg="white", font=(E.FUENTE_UI, 9, "bold"), anchor="w")
    _p["titulo_playlist"].pack(side="left", fill="x", expand=True)
    tk.Button(
        cab_pls, text="⇄ Fuente", bg="#242d3d", fg="white",
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=_alternar_fuente,
    ).pack(side="right")
    marco_tree_pls = tk.Frame(col_izq, bg=E.color_barra_titulo())
    marco_tree_pls.pack(fill="both", expand=True)
    _p["tree_playlist"] = _crear_tabla(marco_tree_pls, compacta=True)
    _p["tree_playlist"].pack(side="left", fill="both", expand=True)
    # Sin scrollbar vertical: con la ruedita alcanza.
    _atajos_arbol(_p["tree_playlist"], "playlist")

    col_der = tk.Frame(divisor, bg=E.color_barra_titulo())
    divisor.add(col_der, minsize=260, stretch="always")
    tk.Label(col_der, text="Biblioteca", bg=E.color_barra_titulo(),
             fg="white", font=(E.FUENTE_UI, 9, "bold"), anchor="w").pack(fill="x")
    marco_tree_bib = tk.Frame(col_der, bg=E.color_barra_titulo())
    marco_tree_bib.pack(fill="both", expand=True)
    _p["tree_biblio"] = _crear_tabla(marco_tree_bib)
    _p["tree_biblio"].pack(side="left", fill="both", expand=True)
    for _col in ("n", "titulo", "album", "fecha"):
        _p["tree_biblio"].heading(_col, command=lambda c=_col: _ordenar_biblio(c))
    # Sin scrollbar horizontal: la columna Título estira y con
    # Shift+rueda igual se puede mover de costado si hace falta.
    _atajos_arbol(_p["tree_biblio"], "biblio")
