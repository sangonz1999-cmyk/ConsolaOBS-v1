import os
import tkinter as tk

from consola_obs.compat import HAY_PILLOW, Image, ImageDraw, ImageOps, ImageTk
from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import rutas as R
from consola_obs.ui import dibujo as mod_ui_dibujo


def _redibujar_cabecera(event=None):
    # Reposicionar el frame embebido (título, chip de estado, etc.) es
    # barato — no crea nada nuevo — así que esto se hace en cada evento,
    # sin esperar a nada, para que el ancho del contenido siga a la
    # ventana sin demora.
    ancho = E.cabecera_fondo.winfo_width() or E.ventana.winfo_width() or C.ANCHO_VENTANA_REFERENCIA
    E.cabecera_fondo.coords(E._ventana_cabecera_id, 0, 0)
    E.cabecera_fondo.itemconfig(E._ventana_cabecera_id, width=ancho, height=C.ALTO_CABECERA)
    # Gate ESPACIAL para el degradado: si no se movió lo suficiente, ni
    # se reprograma (ver SALTO_MINIMO_REDIBUJO_PX en constantes).
    ultimo = getattr(E.cabecera_fondo, "_ult_repintado", (0, 0))
    if abs(ancho - ultimo[0]) < C.SALTO_MINIMO_REDIBUJO_PX:
        return
    E.cabecera_fondo._ult_repintado = (ancho, E.cabecera_fondo.winfo_height())

    # Lo caro es el degradado de fondo: borra y vuelve a crear ~108
    # rectángulos (franja del degradado vertical + franja de acento).
    # Antes esto se hacía en CADA evento <Configure>, sin ningún límite
    # — y mientras se arrastra el borde de la ventana, el sistema
    # operativo manda decenas de esos eventos por segundo. Cada uno
    # disparaba una recreación completa del degradado, compitiendo por
    # CPU justo en el momento en que la interfaz necesita responder
    # rápido: esa era una de las causas concretas del lag/tildado
    # durante el arrastre (además de que, al estar todo tapado por el
    # velo mientras se arrastra, redibujar el degradado en ese momento
    # ni siquiera se llega a ver). Ahora se throttlea igual que el
    # resto de los redimensionados de la app: se espera a que la
    # cabecera deje de cambiar de ancho antes de redibujar el
    # degradado, en vez de hacerlo en cada cuadro.
    if E._trabajo_redibujado_cabecera["id"] is not None:
        E.ventana.after_cancel(E._trabajo_redibujado_cabecera["id"])
    E._trabajo_redibujado_cabecera["id"] = E.ventana.after(120, _redibujar_degradado_cabecera)


def _redibujar_degradado_cabecera():
    E._trabajo_redibujado_cabecera["id"] = None
    E.cabecera_fondo.delete("fondo_cabecera")
    ancho = E.cabecera_fondo.winfo_width() or E.ventana.winfo_width() or C.ANCHO_VENTANA_REFERENCIA
    # pasos=14 en vez de 48/60: a este tamaño de franja (unos 74px de
    # alto) el ojo no distingue 14 escalones de color de 48, pero son
    # una fracción de los rectángulos a crear cada vez que se redibuja.
    ids = mod_ui_dibujo._gradiente_vertical(E.cabecera_fondo, 0, 0, ancho, C.ALTO_CABECERA, E.color_cabecera_arriba(), E.color_cabecera_abajo(), pasos=14)
    for iid in ids:
        E.cabecera_fondo.addtag_withtag("fondo_cabecera", iid)
    ids_acento = mod_ui_dibujo._gradiente_horizontal(E.cabecera_fondo, 0, C.ALTO_CABECERA - 3, ancho, C.ALTO_CABECERA, E.color_acento(), E.color_acento_oscuro(), pasos=14)
    for iid in ids_acento:
        E.cabecera_fondo.addtag_withtag("fondo_cabecera", iid)
    E.cabecera_fondo.tag_lower("fondo_cabecera")


def _geometria_faders(cx, cy, radio):
    """Medidas del ícono de Ajustes: tres faders verticales (barras con
    puntas redondeadas) con su perilla anular, la del medio arriba y las
    de los costados abajo. Todo sale en proporción a 'radio' para que el
    ícono se vea igual a cualquier tamaño."""
    ancho_barra = radio * 0.27
    medio_alto = radio * 0.92
    radio_perilla = radio * 0.36
    radio_hueco = radio * 0.145
    separacion = radio * 0.62
    barras = []
    for desplazamiento_x, y_perilla in (
        (-separacion, cy + radio * 0.30),
        (0.0, cy - radio * 0.34),
        (separacion, cy + radio * 0.30),
    ):
        x = cx + desplazamiento_x
        barras.append({
            "x": x,
            "y0": cy - medio_alto,
            "y1": cy + medio_alto,
            "y_perilla": y_perilla,
        })
    return barras, ancho_barra, radio_perilla, radio_hueco


