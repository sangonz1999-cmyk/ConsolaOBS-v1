import tkinter as tk

from tkinter import ttk

from consola_obs.compat import HAY_PILLOW, Image, ImageGrab, ImageTk
from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import plataforma as P
from consola_obs import configuracion as mod_configuracion
from consola_obs import utilidades as mod_utilidades
from consola_obs.obs import cliente as mod_obs_cliente
from consola_obs.ui import tarjeta_fuente as mod_ui_tarjeta
from consola_obs.ui import soundboard as mod_ui_soundboard
from consola_obs.ui import musica as mod_ui_musica
from consola_obs.ui import medidores as mod_ui_medidores
from consola_obs.ui import cabecera as mod_ui_cabecera


def cambiar_tema_interfaz(nuevo_tema):
    """Se llama desde el combobox 'Interfaz' de Ajustes → Apariencia.
    Sólo cambia lo visual (Profesional/Moderna); la funcionalidad es la
    misma. Como los dibujos tienen tamaño fijo, se reconstruye todo."""
    if nuevo_tema not in E.TEMAS_INTERFAZ:
        return
    E.tema_interfaz = nuevo_tema
    E.miniaturas_cargadas.clear()
    _reconstruir_interfaz_con_velo()
    try:
        mod_ui_cabecera.aplicar_tema_cabecera()
    except Exception:
        pass
    try:
        for entrada in (getattr(E, "entrada_host", None), getattr(E, "entrada_puerto", None),
                        getattr(E, "entrada_password", None)):
            if entrada is not None:
                entrada.config(highlightcolor=E.color_acento())
    except Exception:
        pass
    mod_configuracion.guardar_config_interfaz({"tema_interfaz": nuevo_tema})


def cambiar_tamano_icono(nuevo_tamano):
    """Se llama desde el combobox de la barra superior. Como los botones
    circulares y los pads del soundboard se dibujan en un Canvas de un
    tamaño fijo, para cambiar su tamaño es más simple y confiable
    reconstruir todo (sin perder el estado de cada fuente ni la
    conexión) que tratar de estirar los dibujos existentes."""

    if nuevo_tamano not in C.TAMANOS_ICONO:
        return

    E.tamano_icono_actual = nuevo_tamano
    E.miniaturas_cargadas.clear()                                                            
    _reconstruir_interfaz_con_velo()
    mod_configuracion.guardar_config_interfaz({"tamano_icono": nuevo_tamano})


def cambiar_alto_tarjeta(nuevo_alto):
    """Se llama desde el combobox "Alto" de Ajustes → Apariencia: cambia
    la altura de las tarjetas de fuente (el canal se estira y el alto
    total lo acompaña) reconstruyendo todo, igual que el tamaño de
    íconos."""
    if nuevo_alto not in C.ALTOS_TARJETA:
        return
    E.alto_tarjeta_actual = nuevo_alto
    _reconstruir_interfaz_con_velo()
    mod_configuracion.guardar_config_interfaz({"alto_tarjeta": nuevo_alto})


def _iniciar_arrastre_panel(nombre):
    E._panel_en_arrastre["origen"] = nombre


def _widget_pertenece_a(widget, contenedor):
    while widget is not None:
        if widget == contenedor:
            return True
        widget = widget.master
    return False


def _soltar_panel(nombre_actual, event):
    origen = E._panel_en_arrastre["origen"]
    E._panel_en_arrastre["origen"] = None
    if origen is None or origen == nombre_actual:
        return

    try:
        widget_destino = E.ventana.winfo_containing(event.x_root, event.y_root)
    except Exception:
        widget_destino = None
    if widget_destino is None:
        return

    contenedor_destino = E.marco_derecho if origen == "fuentes" else E.marco_fuentes
    if _widget_pertenece_a(widget_destino, contenedor_destino):
        E.orden_paneles = list(reversed(E.orden_paneles))
        _reconstruir_interfaz_con_velo()
        mod_configuracion.guardar_config_interfaz({
            "orientacion_paneles": E.orientacion_paneles,
            "orden_paneles": E.orden_paneles,
        })


# El divisor se mueve LIBRE (infinitas posiciones): sigue al mouse
# píxel por píxel dentro del rango útil. Sin snap a posiciones fijas.
MIN_PANEL_FUENTES = 140
MIN_PANEL_SOUNDBOARD = 220


def _limitar_divisor(valor, total, minimo_antes, minimo_despues):
    """Posición entera de `valor` limitada al rango útil.
    None si no hay recorrido válido."""
    lo = max(0, minimo_antes)
    hi = min(total, total - minimo_despues)
    if hi <= lo or total <= 1:
        return None
    return int(round(max(lo, min(hi, valor))))


def _presionar_divisor(event):
    # OJO: identify devuelve una LISTA como [0, 'sash'] (no el string
    # 'sash' solo), por eso se busca adentro y no con ==.
    try:
        donde = E.cuerpo.identify(event.x, event.y)
    except Exception:
        return
    if "sash" not in str(donde):
        return
    # Se toma el control del arrastre (sin el break, Tk movería el sash
    # píxel por píxel por su cuenta y volverían las posiciones
    # intermedias).
    # Si quedó una sesión vieja colgada (release perdido fuera de la
    # ventana), se asienta primero para arrancar limpio.
    if getattr(E.cuerpo, "_arrastrando_sash", False):
        _asentar_grillas()
    E.cuerpo._arrastrando_sash = True
    entrar_modo_super("divisor")
    # FASE 1: foto fija de pads y título que queda hasta soltar (sin
    # timers en el medio).
    _tapar_pads_con_foto()
    _tapar_titulo_con_foto()
    return "break"


def _tapar_pads_con_foto():
    """FASE 1: congela la vista actual de los pads en una foto que queda
    en pantalla hasta la FASE 3. Así nunca se ven pads cortados."""
    try:
        tapa = getattr(E, "tapa_pads", None)
        lienzo = getattr(E, "canvas_sb", None)
        if tapa is None or lienzo is None:
            return
        if HAY_PILLOW and ImageGrab is not None:
            try:
                E.ventana.update_idletasks()
                x, y = lienzo.winfo_rootx(), lienzo.winfo_rooty()
                ancho, alto = lienzo.winfo_width(), lienzo.winfo_height()
                if ancho > 1 and alto > 1:
                    foto = ImageGrab.grab(bbox=(x, y, x + ancho, y + alto))
                    tapa.imagen_foto = ImageTk.PhotoImage(foto)
                    tapa.config(image=tapa.imagen_foto)
            except Exception:
                tapa.config(image="")
        tapa.place(in_=lienzo, x=0, y=0, relwidth=1, relheight=1)
        tapa.lift()
    except Exception:
        pass


