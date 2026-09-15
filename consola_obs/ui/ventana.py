import time
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


# Cuánto tiene que quedarse quieta la ventana para dar por terminado un
# arrastre y recién ahí reconstruir (antes: 180 ms, que con movimientos
# suaves se cumplía a mitad del arrastre y reconstruía a cada pausa,
# y eso era el parpadeo).
DEMORA_FIN_ARRASTRE_MS = 300
# La foto del velo no se reescala más seguido que esto durante el
# arrastre (reescalar la foto completa en cada evento traba el hilo
# de la interfaz y se nota como tironeo).
INTERVALO_MINIMO_FOTO_VELO_SEG = 0.06


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


def _presionar_divisor(event):
    """Arranca la sesión de arrastre del divisor (sash) entre paneles,
    pero SÓLO si el clic cayó justo sobre la barra del divisor (los
    clics en el resto del PanedWindow son de los widgets de adentro y
    no llegan acá igual). Mientras dura, las grillas no se reconstruyen
    (ver _aplicar_redimension_soundboard): se reacomodan una sola vez
    al soltar."""
    try:
        es_divisor = E.cuerpo.identify(event.x, event.y) == "sash"
    except Exception:
        es_divisor = False
    if not es_divisor:
        return
    E._arrastre_divisor["activo"] = True
    _reprogramar_fin_divisor()


def _reprogramar_fin_divisor():
    if E._trabajo_divisor["id"] is not None:
        try:
            E.ventana.after_cancel(E._trabajo_divisor["id"])
        except Exception:
            pass
    E._trabajo_divisor["id"] = E.ventana.after(
        DEMORA_FIN_ARRASTRE_MS, _fin_arrastre_divisor)


def _cancelar_arrastre_divisor():
    """Termina la sesión del divisor SIN reacomodar (lo usa el arrastre
    de ventana cuando toma la posta: su reconstrucción ya cubre todo)."""
    E._arrastre_divisor["activo"] = False
    if E._trabajo_divisor["id"] is not None:
        try:
            E.ventana.after_cancel(E._trabajo_divisor["id"])
        except Exception:
            pass
        E._trabajo_divisor["id"] = None


def _fin_arrastre_divisor():
    """Termina la sesión del divisor y reacomoda las grillas una sola
    vez. Los _aplicar pendientes (o este llamado directo) reconstruyen
    sólo si hizo falta (columnas/ancho); si no, no tocan nada."""
    E._trabajo_divisor["id"] = None
    if not E._arrastre_divisor["activo"]:
        return
    E._arrastre_divisor["activo"] = False
    mod_ui_tarjeta._aplicar_redimension_fuentes()
    mod_ui_soundboard._aplicar_redimension_soundboard()


def _soltar_divisor(event):
    """Soltar el botón en cualquier parte de la ventana termina la
    sesión del divisor (vía rápida; el timer de calma es el respaldo
    por si el release se pierde, p. ej. soltando fuera de la ventana)."""
    if E._arrastre_divisor["activo"]:
        _fin_arrastre_divisor()


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

    E.cuerpo = tk.PanedWindow(E.ventana, orient=E.orientacion_paneles, bg="#0b0e13", sashwidth=8, sashrelief="flat")
    E.cuerpo.pack(fill="both", expand=True)
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
    E.cuerpo.bind("<ButtonPress-1>", _presionar_divisor)


    E.marco_fuentes = tk.Frame(E.cuerpo, bg="#10141b")

    barra_titulo_fuentes = tk.Frame(E.marco_fuentes, bg="#151a24", height=40)
    barra_titulo_fuentes.pack(fill="x")
    barra_titulo_fuentes.pack_propagate(False)

    tk.Frame(barra_titulo_fuentes, bg="#2fd693", width=4).pack(side="left", fill="y")
    tk.Frame(barra_titulo_fuentes, bg="#17b8b0", height=2).pack(side="bottom", fill="x")

    titulo_fuentes = tk.Label(
        barra_titulo_fuentes, text="☰  FUENTES DE AUDIO   ·   arrastrá para mover el panel",
        bg="#151a24", fg="white", font=(E.FUENTE_UI, 11, "bold"), cursor="fleur"
    )
    titulo_fuentes.pack(side="left", padx=12)
    titulo_fuentes.bind("<ButtonPress-1>", lambda e: _iniciar_arrastre_panel("fuentes"))
    titulo_fuentes.bind("<ButtonRelease-1>", lambda e: _soltar_panel("fuentes", e))

    E.marco_canvas = tk.Frame(E.marco_fuentes, bg="#10141b")
    E.marco_canvas.pack(fill="both", expand=True)

    E.canvas = tk.Canvas(E.marco_canvas, bg="#10141b", highlightthickness=0)
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

    E.panel_fuentes = tk.Frame(E.canvas, bg="#10141b")
    E.canvas.create_window((0, 0), window=E.panel_fuentes, anchor="nw")

    E.panel_fuentes.bind("<Configure>", actualizar_scroll)
    E.canvas.bind("<Configure>", lambda e: (actualizar_scroll(e), mod_ui_tarjeta._al_redimensionar_fuentes(e)))
    E.canvas.bind("<Enter>", _activar_rueda_fuentes)
    E.canvas.bind("<Leave>", _desactivar_rueda_fuentes)


    E.marco_derecho = tk.Frame(E.cuerpo, bg="#10141b")

    E.barra_soundboard = tk.Frame(E.marco_derecho, bg="#151a24", height=40)
    E.barra_soundboard.pack(fill="x")
    E.barra_soundboard.pack_propagate(False)

    tk.Frame(E.barra_soundboard, bg="#17b8b0", width=4).pack(side="left", fill="y")
    tk.Frame(E.barra_soundboard, bg="#2fd693", height=2).pack(side="bottom", fill="x")

    titulo_soundboard = tk.Label(
        E.barra_soundboard, text="☰  Efectos De Sonido",
        bg="#151a24", fg="white", font=(E.FUENTE_UI, 11, "bold"), cursor="fleur"
    )
    titulo_soundboard.pack(side="left", padx=12)
    titulo_soundboard.bind("<ButtonPress-1>", lambda e: _iniciar_arrastre_panel("soundboard"))
    titulo_soundboard.bind("<ButtonRelease-1>", lambda e: _soltar_panel("soundboard", e))

    E.marco_soundboard_scroll = tk.Frame(E.marco_derecho, bg="#10141b")
    E.marco_soundboard_scroll.pack(fill="both", expand=True)

    E.canvas_sb = tk.Canvas(E.marco_soundboard_scroll, bg="#10141b", highlightthickness=0)
    E.scrollbar_sb = ttk.Scrollbar(
        E.marco_soundboard_scroll, orient="vertical", command=E.canvas_sb.yview,
        style="Discreta.Vertical.TScrollbar"
    )
    E.canvas_sb.configure(yscrollcommand=E.scrollbar_sb.set)

    E.canvas_sb.pack(side="left", fill="both", expand=True)

    E.panel_soundboard = tk.Frame(E.canvas_sb, bg="#10141b")
    E.canvas_sb.create_window((0, 0), window=E.panel_soundboard, anchor="nw")

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