def _dibujar_engranaje(canvas, cx, cy, radio, color="#9fb0d8"):
    """Respaldo sin Pillow: el ícono de faders dibujado con primitivas de
    Tk (queda con algún escalón en las curvas, pero sólo se usa si Pillow
    no está disponible). Conserva el nombre viejo para no tener que tocar
    los lugares donde ya se llamaba."""
    barras, ancho_barra, radio_perilla, radio_hueco = _geometria_faders(cx, cy, radio)
    for barra_icono in barras:
        canvas.create_line(
            barra_icono["x"], barra_icono["y0"], barra_icono["x"], barra_icono["y1"],
            fill=color, width=max(2, round(ancho_barra)), capstyle="round"
        )
    for barra_icono in barras:
        x, y = barra_icono["x"], barra_icono["y_perilla"]
        canvas.create_oval(
            x - radio_perilla, y - radio_perilla, x + radio_perilla, y + radio_perilla,
            fill=color, outline=""
        )
        canvas.create_oval(
            x - radio_hueco, y - radio_hueco, x + radio_hueco, y + radio_hueco,
            fill=E.color_cabecera_abajo(), outline=""
        )


def _imagen_boton_engranaje(lado, color_icono, hover=False, abierto=False):
    """Botón de Ajustes completo (placa de vidrio + ícono de faders) hecho con
    Pillow al cuádruple de resolución y reducido con LANCZOS: mismo
    tratamiento que los pads, para que la cabecera no desentone ni
    muestre bordes dentados."""
    clave = (lado, color_icono, hover, abierto)
    if clave in E._cache_engranajes:
        return E._cache_engranajes[clave]

    base = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))

    S = 4
    capa = Image.new("RGBA", (lado * S, lado * S), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(capa)
    centro = lado * S / 2
    radio = lado * S * 0.30
    barras, ancho_barra, radio_perilla, radio_hueco = _geometria_faders(centro, centro, radio)
    relleno = mod_ui_dibujo._hex_a_rgb(color_icono) + (255,)
    for barra_icono in barras:
        x = barra_icono["x"]
        # Barra con puntas redondeadas = rectángulo redondeado de radio
        # igual a la mitad de su ancho.
        dibujo.rounded_rectangle(
            [x - ancho_barra / 2, barra_icono["y0"], x + ancho_barra / 2, barra_icono["y1"]],
            radius=ancho_barra / 2, fill=relleno
        )
    for barra_icono in barras:
        x, y = barra_icono["x"], barra_icono["y_perilla"]
        dibujo.ellipse([x - radio_perilla, y - radio_perilla, x + radio_perilla, y + radio_perilla],
                       fill=relleno)
    # El agujero de cada perilla se perfora DESPUÉS de dibujar las tres,
    # pisando con alpha 0: así se ve la cara del botón a través del anillo
    # (igual que en el ícono de referencia) y no la barra que pasa detrás.
    for barra_icono in barras:
        x, y = barra_icono["x"], barra_icono["y_perilla"]
        dibujo.ellipse([x - radio_hueco, y - radio_hueco, x + radio_hueco, y + radio_hueco],
                       fill=(0, 0, 0, 0))
    capa = capa.resize((lado, lado), Image.LANCZOS)

    base.alpha_composite(capa)
    foto = ImageTk.PhotoImage(base)
    E._cache_engranajes[clave] = foto
    return foto


def _redibujar_icono_engranaje(event=None):
    # El canvas es de tamaño fijo: si viene de un Configure y no cambió
    # nada relevante, se saltea (los hover llaman sin evento y siempre
    # repintan).
    if event is not None:
        lado_ahora = E.marco_engranaje.winfo_width()
        ultimo = getattr(E.marco_engranaje, "_ult_repintado", (0, 0))
        if abs(lado_ahora - ultimo[0]) < C.SALTO_MINIMO_REDIBUJO_PX:
            return
        E.marco_engranaje._ult_repintado = (lado_ahora, E.marco_engranaje.winfo_height())
    E.marco_engranaje.delete("all")
    lado = E.marco_engranaje.winfo_width() or 46
    E.marco_engranaje.config(bg=E.color_cabecera_arriba())
    if HAY_PILLOW:
        # Con el menú abierto el ícono va en acento claro (no en negro
        # como antes): en negro se perdía contra el fondo oscuro.
        color = (E.color_acento_claro() if E._estado_engranaje["abierto"] else (
            "#d7e6ff" if E._estado_engranaje["hover"] else "#aebbd8"
        ))
        try:
            foto = _imagen_boton_engranaje(
                lado, color, E._estado_engranaje["hover"], E._estado_engranaje["abierto"]
            )
            E._imagen_engranaje["foto"] = foto
            E.marco_engranaje.create_image(0, 0, anchor="nw", image=foto)
            return
        except Exception:
            pass
    color = E.color_acento() if (E._estado_engranaje["hover"] or E._estado_engranaje["abierto"]) else "#9fb0d8"
    margen = max(2, round(lado * 0.14))
    _dibujar_engranaje(E.marco_engranaje, lado / 2, lado / 2, lado / 2 - margen, color=color)


def _hover_engranaje_dentro(event=None):
    E._estado_engranaje["hover"] = True
    _redibujar_icono_engranaje()


def _hover_engranaje_fuera(event=None):
    E._estado_engranaje["hover"] = False
    _redibujar_icono_engranaje()


def _seccion_menu(texto, padre=None):
    """Título de sección + línea separadora, para que el menú se lea
    como un panel de ajustes y no como una lista suelta de campos."""
    base = padre if padre is not None else E.barra
    contenedor = tk.Frame(base, bg=C.COLOR_MENU_FONDO)
    contenedor.pack(fill="x", padx=16, pady=(10, 2))
    tk.Label(
        contenedor, text=texto, bg=C.COLOR_MENU_FONDO, fg=C.COLOR_MENU_TITULO,
        font=(E.FUENTE_UI, 8, "bold")
    ).pack(side="left")
    linea = tk.Frame(contenedor, bg="#232c3d", height=1)
    linea.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(6, 0))
    return contenedor