def _tapar_grillas():
    """Cubre SÓLO la grilla de pads con su fondo (los faders nunca se
    tapan). Todo lo demás (divisor, títulos, scrollbars) queda visible."""
    try:
        tapa = getattr(E, "tapa_pads", None)
        lienzo = getattr(E, "canvas_sb", None)
        if tapa is None or lienzo is None:
            return
        tapa.place(in_=lienzo, x=0, y=0, relwidth=1, relheight=1)
        tapa.lift()
    except Exception:
        pass


def _tapar_fuentes_con_foto():
    """Espejo de _tapar_pads_con_foto para la grilla de faders: congela
    la vista actual en una foto que queda hasta el asentado. Si ya está
    puesta no re-saca la foto (un grab por gesto alcanza)."""
    try:
        if getattr(E, "tapa_fuentes_puesta", False):
            return
        tapa = getattr(E, "tapa_fuentes", None)
        lienzo = getattr(E, "canvas", None)
        if tapa is None or lienzo is None:
            return
        if HAY_PILLOW and ImageGrab is not None:
            try:
                E.ventana.update_idletasks()
                x, y = lienzo.winfo_rootx(), lienzo.winfo_rooty()
                ancho, alto = lienzo.winfo_width(), lienzo.winfo_height()
                if ancho > 1 and alto > 1:
                    foto = ImageGrab.grab(bbox=(x, y, x + ancho, y + alto))
                    tapa.imagen_foto = ImageTk.PhotoImage(foto)
                    tapa.config(image=tapa.imagen_foto)
            except Exception:
                tapa.config(image="")
        tapa.place(in_=lienzo, x=0, y=0, relwidth=1, relheight=1)
        tapa.lift()
        E.tapa_fuentes_puesta = True
    except Exception:
        pass


def _tapar_fuentes():
    """Cubre la grilla de faders con su fondo (sin foto). Para el drag
    del divisor, donde los pads ya van con foto."""
    try:
        tapa = getattr(E, "tapa_fuentes", None)
        lienzo = getattr(E, "canvas", None)
        if tapa is None or lienzo is None:
            return
        tapa.place(in_=lienzo, x=0, y=0, relwidth=1, relheight=1)
        tapa.lift()
        E.tapa_fuentes_puesta = True
    except Exception:
        pass


def _destapar_fuentes():
    try:
        tapa = getattr(E, "tapa_fuentes", None)
        if tapa is not None:
            tapa.place_forget()
    except Exception:
        pass
    try:
        E.tapa_fuentes_puesta = False
    except Exception:
        pass


def _programar_asentado_fuentes():
    """Reprograma el asentado OCULTO a los 150 ms (resetea el timer en
    cada movimiento). El asentado en quietud reacomoda SIN destapar: la
    tapa sólo sale al soltar (ver _asentar_fuentes). Si se destapara por
    quietud, en movimientos rápidos (donde Tk deja de mandar <Configure>
    por instantes) se verían frames rotos a mitad del gesto."""
    try:
        timer = getattr(E.ventana, "_timer_asentado_fuentes", None)
        if timer is not None:
            E.ventana.after_cancel(timer)
    except Exception:
        pass
    _tapar_fuentes_con_foto()
    try:
        E.ventana._timer_asentado_fuentes = E.ventana.after(150, _asentar_fuentes_oculto)
    except Exception:
        pass


def _asentar_fuentes_oculto():
    """Reacomoda la grilla y fuerza el pintado SIN destapar: el layout
    queda fresco pero tapado hasta la soltada."""
    try:
        E.ventana._timer_asentado_fuentes = None
    except Exception:
        pass
    try:
        mod_ui_tarjeta._reubicar_fuentes()
    except Exception:
        pass
    try:
        E.ventana.update_idletasks()
    except Exception:
        pass


def _asentar_fuentes():
    """Reacomoda la grilla de faders, fuerza el pintado completo y
    destapa. Sólo para fin de gesto (soltada o clic de seguridad):
    nunca por quietud a mitad del gesto. Idempotente."""
    try:
        E.ventana._timer_asentado_fuentes = None
    except Exception:
        pass
    try:
        mod_ui_tarjeta._reubicar_fuentes()
    except Exception:
        pass
    try:
        E.ventana.update_idletasks()
    except Exception:
        pass
    _destapar_fuentes()


def _tapar_titulo_con_foto():
    """Igual que pads pero para la barra del título: foto fija de
    "Efectos De Sonido" que queda hasta soltar."""
    try:
        tapa = getattr(E, "tapa_titulo", None)
        barra = getattr(E, "barra_soundboard", None)
        if tapa is None or barra is None:
            return
        if HAY_PILLOW and ImageGrab is not None:
            try:
                E.ventana.update_idletasks()
                x, y = barra.winfo_rootx(), barra.winfo_rooty()
                ancho, alto = barra.winfo_width(), barra.winfo_height()
                if ancho > 1 and alto > 1:
                    foto = ImageGrab.grab(bbox=(x, y, x + ancho, y + alto))
                    tapa.imagen_foto = ImageTk.PhotoImage(foto)
                    tapa.config(image=tapa.imagen_foto)
            except Exception:
                tapa.config(image="")
        tapa.place(in_=barra, x=0, y=0, relwidth=1, relheight=1)
        tapa.lift()
    except Exception:
        pass


def _destapar_grillas():
    for tapa in (getattr(E, "tapa_pads", None), getattr(E, "tapa_titulo", None),
                 getattr(E, "tapa_fuentes", None)):
        try:
            if tapa is not None:
                tapa.place_forget()
        except Exception:
            pass
    try:
        E.tapa_fuentes_puesta = False
    except Exception:
        pass


def entrar_modo_super(origen=None):
    """Activa el modo super-optimizador (ver _modo_super en estado.py):
    cada evento de movimiento lo renueva y programa la salida a los
    200ms de quietud. Es barato de llamar en cada evento. Al activarse
    (flanco), apaga los medidores VU; vuelven solos al salir."""
    if origen is not None:
        E._modo_super["origen"] = origen
    if not E._modo_super.get("activo"):
        E._modo_super["activo"] = True
        try:
            mod_ui_medidores.apagar_medidores()
        except Exception:
            pass
    # Vigilancia, NO salida por tiempo: cada evento la renueva; cuando
    # pasan 150ms sin movimiento se mira el botón real: si sigue
    # presionado se sigue esperando (sin prender nada), si ya se soltó
    # se sale. Quedarse quieto con el botón agarrado NUNCA prende los
    # LEDs: sólo la soltada lo hace.
    try:
        timer = E._modo_super.get("timer")
        if timer is not None:
            E.ventana.after_cancel(timer)
    except Exception:
        pass
    try:
        E._modo_super["timer"] = E.ventana.after(150, _vigilar_modo_super)
    except Exception:
        pass