def _activar_rueda_fuentes(event):
    E.canvas.bind_all("<MouseWheel>", _rueda_fuentes_vertical)
    E.canvas.bind_all("<Shift-MouseWheel>", _rueda_fuentes_horizontal)


def _desactivar_rueda_fuentes(event):
    E.canvas.unbind_all("<MouseWheel>")
    E.canvas.unbind_all("<Shift-MouseWheel>")


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


def _desactivar_rueda_soundboard(event):
    E.canvas_sb.unbind_all("<MouseWheel>")


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


def _fuentes_tipografia_disponibles():
    """Opciones del selector de tipografía: la predeterminada (la que
    el programa elige sola) más las tipografías propias registradas
    desde la carpeta assets/fuentes que estén disponibles."""
    propias = sorted({f for f in E._NOMBRES_FUENTES_PERSONALIZADAS
                      if f in E._familias_disponibles})
    return [FUENTE_PREDETERMINADA] + propias


def aplicar_fuente_elegida(nombre, guardar=True):
    """Aplica la tipografía elegida a todas las letras del programa
    (textos generales y títulos, que son los que usan FUENTE_UI y
    FUENTE_TITULO). Las fuentes de íconos y emojis (■ ↻ 🔊 🎧) se dejan
    como están a propósito: las tipografías decorativas no traen esos
    símbolos y quedarían en blanco."""
    if not nombre or nombre == FUENTE_PREDETERMINADA:
        E.FUENTE_UI = next((f for f in E._PREFERENCIAS_FUENTE_UI if f in E._familias_disponibles), "TkDefaultFont")
        E.FUENTE_TITULO = next((f for f in E._PREFERENCIAS_FUENTE_TITULO if f in E._familias_disponibles), E.FUENTE_UI)
        E.fuente_elegida = ""
    else:
        if nombre not in E._familias_disponibles:
            return
        E.FUENTE_UI = nombre
        E.FUENTE_TITULO = nombre
        E.fuente_elegida = nombre
    if guardar:
        mod_configuracion.guardar_config_interfaz({"fuente_ui": E.fuente_elegida})


def cambiar_fuente(nombre):
    """Se llama desde el combobox de tipografía del menú de ajustes:
    aplica la fuente elegida y reconstruye la interfaz para que el
    cambio se vea reflejado en todas las letras. La cabecera superior
    (título, subtítulo y estado) no se reconstruye con el resto, así
    que su fuente se actualiza acá en el acto."""
    aplicar_fuente_elegida(nombre)
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