def _fila_menu(texto, widget_ancho=None, padre=None):
    """Una fila 'etiqueta a la izquierda, control a la derecha'."""
    base = padre if padre is not None else E.barra
    fila = tk.Frame(base, bg=C.COLOR_MENU_FONDO)
    fila.pack(fill="x", padx=16, pady=4)
    tk.Label(
        fila, text=texto, bg=C.COLOR_MENU_FONDO, fg=C.COLOR_MENU_TEXTO,
        font=(E.FUENTE_UI, 9), width=11, anchor="w"
    ).pack(side="left")
    return fila


def _ayuda_menu(padre, texto):
    """Descripción chica gris debajo de un grupo de opciones: qué va en
    cada campo, en una línea o dos."""
    base = padre if padre is not None else E.barra
    etiqueta = tk.Label(
        base, text=texto, bg=C.COLOR_MENU_FONDO, fg="#8fa0bd",
        font=(E.FUENTE_UI, 8), wraplength=420, justify="left",
    )
    etiqueta.pack(fill="x", padx=16, pady=(0, 6))
    return etiqueta


def _entrada_menu(padre, **extras):
    entrada = tk.Entry(
        padre, bg=C.COLOR_MENU_CAMPO, fg="white", insertbackground="white", relief="flat",
        highlightthickness=1, highlightbackground="#2b3548", highlightcolor=E.color_acento(),
        font=(E.FUENTE_UI, 10), **extras
    )
    entrada.pack(side="left", fill="x", expand=True, ipady=4)
    return entrada


PESTANAS_AJUSTES = ("Conexión", "Apariencia", "Audio",
                    "Sincronización", "Actualización")


def mostrar_pestana_ajustes(nombre):
    """Muestra una pestaña de la ventana de Ajustes (lista a la
    izquierda, panel a la derecha). Nunca lanza."""
    try:
        if nombre not in PESTANAS_AJUSTES:
            nombre = PESTANAS_AJUSTES[0]
        for clave, marco in (getattr(E, "pestanas_ajustes", None) or {}).items():
            try:
                if clave == nombre:
                    marco.pack(fill="both", expand=True)
                else:
                    marco.pack_forget()
            except Exception:
                pass
        E._pestana_ajustes_actual = nombre
        try:
            lista = E.lista_pestanas_ajustes
            idx = PESTANAS_AJUSTES.index(nombre)
            lista.selection_clear(0, "end")
            lista.selection_set(idx)
            lista.see(idx)
        except Exception:
            pass
    except Exception:
        pass