def _vigilar_modo_super():
    """150ms sin movimiento: si el botón sigue presionado, se sigue
    esperando (se reprograma); si ya se soltó (o el release se perdió
    por el camino, ej. maximizar), se sale."""
    E._modo_super["timer"] = None
    if not E._modo_super.get("activo"):
        return
    try:
        sigue_agarrado = P._boton_izquierdo_presionado()
    except Exception:
        sigue_agarrado = False
    if sigue_agarrado:
        try:
            E._modo_super["timer"] = E.ventana.after(150, _vigilar_modo_super)
        except Exception:
            pass
        return
    # Se soltó de verdad (aunque el evento se haya perdido): si quedó
    # la tapa de fuentes, asentar y destapar acá también.
    try:
        if getattr(E, "tapa_fuentes_puesta", False):
            _asentar_fuentes()
    except Exception:
        pass
    salir_modo_super()


def salir_modo_super():
    """Apaga el modo super-optimizador y deja todo pintado final: los
    LEDs se invalidan para que el próximo cuadro los repinte completos,
    los degradados se refrescan y ambas grillas se asientan. Idempotente:
    si no está activo, no hace nada."""
    try:
        timer = E._modo_super.get("timer")
        if timer is not None:
            E.ventana.after_cancel(timer)
    except Exception:
        pass
    E._modo_super["timer"] = None
    if not E._modo_super.get("activo"):
        return
    E._modo_super["activo"] = False
    E._modo_super["origen"] = None
    for widgets in list(E.fuentes.values()):
        try:
            widgets.get("vu_led_estado", {}).pop("ultimo", None)
            redibujar = widgets.get("redibujar_cabecera")
            if redibujar is not None:
                redibujar()
        except Exception:
            pass
    try:
        mod_ui_tarjeta._reubicar_fuentes()
    except Exception:
        pass
    try:
        mod_ui_soundboard._reubicar_pads()
    except Exception:
        pass


def _programar_asentado():
    """Tapa y programa el asentado a los 150 ms (resetea el timer en cada
    movimiento: mientras haya movimiento, no se muestra nada a medias)."""
    try:
        timer = getattr(E.ventana, "_timer_asentado", None)
        if timer is not None:
            E.ventana.after_cancel(timer)
    except Exception:
        pass
    _tapar_grillas()
    try:
        E.ventana._timer_asentado = E.ventana.after(150, _asentar_grillas)
    except Exception:
        pass


def _asentar_grillas():
    """Reacomoda ambas grillas, fuerza el pintado completo y destapa.
    Así nunca se ve un estado a medio renderizar."""
    try:
        E.ventana._timer_asentado = None
    except Exception:
        pass
    try:
        mod_ui_tarjeta._reubicar_fuentes()
    except Exception:
        pass
    try:
        mod_ui_soundboard._reubicar_pads()
    except Exception:
        pass
    try:
        E.ventana.update_idletasks()
    except Exception:
        pass
    _destapar_grillas()


def _mover_divisor(event):
    if not getattr(E.cuerpo, "_arrastrando_sash", False):
        return
    entrar_modo_super("divisor")
    try:
        # El evento puede venir de cualquier widget (burbujea hasta la
        # ventana): se pasa a coordenadas del PanedWindow.
        px = event.x_root - E.cuerpo.winfo_rootx()
        py = event.y_root - E.cuerpo.winfo_rooty()
        mins = {"fuentes": MIN_PANEL_FUENTES, "soundboard": MIN_PANEL_SOUNDBOARD}
        orden = list(E.orden_paneles or ["fuentes", "soundboard"])
        min_antes = mins.get(orden[0], 140)
        min_despues = mins.get(orden[-1], 140)
        nx = _limitar_divisor(px, E.cuerpo.winfo_width(), min_antes, min_despues)
        ny = _limitar_divisor(py, E.cuerpo.winfo_height(), min_antes, min_despues)
        if nx is None or ny is None:
            return
        # Sólo se actúa si cambió de píxel. FASE 2: se coloca
        # el sash y se renderiza todo en segundo plano (tapado por la
        # foto de la FASE 1), sin mostrar nada hasta la FASE 3. Sin
        # timers en el medio: la copia queda hasta soltar.
        if getattr(E.cuerpo, "_ultimo_snap", None) == (nx, ny):
            return
        E.cuerpo._ultimo_snap = (nx, ny)
        _tapar_grillas()
        _tapar_fuentes()
        E.cuerpo.sash_place(0, nx, ny)
        try:
            E.ventana.update_idletasks()
        except Exception:
            pass
        try:
            mod_ui_tarjeta._reubicar_fuentes()
        except Exception:
            pass
        try:
            mod_ui_soundboard._reubicar_pads()
        except Exception:
            pass
        try:
            E.ventana.update_idletasks()
        except Exception:
            pass
    except Exception:
        pass
    return "break"


def _soltar_divisor(event):
    if not getattr(E.cuerpo, "_arrastrando_sash", False):
        return
    E.cuerpo._arrastrando_sash = False
    try:
        timer = getattr(E.ventana, "_timer_asentado", None)
        if timer is not None:
            E.ventana.after_cancel(timer)
            E.ventana._timer_asentado = None
    except Exception:
        pass
    _asentar_grillas()
    # Al soltar el divisor termina el resize: los medidores vuelven ya.
    salir_modo_super()


def _soltar_boton_termina_resize(event=None):
    """Cualquier soltada del botón izquierdo termina el resize de borde
    de ventana o divisor: los medidores vuelven en el acto. Sólo actúa
    si el modo se originó en un resize real (borde o divisor); los clics
    comunes no hacen nada."""
    try:
        if E._modo_super.get("activo") and E._modo_super.get("origen") in ("ventana", "divisor"):
            salir_modo_super()
    except Exception:
        pass
    # Si quedó la tapa de fuentes puesta (resize de borde), asentar ya:
    # no esperar al timer de quietud.
    try:
        if getattr(E, "tapa_fuentes_puesta", False):
            try:
                timer = getattr(E.ventana, "_timer_asentado_fuentes", None)
                if timer is not None:
                    E.ventana.after_cancel(timer)
                    E.ventana._timer_asentado_fuentes = None
            except Exception:
                pass
            _asentar_fuentes()
    except Exception:
        pass