def _actualizar_imagen_velo(forzar=False):
    """Escala la última foto guardada al tamaño actual de la ventana y
    la deja puesta en el velo. Escalar una imagen ya capturada es
    barato (no reconstruye ningún widget), así que esto sí se puede
    llamar en cada evento de arrastre sin volver a generar el lag que
    se quería eliminar: es lo que da la sensación de que la interfaz
    "sigue" al mouse en tiempo real. Igual se limita a una tasa máxima
    (salvo forzar=True al mostrar el velo) porque el reescalado en el
    hilo de la interfaz, evento tras evento, se nota como tironeo."""
    if not forzar:
        ahora = time.monotonic()
        if ahora - E._foto_velo.get("t", 0.0) < INTERVALO_MINIMO_FOTO_VELO_SEG:
            return
        E._foto_velo["t"] = ahora
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
    _actualizar_imagen_velo(forzar=True)
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


def _al_redimensionar_ventana(event):
    """Modelo de sesión de arrastre: del primer evento hasta que la
    ventana se queda quieta del todo se considera UN solo arrastre.
    Durante la sesión no se reconstruye nada (antes se reconstruía en
    cada pausa de 180 ms, y con movimientos suaves eso disparaba un
    rebuild a mitad del arrastre una y otra vez: ese era el parpadeo).
    Lo único que pasa en cada evento es que la foto del velo sigue al
    borde; la reconstrucción (una sola) llega con _fin_arrastre_ventana.
    """
    if event.widget is not E.ventana:
        return
    if E._arrastre_divisor["activo"]:
        # Se agarró el borde a mitad de un arrastre del divisor: la
        # reconstrucción de la ventana ya cubre todo, se transfiere la
        # posta sin reacomodar dos veces.
        _cancelar_arrastre_divisor()
    if E._reconstruccion_en_curso["activa"]:
        # El usuario movió el borde justo mientras se estaba armando:
        # no se toca nada, sólo se extiende la espera de calma.
        if E._trabajo_redimension["id"] is not None:
            E.ventana.after_cancel(E._trabajo_redimension["id"])
        E._trabajo_redimension["id"] = E.ventana.after(
            DEMORA_FIN_ARRASTRE_MS, _fin_arrastre_ventana)
        return
    if not E._arrastre_ventana["activo"]:
        E._arrastre_ventana["activo"] = True
        _mostrar_velo_redimension()
    else:
        if E._trabajo_redimension["id"] is not None:
            E.ventana.after_cancel(E._trabajo_redimension["id"])
        # El velo (con su foto) es la tapa real, así que hay que ir
        # reescalando la foto en cada evento para que siga al borde.
        _actualizar_imagen_velo()
    # Cada evento nuevo reinicia la espera: mientras el usuario siga
    # moviendo, _fin_arrastre_ventana nunca llega a dispararse.
    E._trabajo_redimension["id"] = E.ventana.after(
        DEMORA_FIN_ARRASTRE_MS, _fin_arrastre_ventana)


def _fin_arrastre_ventana():
    """La ventana se quedó quieta: termina la sesión de arrastre y
    recién ahora se evalúa si hace falta reconstruir (una sola vez)."""
    E._trabajo_redimension["id"] = None
    E._arrastre_ventana["activo"] = False
    _aplicar_redimension()


def _aplicar_redimension():
    E._trabajo_redimension["id"] = None

    # Si ya hay una reconstrucción corriendo (poco probable, pero puede
    # pasar si el usuario suelta y vuelve a arrastrar muy rápido),
    # reprogramamos para más tarde en vez de superponerla: lanzar una
    # segunda reconstrucción a mitad de la primera es lo que producía
    # los "bugs visuales" (paneles a medio armar, sashes en posiciones
    # raras, tarjetas duplicadas un instante). El velo (con su foto)
    # sigue puesto mientras tanto, así que no se ve nada raro en el medio.
    if E._reconstruccion_en_curso["activa"]:
        E._trabajo_redimension["id"] = E.ventana.after(
            DEMORA_FIN_ARRASTRE_MS, _aplicar_redimension)
        return

    nuevo_factor = mod_utilidades.factor_escala_ui()
    if abs(nuevo_factor - E._ultimo_factor_escala["valor"]) < 0.03:
        # El arrastre terminó pero el cambio de tamaño fue chico y no
        # amerita reconstruir nada: se reacomoda la grilla una vez (los
        # reacomodos de a mitad del arrastre se saltearon a propósito)
        # y se destapa.
        mod_ui_tarjeta._reubicar_fuentes()
        _ocultar_velo_redimension()
        return
    E._ultimo_factor_escala["valor"] = nuevo_factor

    E._reconstruccion_en_curso["activa"] = True
    if P._ES_WINDOWS:
        P._congelar_pintado_ventana()
    try:
        # El velo (con la foto) ya está puesto desde que arrancó el
        # arrastre (ver _al_redimensionar_ventana), así que durante toda
        # esta reconstrucción el usuario sigue viendo esa foto, nunca
        # los paneles a medio armar. El freeze va sólo acá adentro.
        construir_cuerpo()
        E.ventana.update_idletasks()
    finally:
        if P._ES_WINDOWS:
            P._descongelar_pintado_ventana()
        _ocultar_velo_redimension()
        E._reconstruccion_en_curso["activa"] = False


def al_cerrar():
    try:
        mod_obs_cliente.desconectar_obs()
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

    E.ventana.destroy()