def abrir_ajustes(pestana="Conexión"):
    """Abre la ventana de Ajustes en la pestaña pedida (por defecto
    Conexión, que oficia de general), centrada sobre la principal (no en
    la esquina como la deja el sistema)."""
    try:
        mostrar_pestana_ajustes(pestana)
        try:
            E.ventana.update_idletasks()
            E.ventana_ajustes.update_idletasks()
            ancho = max(E.ventana_ajustes.winfo_width(),
                        E.ventana_ajustes.winfo_reqwidth())
            alto = max(E.ventana_ajustes.winfo_height(),
                       E.ventana_ajustes.winfo_reqheight())
            x = E.ventana.winfo_rootx() + (E.ventana.winfo_width() - ancho) // 2
            y = E.ventana.winfo_rooty() + (E.ventana.winfo_height() - alto) // 2
            x = max(0, min(x, E.ventana.winfo_screenwidth() - ancho))
            y = max(0, min(y, E.ventana.winfo_screenheight() - alto))
            E.ventana_ajustes.geometry(f"+{int(x)}+{int(y)}")
        except Exception:
            pass
        E.ventana_ajustes.deiconify()
        E.ventana_ajustes.lift()
        try:
            E.ventana_ajustes.focus_force()
        except Exception:
            pass
        E._estado_engranaje["abierto"] = True
        _redibujar_icono_engranaje()
        if pestana == "Conexión":
            E.ventana_ajustes.after(80, lambda: E.entrada_host.focus_set())
    except Exception:
        pass


def _abrir_menu_ajustes():
    abrir_ajustes("Conexión")


def _cerrar_menu_ajustes(event=None):
    try:
        E.ventana_ajustes.withdraw()
    except Exception:
        pass
    try:
        E._estado_engranaje["abierto"] = False
        _redibujar_icono_engranaje()
    except Exception:
        pass


def _menu_ajustes_visible():
    try:
        return E.ventana_ajustes.state() != "withdrawn"
    except Exception:
        return False


def _alternar_menu_ajustes(event=None):
    if _menu_ajustes_visible():
        _cerrar_menu_ajustes()
    else:
        _abrir_menu_ajustes()


def _clic_fuera_del_menu(event=None):
    """OBSOLETA: con la ventana de Ajustes con marco propio ya no se
    cierra al tocar afuera (se cierra con ✕, Escape o el engranaje). Se
    deja vacía por si algo viejo todavía la llama."""
    return


def _seguir_ventana_con_menu(event=None):
    """OBSOLETA: la ventana de Ajustes es independiente y no sigue a la
    principal. Se deja vacía por compatibilidad."""
    return


def repintar_logo_cabecera():
    """Dibuja el logo: el PNG si existe, o el ecualizador con el color
    de acento del tema actual."""
    try:
        E.marco_icono_cabecera.delete("all")
    except Exception:
        return
    E._ruta_logo_cabecera = os.path.join(R.CARPETA_ICONOS, "logo_cabecera.png")
    if HAY_PILLOW and os.path.exists(E._ruta_logo_cabecera):
        try:
            _img_logo = Image.open(E._ruta_logo_cabecera).convert("RGBA")
            _img_logo = ImageOps.contain(_img_logo, (44, 44))
            E._imagen_logo_cabecera["foto"] = ImageTk.PhotoImage(_img_logo)
            E.marco_icono_cabecera.create_image(24, 24, image=E._imagen_logo_cabecera["foto"])
            return
        except Exception:
            pass
    else:
        try:
            mod_ui_dibujo._dibujar_rect_redondeado(
                E.marco_icono_cabecera, 2, 2, 46, 46, radio=12,
                fill="#283040", outline="#394151", width=1)
        except Exception:
            pass
    try:
        mod_ui_dibujo._dibujar_icono_ecualizador(
            E.marco_icono_cabecera, 24, 24, 26, color=E.color_acento())
    except Exception:
        pass


def aplicar_tema_cabecera():
    """Aplica el tema actual a la barra superior (se llama al arrancar y
    al cambiar de interfaz): fondos grises/azulados, degradado, logo,
    engranaje y chip de estado."""
    C.COLOR_CABECERA_ARRIBA = E.color_cabecera_arriba()
    C.COLOR_CABECERA_ABAJO = E.color_cabecera_abajo()
    try:
        E.cabecera_fondo.config(bg=C.COLOR_CABECERA_ARRIBA)
        E.cabecera.config(bg=C.COLOR_CABECERA_ARRIBA)
        E.marco_icono_cabecera.config(bg=C.COLOR_CABECERA_ARRIBA)
        E.marco_titulos_cabecera.config(bg=C.COLOR_CABECERA_ARRIBA)
        E.titulo.config(bg=C.COLOR_CABECERA_ARRIBA)
        E.subtitulo.config(bg=C.COLOR_CABECERA_ARRIBA)
    except Exception:
        pass
    repintar_logo_cabecera()
    try:
        _redibujar_degradado_cabecera()
    except Exception:
        pass
    try:
        _redibujar_icono_engranaje()
    except Exception:
        pass
    try:
        if E.conectado:
            E.estado.config(fg=E.color_acento())
            E.estado_chip.config(highlightbackground=E.color_acento())
        else:
            E.boton_conectar.config(bg=E.color_acento(), activebackground=E.color_acento_claro())
    except Exception:
        pass