def construir_cuerpo():

    estado_previo_fuentes = []
    if E.cuerpo is not None:
        for nombre, w in E.fuentes.items():
            estado_previo_fuentes.append({
                "nombre": nombre,
                "nombre_visible": w.get("nombre_visible", nombre),
                "vol_db": w["fader"].get(),
                "muted": w.get("muted", False),
                "tipo_monitor": w.get("tipo_monitor", "OBS_MONITORING_TYPE_NONE"),
            })
        E.fuentes.clear()
        E.cuerpo.destroy()

    E.columnas_soundboard = 4
    E.columnas_fuentes = 1
    # Las tarjetas se recrean de cero más abajo, ya con el ancho
    # correcto para el tamaño actual: si dejáramos el ancho "recordado"
    # de la reconstrucción anterior, el primer _reubicar_fuentes()
    # después de esto podría creer (por error) que el ancho no cambió y
    # saltarse el reacomodo que hace falta.
    E._ultimo_ancho_celda_fuentes["valor"] = None
    E._ultima_grilla_fuentes["clave"] = None
    E._ultimas_columnas_pads["valor"] = None

    E.cuerpo = tk.PanedWindow(E.ventana, orient=E.orientacion_paneles, bg="#0b0e13", sashwidth=8, sashrelief="flat")
    E.cuerpo.pack(fill="both", expand=True)
    # El press va acá (a nivel widget, para frenar el drag nativo con
    # break antes de que arranque); motion y release van una sola vez
    # a nivel ventana en app.py (llegan se esté donde se esté el mouse,
    # por bubbling).
    E.cuerpo.bind("<ButtonPress-1>", _presionar_divisor)
    # Los widgets nuevos se apilan por encima de los que ya existían;
    # si el velo de redimensionado está puesto (ver más abajo, cerca
    # del final del archivo), hay que volver a subirlo por encima de
    # este panel recién creado para que lo siga tapando mientras se
    # arma el resto. Si el velo no existe todavía (primera vez que se
    # arma la interfaz, al arrancar el programa) o no está puesto, esto
    # no hace nada.
    try:
        E.velo_redimension.lift()
    except NameError:
        pass


    E.marco_fuentes = tk.Frame(E.cuerpo, bg=E.color_fondo_panel())

    barra_titulo_fuentes = tk.Frame(E.marco_fuentes, bg=E.color_barra_titulo(), height=40)
    barra_titulo_fuentes.pack(fill="x")
    barra_titulo_fuentes.pack_propagate(False)

    _acento_barra = C.MOD_ACENTO if E.es_moderna() else "#2fd693"
    _acento_linea = C.MOD_ACENTO_OSCURO if E.es_moderna() else "#17b8b0"
    tk.Frame(barra_titulo_fuentes, bg=_acento_barra, width=4).pack(side="left", fill="y")
    tk.Frame(barra_titulo_fuentes, bg=_acento_linea, height=2).pack(side="bottom", fill="x")

    titulo_fuentes = tk.Label(
        barra_titulo_fuentes, text="☰  FUENTES DE AUDIO   ·   arrastrá para mover el panel",
        bg=E.color_barra_titulo(), fg="white", font=(E.FUENTE_UI, 11, "bold"), cursor="fleur"
    )
    titulo_fuentes.pack(side="left", padx=12)
    titulo_fuentes.bind("<ButtonPress-1>", lambda e: _iniciar_arrastre_panel("fuentes"))
    titulo_fuentes.bind("<ButtonRelease-1>", lambda e: _soltar_panel("fuentes", e))

    E.marco_canvas = tk.Frame(E.marco_fuentes, bg=E.color_fondo_panel())
    E.marco_canvas.pack(fill="both", expand=True)

    E.canvas = tk.Canvas(E.marco_canvas, bg=E.color_fondo_panel(), highlightthickness=0)
    E.scrollbar_v = ttk.Scrollbar(
        E.marco_canvas, orient="vertical", command=E.canvas.yview, style="Discreta.Vertical.TScrollbar"
    )
    E.scrollbar_h = ttk.Scrollbar(
        E.marco_canvas, orient="horizontal", command=E.canvas.xview, style="Discreta.Horizontal.TScrollbar"
    )
    E.canvas.configure(yscrollcommand=E.scrollbar_v.set, xscrollcommand=E.scrollbar_h.set)

    E.canvas.grid(row=0, column=0, sticky="nsew")
    E.scrollbar_v.grid(row=0, column=1, sticky="ns")
    E.scrollbar_h.grid(row=1, column=0, sticky="ew")
    E.marco_canvas.grid_rowconfigure(0, weight=1)
    E.marco_canvas.grid_columnconfigure(0, weight=1)
    E.scrollbar_v.grid_remove()
    E.scrollbar_h.grid_remove()

    E.panel_fuentes = tk.Frame(E.canvas, bg=E.color_fondo_panel())
    E.canvas.create_window((0, 0), window=E.panel_fuentes, anchor="nw")

    E.panel_fuentes.bind("<Configure>", actualizar_scroll)
    E.canvas.bind("<Configure>", lambda e: (actualizar_scroll(e), mod_ui_tarjeta._al_redimensionar_fuentes(e)))
    E.canvas.bind("<Enter>", _activar_rueda_fuentes)
    E.canvas.bind("<Leave>", _desactivar_rueda_fuentes)

    # Clic derecho sobre el fondo del panel de fuentes (no sobre una
    # tarjeta) -> menú "Agregar fuente", igual que el clic derecho en la
    # lista de fuentes de OBS. Se ata tanto al canvas como al marco de
    # adentro porque, según cuántas tarjetas haya, el pixel vacío puede
    # pertenecer a cualquiera de los dos. Las tarjetas ya tienen su
    # propio <Button-3> y Tk le da prioridad al widget de más adentro,
    # así que no se pisan.
    E.canvas.bind("<Button-3>", mod_ui_tarjeta._abrir_menu_contextual_panel_fuentes)
    E.panel_fuentes.bind("<Button-3>", mod_ui_tarjeta._abrir_menu_contextual_panel_fuentes)


    E.marco_derecho = tk.Frame(E.cuerpo, bg=E.color_fondo_panel())

    E.barra_soundboard = tk.Frame(E.marco_derecho, bg=E.color_barra_titulo(), height=40)
    E.barra_soundboard.pack(fill="x")
    E.barra_soundboard.pack_propagate(False)

    tk.Frame(E.barra_soundboard, bg=_acento_linea, width=4).pack(side="left", fill="y")
    tk.Frame(E.barra_soundboard, bg=_acento_barra, height=2).pack(side="bottom", fill="x")

    titulo_soundboard = tk.Label(
        E.barra_soundboard, text="☰  Efectos De Sonido",
        bg=E.color_barra_titulo(), fg="white", font=(E.FUENTE_UI, 11, "bold"), cursor="fleur"
    )
    titulo_soundboard.pack(side="left", padx=12)
    titulo_soundboard.bind("<ButtonPress-1>", lambda e: _iniciar_arrastre_panel("soundboard"))
    titulo_soundboard.bind("<ButtonRelease-1>", lambda e: _soltar_panel("soundboard", e))

    # Tapa del título: mismas 4 fases que los pads (foto fija hasta soltar).
    E.tapa_titulo = tk.Label(E.barra_soundboard, bg=E.color_barra_titulo(), bd=0, highlightthickness=0)
    E.tapa_titulo.place_forget()
    E.tapa_titulo.bind("<ButtonPress-1>", lambda e: _asentar_grillas())

    E.marco_soundboard_scroll = tk.Frame(E.marco_derecho, bg=E.color_fondo_panel())
    E.marco_soundboard_scroll.pack(fill="both", expand=True)

    E.canvas_sb = tk.Canvas(E.marco_soundboard_scroll, bg=E.color_fondo_panel(), highlightthickness=0)
    E.scrollbar_sb = ttk.Scrollbar(
        E.marco_soundboard_scroll, orient="vertical", command=E.canvas_sb.yview,
        style="Discreta.Vertical.TScrollbar"
    )
    E.canvas_sb.configure(yscrollcommand=E.scrollbar_sb.set)

    E.canvas_sb.pack(side="left", fill="both", expand=True)

    E.panel_soundboard = tk.Frame(E.canvas_sb, bg=E.color_fondo_panel())
    E._ventana_panel_sb_id = E.canvas_sb.create_window((0, 0), window=E.panel_soundboard, anchor="nw")

    E.panel_soundboard.bind("<Configure>", actualizar_scroll_soundboard)
    E.canvas_sb.bind("<Configure>", mod_ui_soundboard._al_redimensionar_soundboard)
    E.canvas_sb.bind("<Enter>", _activar_rueda_soundboard)
    E.canvas_sb.bind("<Leave>", _desactivar_rueda_soundboard)


    zonas = {"fuentes": E.marco_fuentes, "soundboard": E.marco_derecho}
    minsizes = {"fuentes": 140, "soundboard": 220}

    for nombre_zona in E.orden_paneles:
        E.cuerpo.add(zonas[nombre_zona], minsize=minsizes[nombre_zona], stretch="always")

    # --------------------------------------------------------------
    # IMPORTANTE: todo lo que sigue (restaurar el divisor y calcular
    # cuántas columnas entran) se hace ACÁ MISMO, de forma sincrónica,
    # antes de crear una sola tarjeta de canal o un solo pad.
    #
    # Antes esto se hacía con ventana.after(150/200, ...), es decir,
    # unos milisegundos DESPUÉS de que construir_cuerpo() ya había
    # terminado. El problema es que quien llama a construir_cuerpo()
    # al terminar de redimensionar (_aplicar_redimension) vuelve a
    # mostrar la ventana (alpha 1) apenas construir_cuerpo() retorna,
    # sin esperar esos after(). Entonces el usuario llegaba a ver, por
    # un instante, el divisor en la posición por defecto y la grilla
    # con la distribución "de fábrica" (1 columna de canales, 4 pads),
    # y recién 150-200ms más tarde todo "saltaba" a como debía verse.
    # Eso es lo que se percibía como "se rompe todo y después se
    # arregla solo" al soltar el borde de la ventana.
    #
    # Al forzar el cálculo de geometría con update_idletasks() y
    # resolver el divisor y las columnas antes de armar el contenido,
    # la interfaz queda bien armada desde el primer cuadro que el
    # usuario llega a ver.
    # --------------------------------------------------------------
    E.ventana.update_idletasks()

    clave_sash = f"posicion_divisor_{E.orientacion_paneles}"
    posicion_guardada = E.config_interfaz_previa.get(clave_sash)
    if posicion_guardada is not None:
        try:
            if E.cuerpo.panes():
                x_actual, y_actual = E.cuerpo.sash_coord(0)
                if E.orientacion_paneles == "vertical":
                    E.cuerpo.sash_place(0, x_actual, int(posicion_guardada))
                else:
                    E.cuerpo.sash_place(0, int(posicion_guardada), y_actual)
        except Exception as e:
            print(f"No se pudo restaurar la posición del divisor: {e}")
        # El divisor recién movido cambia el ancho real de cada panel;
        # hay que dejar que se recalcule antes de medir columnas.
        E.ventana.update_idletasks()

    E.columnas_fuentes = mod_ui_tarjeta._columnas_disponibles_fuentes()
    E.columnas_soundboard = mod_ui_soundboard._columnas_disponibles()

    for datos in estado_previo_fuentes:
        mod_ui_tarjeta.crear_fader_fuente(
            datos["nombre"], datos["vol_db"], datos["muted"], datos["tipo_monitor"],
            nombre_visible=datos["nombre_visible"]
        )
    actualizar_scroll()

    mod_ui_soundboard.construir_soundboard()

    # Red de seguridad: si por lo que sea (fuente distinta, scrollbar
    # que aparece y come unos píxeles, etc.) la medida cambia apenas la
    # ventana termina de asentarse, esto la corrige. Se llama a la
    # versión directa (no a la que espera un toque de calma) porque acá
    # ya no hace falta esperar nada: la ventana ya terminó de moverse,
    # sólo estamos chequeando que no haya quedado nada desalineado. Como
    # ya arrancamos bien acomodados, en el caso normal estas llamadas no
    # van a encontrar ningún cambio y no van a mover nada en pantalla.
    E.ventana.after(30, mod_ui_soundboard._aplicar_redimension_soundboard)
    E.ventana.after(30, mod_ui_tarjeta._aplicar_redimension_fuentes)

    # Tapas anti-corte: cubren sólo las grillas (pads y faders). Todo lo
    # demás (divisor, títulos, scrollbars) queda visible. Se recrean
    # ocultas con cada construir_cuerpo.
    E.tapa_pads = tk.Label(E.marco_soundboard_scroll, bg=E.color_fondo_panel(), bd=0, highlightthickness=0)
    E.tapa_pads.place_forget()
    # Si alguna vez queda tapado sin sesión (release perdido), un clic
    # sobre la tapa lo destapa y acomoda (asentar es idempotente).
    E.tapa_pads.bind("<ButtonPress-1>", lambda e: _asentar_grillas())

    # Tapa anti-corte de FUENTES (espejo de la de pads): congela la
    # grilla de faders con una foto durante el redimensionado, así no
    # se ven estados a medio reubicar. Se recrea oculta con cada
    # construir_cuerpo, igual que la de pads.
    try:
        E.tapa_fuentes = tk.Label(E.marco_canvas, bg=E.color_fondo_panel(), bd=0, highlightthickness=0)
        E.tapa_fuentes.place_forget()
        E.tapa_fuentes.bind("<ButtonPress-1>", lambda e: _asentar_fuentes())
    except Exception:
        E.tapa_fuentes = None
    E.tapa_fuentes_puesta = False

    # Mini player de música al pie del panel de fuentes (se reconstruye
    # acá para sobrevivir a cambios de tema/diseño como el resto).
    try:
        mod_ui_musica.construir_mini_player()
    except Exception as e:
        print(f"No se pudo construir el mini player de música: {e}")


def actualizar_scroll(event=None):
    bbox = E.canvas.bbox("all")
    E.canvas.configure(scrollregion=bbox)
    if not bbox:
        return

    ancho_contenido = bbox[2] - bbox[0]
    alto_contenido = bbox[3] - bbox[1]
    ancho_visible = E.canvas.winfo_width()
    alto_visible = E.canvas.winfo_height()

    if alto_contenido > alto_visible + 2:
        E.scrollbar_v.grid()
    else:
        E.scrollbar_v.grid_remove()

    if ancho_contenido > ancho_visible + 2:
        E.scrollbar_h.grid()
    else:
        E.scrollbar_h.grid_remove()


def _rueda_fuentes_vertical(event):
    E.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


def _rueda_fuentes_horizontal(event):
    E.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")


class _Delta:
    """Evento falso con solo .delta, para la rueda de Linux/X11
    (Botón-4/5 no trae delta como MouseWheel de Windows)."""


def _activar_rueda_fuentes(event):
    E.canvas.bind_all("<MouseWheel>", _rueda_fuentes_vertical)
    E.canvas.bind_all("<Shift-MouseWheel>", _rueda_fuentes_horizontal)
    E.canvas.bind_all("<Button-4>", lambda e: _rueda_fuentes_vertical(_Delta(120)))
    E.canvas.bind_all("<Button-5>", lambda e: _rueda_fuentes_vertical(_Delta(-120)))
    E.canvas.bind_all("<Shift-Button-4>", lambda e: _rueda_fuentes_horizontal(_Delta(120)))
    E.canvas.bind_all("<Shift-Button-5>", lambda e: _rueda_fuentes_horizontal(_Delta(-120)))


def _desactivar_rueda_fuentes(event):
    E.canvas.unbind_all("<MouseWheel>")
    E.canvas.unbind_all("<Shift-MouseWheel>")
    E.canvas.unbind_all("<Button-4>")
    E.canvas.unbind_all("<Button-5>")
    E.canvas.unbind_all("<Shift-Button-4>")
    E.canvas.unbind_all("<Shift-Button-5>")


def actualizar_scroll_soundboard(event=None):
    bbox = E.canvas_sb.bbox("all")
    E.canvas_sb.configure(scrollregion=bbox)
    if not bbox:
        return

    alto_contenido = bbox[3] - bbox[1]
    alto_visible = E.canvas_sb.winfo_height()

    if alto_contenido > alto_visible + 2:
        if not E.scrollbar_sb.winfo_ismapped():
            E.scrollbar_sb.pack(side="right", fill="y")
    else:
        if E.scrollbar_sb.winfo_ismapped():
            E.scrollbar_sb.pack_forget()


def _rueda_soundboard(event):
    E.canvas_sb.yview_scroll(int(-1 * (event.delta / 120)), "units")


def _activar_rueda_soundboard(event):
    E.canvas_sb.bind_all("<MouseWheel>", _rueda_soundboard)
    E.canvas_sb.bind_all("<Button-4>", lambda e: _rueda_soundboard(_Delta(120)))
    E.canvas_sb.bind_all("<Button-5>", lambda e: _rueda_soundboard(_Delta(-120)))


def _desactivar_rueda_soundboard(event):
    E.canvas_sb.unbind_all("<MouseWheel>")
    E.canvas_sb.unbind_all("<Button-4>")
    E.canvas_sb.unbind_all("<Button-5>")


def _nombre_diseno_actual():
    for nombre, (orient, orden) in E.DISENOS.items():
        if orient == E.orientacion_paneles and orden == E.orden_paneles:
            return nombre
    return "Fuentes arriba"


def cambiar_diseno(nombre_diseno):
    if nombre_diseno not in E.DISENOS:
        return
    E.orientacion_paneles, E.orden_paneles = E.DISENOS[nombre_diseno]
    _reconstruir_interfaz_con_velo()
    mod_configuracion.guardar_config_interfaz({
        "orientacion_paneles": E.orientacion_paneles,
        "orden_paneles": E.orden_paneles,
    })


FUENTE_PREDETERMINADA = "Predeterminada"

# Alias de tipografía (pack obs_pack): nombre visible -> familias reales
# en orden de preferencia. "Tipografia de obs" es Open Sans (la de OBS).
ALIAS_TIPOGRAFIAS = {"Tipografia de obs": ("Open Sans", "Helvetica", "Arial")}


def _resolver_familia_tipografia(nombre):
    """Familia real para un nombre del selector (alias o directa).
    None si no hay ninguna disponible."""
    for familia in ALIAS_TIPOGRAFIAS.get(nombre, (nombre,)):
        if familia in E._familias_disponibles:
            return familia
    return None


def _fuentes_tipografia_disponibles():
    """Opciones del selector de tipografía: primero el alias de OBS,
    después la predeterminada (la que el programa elige sola) más las
    tipografías propias registradas desde la carpeta assets/fuentes
    que estén disponibles."""
    propias = sorted({f for f in E._NOMBRES_FUENTES_PERSONALIZADAS
                      if f in E._familias_disponibles})
    if "Tipografia de obs" not in propias and _resolver_familia_tipografia("Tipografia de obs"):
        propias = ["Tipografia de obs"] + propias
    if propias and propias[0] == "Tipografia de obs":
        return ["Tipografia de obs", FUENTE_PREDETERMINADA] + propias[1:]
    return [FUENTE_PREDETERMINADA] + propias


def aplicar_fuente_elegida(nombre, guardar=True):
    """Aplica la tipografía elegida a todas las letras del programa
    (textos generales y títulos, que son los que usan FUENTE_UI y
    FUENTE_TITULO). Las fuentes de íconos y emojis (■ ↻ 🔊 🎧) se dejan
    como están a propósito: las tipografías decorativas no traen esos
    símbolos y quedarían en blanco.
    Acepta el alias "Tipografia de obs" (Open Sans, con fallback)."""
    if not nombre or nombre == FUENTE_PREDETERMINADA:
        E.FUENTE_UI = next((f for f in E._PREFERENCIAS_FUENTE_UI if f in E._familias_disponibles), "TkDefaultFont")
        E.FUENTE_TITULO = next((f for f in E._PREFERENCIAS_FUENTE_TITULO if f in E._familias_disponibles), E.FUENTE_UI)
        E.fuente_elegida = ""
    else:
        familia = _resolver_familia_tipografia(nombre)
        if familia is None:
            return
        E.FUENTE_UI = familia
        E.FUENTE_TITULO = familia
        E.fuente_elegida = nombre
    if guardar:
        mod_configuracion.guardar_config_interfaz({"fuente_ui": E.fuente_elegida})


def _familia_fuente_actual(widget):
    """Familia de la fuente que un widget tiene configurada ahora. Los
    specs de Tk vienen como '{Familia Con Espacios} tamaño estilos',
    como tupla, o como nombre de fuente del sistema."""
    try:
        spec = widget.cget("font")
    except Exception:
        return None
    if isinstance(spec, (tuple, list)):
        return spec[0] if spec else None
    if not isinstance(spec, str):
        return None
    spec = spec.strip()
    if spec.startswith("{"):
        fin = spec.find("}")
        return spec[1:fin] if fin > 1 else None
    return spec.split(" ", 1)[0] if spec else None


def _reaplicar_fuentes_persistentes(fuente_ui_vieja, fuente_titulo_vieja):
    """El cambio de tipografía reconstruye el cuerpo, pero el menú de
    ajustes y la cabecera son persistentes y se quedarían con la letra
    vieja. Se les cambia sólo la familia (tamaño y estilo intactos):
    lo que estaba en la UI vieja pasa a la nueva, ídem títulos; lo
    demás (íconos, emojis, fuentes del sistema) no se toca."""
    def _visitar(w):
        try:
            hijos = w.winfo_children()
        except Exception:
            hijos = []
        for h in hijos:
            _visitar(h)
        fam = _familia_fuente_actual(w)
        if fam == fuente_ui_vieja:
            nueva = E.FUENTE_UI
        elif fam == fuente_titulo_vieja:
            nueva = E.FUENTE_TITULO
        else:
            return
        try:
            actual = w.cget("font")
        except Exception:
            return
        if isinstance(actual, (tuple, list)):
            resto = tuple(actual[1:])
        else:
            partes = actual.strip()
            if partes.startswith("{"):
                partes = partes[partes.find("}") + 1:].strip()
            else:
                partes = partes.split(" ", 1)[1] if " " in partes else ""
            resto = tuple(partes.split()) if partes else ()
        try:
            w.configure(font=(nueva,) + resto)
        except Exception:
            pass
    for raiz in (getattr(E, "cabecera", None), getattr(E, "barra", None)):
        if raiz is not None:
            try:
                _visitar(raiz)
            except Exception:
                pass
    # Comboboxes (ttk: la fuente va por estilo, no por widget) y su
    # lista desplegable (va por option_add, fijado una sola vez al
    # arrancar): sin esto los selectores quedan con la letra vieja.
    try:
        E._estilo_scrollbar.configure("Discreta.TCombobox", font=(E.FUENTE_UI, 9))
    except Exception:
        pass
    try:
        E.ventana.option_add("*TCombobox*Listbox.font", (E.FUENTE_UI, 9))
    except Exception:
        pass


def cambiar_fuente(nombre):
    """Se llama desde el combobox de tipografía del menú de ajustes:
    aplica la fuente elegida y reconstruye la interfaz para que el
    cambio se vea reflejado en todas las letras. La cabecera superior
    (título, subtítulo y estado) y el resto de widgets persistentes
    (menú de ajustes) no se reconstruyen con el resto, así que su
    fuente se actualiza acá en el acto."""
    fuente_ui_vieja, fuente_titulo_vieja = E.FUENTE_UI, E.FUENTE_TITULO
    aplicar_fuente_elegida(nombre)
    _reaplicar_fuentes_persistentes(fuente_ui_vieja, fuente_titulo_vieja)
    _reconstruir_interfaz_con_velo()
    try:
        E.titulo.configure(font=(E.FUENTE_TITULO, 19, "bold"))
        E.subtitulo.configure(font=(E.FUENTE_UI, 9))
        E.estado.configure(font=(E.FUENTE_UI, 10, "bold"))
    except Exception:
        pass


def _capturar_snapshot_ventana():
    """Saca una foto de cómo se ve la ventana AHORA MISMO y la guarda
    para la próxima vez que arranque un arrastre. Se llama justo
    después de cada reconstrucción (con la interfaz ya destapada y
    dibujada), nunca durante un arrastre, así que no le cuesta nada de
    fluidez al usuario: es una operación puntual, no algo que se repita
    en cada evento."""
    if not HAY_PILLOW or ImageGrab is None:
        return
    try:
        E.ventana.update_idletasks()
        x, y = E.ventana.winfo_rootx(), E.ventana.winfo_rooty()
        ancho, alto = E.ventana.winfo_width(), E.ventana.winfo_height()
        if ancho <= 1 or alto <= 1:
            return
        E._captura_ventana["imagen_pil"] = ImageGrab.grab(bbox=(x, y, x + ancho, y + alto))
    except Exception:
        # Cualquier falla acá (por ejemplo, ImageGrab sin soporte en
        # este Linux) simplemente nos deja sin foto para la próxima vez,
        # y _mostrar_velo_redimension ya sabe caer al rectángulo liso.
        pass


def _actualizar_imagen_velo():
    """Escala la última foto guardada al tamaño actual de la ventana y
    la deja puesta en el velo (para las reconstrucciones explícitas)."""
    imagen = E._captura_ventana["imagen_pil"]
    ancho, alto = max(1, E.ventana.winfo_width()), max(1, E.ventana.winfo_height())
    if imagen is None:
        # Sin foto (todavía no hubo ninguna reconstrucción, o Pillow no
        # está disponible): rectángulo liso de siempre, sin imagen.
        E.velo_redimension.config(image="")
        E._foto_velo["tk"] = None
        return
    try:
        # BILINEAR en vez de NEAREST: escalar la foto del velo con
        # vecino más cercano hacía que, mientras se arrastra el borde,
        # la interfaz congelada se viera con escalones y bordes rotos.
        # BILINEAR suaviza y sigue siendo barato de hacer por cuadro.
        escalada = imagen.resize((ancho, alto), Image.BILINEAR)
        E._foto_velo["tk"] = ImageTk.PhotoImage(escalada)
        E.velo_redimension.config(image=E._foto_velo["tk"])
    except Exception:
        E.velo_redimension.config(image="")
        E._foto_velo["tk"] = None


def _mostrar_velo_redimension():
    # El velo de Tk tapa siempre, sea cual sea la cantidad de ventanas
    # nativas por debajo, porque es un hermano posicionado ENCIMA dentro
    # del mismo árbol de Tk. A propósito NO se congela el pintado acá:
    # la gracia del velo es que su foto se repinta en vivo siguiendo al
    # borde (ver _actualizar_imagen_velo); con el freeze puesto esos
    # repintados no saldrían y el arrastre se vería como un cuadro
    # congelado. El freeze se usa sólo alrededor de la reconstrucción
    # (ver _reconstruir_interfaz_con_velo y _aplicar_redimension).
    _actualizar_imagen_velo()
    E.velo_redimension.place(x=0, y=0, relwidth=1, relheight=1)
    E.velo_redimension.lift()


def _ocultar_velo_redimension():
    E.velo_redimension.place_forget()
    # La interfaz de verdad ya está armada y visible: es el momento
    # justo para renovar la foto, así el PRÓXIMO arrastre arranca
    # mostrando este estado (y no uno viejo).
    _capturar_snapshot_ventana()


def _reconstruir_interfaz_con_velo():
    """Reconstruye toda la interfaz (construir_cuerpo) tapándola con el
    velo mientras dura el armado. Se usa en cualquier lugar que
    necesite reconstruir todo de golpe —cambiar el tamaño de ícono,
    cambiar el diseño de paneles, soltar un panel arrastrado a otro
    lado— y no sólo al redimensionar la ventana, para que ninguna de
    esas acciones deje ver un instante con la interfaz a medio armar.
    En Windows se suma el freeze nativo sólo acá (durante el armado),
    nunca durante el arrastre (ver _mostrar_velo_redimension)."""
    _mostrar_velo_redimension()
    if P._ES_WINDOWS:
        P._congelar_pintado_ventana()
    try:
        construir_cuerpo()
        E.ventana.update_idletasks()
    finally:
        if P._ES_WINDOWS:
            P._descongelar_pintado_ventana()
        _ocultar_velo_redimension()


def _reubicar_vivo_ventana():
    """Reacomoda ambas grillas en vivo durante el redimensionado de la
    ventana, sin tapar nada: sólo grid_forget + grid, sin destruir ni
    crear nada, así el movimiento se ve fluido."""
    try:
        E.ventana._timer_resize_vivo = None
    except Exception:
        pass
    try:
        mod_ui_tarjeta._reubicar_fuentes()
    except Exception:
        pass
    try:
        mod_ui_soundboard._reubicar_pads()
    except Exception:
        pass


def _al_redimensionar_ventana(event):
    """Si cambió el TAMAÑO de la ventana, reacomoda las grillas en vivo
    (throttle corto, sin tapas). Mover la ventana de lugar (misma
    medida) no hace nada. Las tapas con foto quedan sólo para el drag
    del divisor."""
    if event.widget is not E.ventana:
        return
    try:
        tam = (E.ventana.winfo_width(), E.ventana.winfo_height())
    except Exception:
        return
    if getattr(E.ventana, "_ult_geom", None) == tam:
        return
    E.ventana._ult_geom = tam
    entrar_modo_super("ventana")
    try:
        timer = getattr(E.ventana, "_timer_resize_vivo", None)
        if timer is not None:
            E.ventana.after_cancel(timer)
    except Exception:
        pass
    try:
        E.ventana._timer_resize_vivo = E.ventana.after(15, _reubicar_vivo_ventana)
    except Exception:
        pass


# Tope para morir igual si algo se cuelga en el cierre (hilos no
# daemon de terceros, sockets a medio cerrar, etc.): la limpieza de
# red tiene esta ventana para terminar; después se fuerza la salida.
_DEMORA_SALIDA_SEG = 8


def _limpieza_cierre_en_hilo():
    """STOP + vaciados + desconexión (puede tardar con enlaces lentos:
    antes corría en el hilo UI y colgaba la ventana con '(No
    responde)'). Sin tocar widgets: la ventana ya se destruyó."""
    try:
        from consola_obs.audio import reproduccion as mod_audio_reproduccion
        mod_audio_reproduccion.detener_y_vaciar_efectos()
    except Exception:
        pass
    try:
        mod_obs_cliente._desconectar_solo_red()
    except Exception:
        pass


def _vigilar_cierre():
    try:
        import time as _t
        _t.sleep(_DEMORA_SALIDA_SEG)
    except Exception:
        pass
    try:
        import os as _os
        _os._exit(0)
    except Exception:
        pass


def al_cerrar():
    try:
        E._cerrando = True
    except Exception:
        pass
    # 1) Local y rápido en el hilo UI: frenar los parlantes ya.
    try:
        from consola_obs.audio import reproduccion as mod_audio_reproduccion
        mod_audio_reproduccion._detener_local()
    except Exception:
        pass
    # 2) La red va en segundo plano (no se la espera).
    try:
        threading.Thread(target=_limpieza_cierre_en_hilo, daemon=True).start()
    except Exception:
        pass
    # 3) Guardados locales (rápidos).
    try:
        from consola_obs.audio import musica as mod_audio_musica
        mod_audio_musica._flush_duraciones(forzar=True)
    except Exception:
        pass

    try:
        datos_a_guardar = {
            "geometria_ventana": E.ventana.geometry(),
            "orientacion_paneles": E.orientacion_paneles,
            "orden_paneles": E.orden_paneles,
            "tamano_icono": E.tamano_icono_actual,
            "num_pads_soundboard": E.num_pads_soundboard,
            "fuentes_principales": sorted(E.fuentes_principales),
            "colores_fuentes": E.colores_fuentes,
            "orden_fuentes": list(E.orden_fuentes),
        }
        if E.cuerpo is not None and E.cuerpo.panes():
            x, y = E.cuerpo.sash_coord(0)
            clave_sash = f"posicion_divisor_{E.orientacion_paneles}"
            datos_a_guardar[clave_sash] = y if E.orientacion_paneles == "vertical" else x
        mod_configuracion.guardar_config_interfaz(datos_a_guardar)
    except Exception as e:
        print(f"No se pudo guardar la configuración de interfaz: {e}")

    # 4) Cerrar la ventana YA y garantizar la muerte del proceso.
    try:
        E.ventana.destroy()
    except Exception:
        pass
    try:
        threading.Thread(target=_vigilar_cierre, daemon=True).start()
    except Exception:
        try:
            import os as _os
            _os._exit(0)
        except Exception:
            pass
