import os
import tkinter as tk

from tkinter import filedialog, messagebox, simpledialog
from tkinter import font as tkfont

from consola_obs.compat import HAY_PILLOW, Image, ImageDraw, ImageOps, ImageTk
from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import rutas as R
from consola_obs import configuracion as mod_configuracion
from consola_obs import utilidades as mod_utilidades
from consola_obs.audio import reproduccion as mod_audio_reproduccion
from consola_obs.ui import dibujo as mod_ui_dibujo


def asignar_sonido(indice):
    ruta = filedialog.askopenfilename(
        title="Elegí un archivo de audio",
        filetypes=[
            ("Archivos de audio", "*.mp3 *.wav *.ogg *.flac *.m4a"),
            ("Todos los archivos", "*.*")
        ]
    )
    if not ruta:
        return

    datos_previos = E.config_soundboard.get(str(indice), {})

    nombre_boton = simpledialog.askstring(
        "Nombre del sonido",
        "¿Cómo querés llamar a este sonido?",
        initialvalue=datos_previos.get("nombre", os.path.splitext(os.path.basename(ruta))[0])
    )
    if not nombre_boton:
        return

    E.config_soundboard[str(indice)] = {
        "nombre": nombre_boton,
        "archivo": ruta,
        "imagen": datos_previos.get("imagen"),
        "color": datos_previos.get("color"),
    }

    mod_configuracion.guardar_config_soundboard()
    construir_soundboard()


def _abrir_menu_contextual_pad(indice, event):
    """Menú de clic derecho de un pad del soundboard: agrupa acá todo lo
    que antes eran botones sueltos siempre visibles ('🔊 Sonido', '🖼
    Imagen') más el color de etiqueta y, ahora, también renombrar y
    quitar el sonido, para que la grilla se vea limpia."""
    datos = E.config_soundboard.get(str(indice)) or {}
    tiene_sonido = bool(datos.get("archivo"))

    menu = tk.Menu(E.ventana, tearoff=0, bg="#151a24", fg="white", activebackground="#323b4c", activeforeground="white")
    menu.add_command(
        label=("🔊  Cambiar sonido…" if tiene_sonido else "🔊  Asignar sonido…"),
        command=lambda: asignar_sonido(indice)
    )
    if tiene_sonido:
        menu.add_command(label="🖼  Asignar imagen…", command=lambda: asignar_imagen(indice))
        menu.add_command(label="✏  Renombrar…", command=lambda: _iniciar_renombrar_pad(indice))
    menu.add_separator()

    submenu_color = tk.Menu(menu, tearoff=0, bg="#151a24", fg="white", activebackground="#323b4c")
    submenu_color.add_command(label="Sin etiqueta", command=lambda: _asignar_color_pad(indice, None))
    submenu_color.add_separator()
    for color in E.PALETA_ETIQUETAS:
        if color is None:
            continue
        submenu_color.add_command(
            label="        ", background=color, activebackground=color,
            command=lambda c=color: _asignar_color_pad(indice, c)
        )
    menu.add_cascade(label="🏷  Color de etiqueta", menu=submenu_color)

    if tiene_sonido:
        menu.add_separator()
        menu.add_command(label="🗑  Quitar sonido", command=lambda: _quitar_pad(indice))

    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _iniciar_renombrar_pad(indice):
    datos = E.config_soundboard.get(str(indice))
    if not datos or not datos.get("archivo"):
        return
    nuevo_nombre = simpledialog.askstring(
        "Renombrar sonido", "Nuevo nombre para este botón:", initialvalue=datos.get("nombre", "")
    )
    if nuevo_nombre is None:
        return
    nuevo_nombre = nuevo_nombre.strip()
    if not nuevo_nombre:
        return
    datos["nombre"] = nuevo_nombre
    mod_configuracion.guardar_config_soundboard()
    construir_soundboard()


def _quitar_pad(indice):
    if not messagebox.askyesno("Quitar sonido", "¿Quitar el sonido asignado a este botón?"):
        return
    color = (E.config_soundboard.get(str(indice)) or {}).get("color")
    if color:
        E.config_soundboard[str(indice)] = {"nombre": None, "archivo": None, "imagen": None, "color": color}
    else:
        E.config_soundboard.pop(str(indice), None)
    for clave in [c for c in E.miniaturas_cargadas if c[0] == indice]:
        E.miniaturas_cargadas.pop(clave, None)
    mod_configuracion.guardar_config_soundboard()
    construir_soundboard()


def _pad_bajo_puntero(x_root, y_root):
    try:
        widget = E.ventana.winfo_containing(x_root, y_root)
    except Exception:
        return None
    while widget is not None:
        indice = getattr(widget, "indice_pad", None)
        if indice is not None:
            return indice
        widget = widget.master
    return None


def _borde_normal_pad(indice):
    # La celda siempre es invisible (mismo color que el panel): el color
    # de la etiqueta ya no se pinta acá afuera, sino en el marco de la
    # propia placa de vidrio (ver "color_marco" en _imagen_placa), así
    # no queda un cuadrado de color suelto alrededor del pad.
    return C.COLOR_PANEL_SOUNDBOARD, 2


def _restablecer_borde_pad(indice):
    celda = E._celdas_pads.get(indice)
    if not celda:
        return
    color, grosor = _borde_normal_pad(indice)
    celda.config(highlightbackground=color, highlightthickness=grosor)


def _resaltar_destino_pad(indice_nuevo):
    anterior = E._arrastre_pad["destino_resaltado"]
    if anterior == indice_nuevo:
        return
    if anterior is not None:
        _restablecer_borde_pad(anterior)
    if indice_nuevo is not None:
        celda = E._celdas_pads.get(indice_nuevo)
        if celda:
            celda.config(highlightbackground="#2fd693", highlightthickness=3)
    E._arrastre_pad["destino_resaltado"] = indice_nuevo


def _limpiar_resaltado_pads():
    anterior = E._arrastre_pad["destino_resaltado"]
    if anterior is not None:
        _restablecer_borde_pad(anterior)
    E._arrastre_pad["destino_resaltado"] = None


def _iniciar_arrastre_pad(indice, event):
    E._arrastre_pad["indice"] = indice
    E._arrastre_pad["arrastrando"] = False
    E._arrastre_pad["x_inicio"] = event.x_root
    E._arrastre_pad["y_inicio"] = event.y_root


def _mover_arrastre_pad(indice, event):
    datos = E._arrastre_pad
    if datos["indice"] != indice:
        return
    if not datos["arrastrando"]:
        dx = abs(event.x_root - datos["x_inicio"])
        dy = abs(event.y_root - datos["y_inicio"])
        if dx < C.UMBRAL_ARRASTRE_PX and dy < C.UMBRAL_ARRASTRE_PX:
            return
        datos["arrastrando"] = True
    _resaltar_destino_pad(_pad_bajo_puntero(event.x_root, event.y_root))


def _soltar_arrastre_pad(indice, event):
    datos = E._arrastre_pad
    if datos["indice"] != indice:
        return
    fue_arrastre = datos["arrastrando"]
    datos["indice"] = None
    datos["arrastrando"] = False
    _limpiar_resaltado_pads()
    if not fue_arrastre:
        mod_audio_reproduccion.reproducir_sonido(indice)
        return
    destino = _pad_bajo_puntero(event.x_root, event.y_root)
    if destino is None or destino == indice:
        return
    _reordenar_pad(indice, destino)


def _reordenar_pad(indice_origen, indice_destino):
    """Intercambia el contenido de dos pads (arrastrar y soltar un pad
    sobre otro para acomodarlos donde el usuario quiera): a diferencia
    del orden de las fuentes, acá se hace un intercambio simple porque
    los pads ocupan siempre una grilla de posiciones fijas."""
    if indice_origen == indice_destino:
        return
    clave_o, clave_d = str(indice_origen), str(indice_destino)
    datos_o = E.config_soundboard.get(clave_o)
    datos_d = E.config_soundboard.get(clave_d)

    if datos_d is not None:
        E.config_soundboard[clave_o] = datos_d
    else:
        E.config_soundboard.pop(clave_o, None)
    if datos_o is not None:
        E.config_soundboard[clave_d] = datos_o
    else:
        E.config_soundboard.pop(clave_d, None)

    for indice in (indice_origen, indice_destino):
        for clave in [c for c in E.miniaturas_cargadas if c[0] == indice]:
            E.miniaturas_cargadas.pop(clave, None)

    mod_configuracion.guardar_config_soundboard()
    construir_soundboard()


def _asignar_color_pad(indice, color):
    datos = E.config_soundboard.setdefault(str(indice), {})
    datos.setdefault("nombre", None)
    datos.setdefault("archivo", None)
    datos.setdefault("imagen", None)
    if color is None:
        datos.pop("color", None)
    else:
        datos["color"] = color
    if not datos.get("archivo") and not datos.get("imagen") and not datos.get("color"):
        E.config_soundboard.pop(str(indice), None)
    mod_configuracion.guardar_config_soundboard()
    construir_soundboard()


def asignar_imagen(indice):
    if not E.config_soundboard.get(str(indice), {}).get("archivo"):
        messagebox.showwarning(
            "Asigná un sonido primero",
            "Elegí un archivo de audio para este botón antes de ponerle una imagen."
        )
        return

    ruta_imagen = filedialog.askopenfilename(
        title="Elegí una imagen para este sonido",
        filetypes=[
            ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp"),
            ("Todos los archivos", "*.*")
        ]
    )
    if not ruta_imagen:
        return

    E.config_soundboard[str(indice)]["imagen"] = ruta_imagen
    for clave in [c for c in E.miniaturas_cargadas if c[0] == indice]:
        E.miniaturas_cargadas.pop(clave, None)

    mod_configuracion.guardar_config_soundboard()
    construir_soundboard()


def _partir_palabra_larga(palabra, fuente, ancho_max):
    """Corta a la fuerza una palabra que ni sola entra en el ancho
    (nombres sin espacios, como 'sali-de-ahi-maravilla...'): Tk hace lo
    mismo al dibujar, así la medición coincide con lo que se ve."""
    partes, actual = [], ""
    for caracter in palabra:
        if fuente.measure(actual + caracter) <= ancho_max:
            actual += caracter
        else:
            if actual:
                partes.append(actual)
            actual = caracter.lstrip()
    if actual:
        partes.append(actual)
    return partes or [palabra]


def _envolver_nombre_pad(texto, fuente, ancho_max):
    """Parte el nombre en líneas que entran en ancho_max píxeles,
    cortando por palabra completa (igual criterio que las tarjetas).
    Las continuaciones de una palabra larga se pegan SIN espacio, tal
    cual las dibuja Tk."""
    palabras = texto.split()
    if not palabras:
        return [texto]
    piezas = []
    for indice_palabra, palabra in enumerate(palabras):
        if fuente.measure(palabra) <= ancho_max:
            piezas.append((palabra, indice_palabra > 0))
        else:
            partes = _partir_palabra_larga(palabra, fuente, ancho_max)
            for i, parte in enumerate(partes):
                piezas.append((parte, indice_palabra > 0 and i == 0))
    lineas = []
    actual = ""
    for parte, con_espacio in piezas:
        if actual:
            candidato = actual + (" " if con_espacio else "") + parte
        else:
            candidato = parte
        if fuente.measure(candidato) <= ancho_max:
            actual = candidato
        else:
            lineas.append(actual)
            actual = parte
    lineas.append(actual)
    return lineas


RENGLONES_NOMBRE_PAD = 2
TAM_MIN_NOMBRE_PAD = 6


def _ajustar_nombre_pad(texto, familia, tam_max, ancho_max):
    """Achica la letra hasta que el nombre entre en RENGLONES_NOMBRE_PAD
    renglones; si ni al mínimo entra, lo recorta con …. Devuelve
    (tamaño, texto_a_mostrar). Así todas las etiquetas miden lo mismo
    y las celdas de la grilla quedan alineadas y del mismo tamaño."""
    tam = max(TAM_MIN_NOMBRE_PAD, int(tam_max))
    while tam > TAM_MIN_NOMBRE_PAD:
        fuente = tkfont.Font(family=familia, size=tam, weight="bold")
        if len(_envolver_nombre_pad(texto, fuente, ancho_max)) <= RENGLONES_NOMBRE_PAD:
            return tam, texto
        tam -= 1
    fuente = tkfont.Font(family=familia, size=TAM_MIN_NOMBRE_PAD, weight="bold")
    if len(_envolver_nombre_pad(texto, fuente, ancho_max)) <= RENGLONES_NOMBRE_PAD:
        return TAM_MIN_NOMBRE_PAD, texto
    recortado = texto
    while recortado and len(_envolver_nombre_pad(recortado + "…", fuente, ancho_max)) > RENGLONES_NOMBRE_PAD:
        recortado = recortado[:-1].rstrip()
    return TAM_MIN_NOMBRE_PAD, (recortado.rstrip() + "…") if recortado else "…"


def _geometria_cara_placa(ancho, alto):
    """Calcula la caja (x0, y0, x1, y1) y el radio de esquina de la CARA
    de un pad de 'ancho' x 'alto', con las mismas proporciones que usa
    _imagen_placa para dibujar marco/foso/cara. Se usa para que la
    miniatura del sonido encaje exactamente en ese hueco, en vez de
    quedar como un cuadrado más chico y descentrado."""
    ancho, alto = max(1, int(ancho)), max(1, int(alto))
    lado = min(ancho, alto)
    margen = max(1, round(lado * 0.035))
    grosor_marco = max(1, round(lado * 0.018))
    grosor_foso = max(1, round(lado * 0.009))
    radio = max(2, round(lado * 0.235))

    x0e, y0e = margen, margen
    x1e, y1e = ancho - 1 - margen, alto - 1 - margen
    x0f, y0f = x0e + grosor_marco, y0e + grosor_marco
    x1f, y1f = x1e - grosor_marco, y1e - grosor_marco
    x0c, y0c = x0f + grosor_foso, y0f + grosor_foso
    x1c, y1c = x1f - grosor_foso, y1f - grosor_foso

    radio_foso = max(2, radio - grosor_marco)
    radio_cara = max(2, radio_foso - grosor_foso)
    return (x0c, y0c, x1c, y1c), radio_cara


def _redimensionar_para_entrar(imagen, ancho_obj, alto_obj, radio=None):
    """Estira la imagen para que ocupe EXACTAMENTE el tamaño del pad
    (mismo ancho y alto que el recuadro), sin dejar bordes vacíos y sin
    recortar ninguna parte: se ve completa, de punta a punta. Si la
    imagen original no es cuadrada va a verse levemente estirada, pero
    eso es preferible a que le sobre marco vacío o que se le corte un
    pedazo.

    El remuestreo ahora es LANCZOS y no NEAREST. NEAREST copia el pixel
    más cercano y listo: cuando la imagen original es más chica que el
    pad (o no es un múltiplo exacto), eso se ve literalmente como
    bloques cuadrados y bordes en escalera -el "pixelado" de antes-.
    LANCZOS promedia el vecindario de cada pixel, así que las diagonales
    y las curvas de la imagen quedan suaves a cualquier tamaño de pad."""
    ancho_obj = max(1, round(ancho_obj))
    alto_obj = max(1, round(alto_obj))
    if radio is None:
        radio = max(2, round(min(ancho_obj, alto_obj) * 0.12))

    ancho_intermedio = ancho_obj * 4
    alto_intermedio = alto_obj * 4
    if imagen.width > ancho_intermedio or imagen.height > alto_intermedio:
        imagen.thumbnail((ancho_intermedio, alto_intermedio), Image.LANCZOS)

    imagen = imagen.resize((ancho_obj, alto_obj), Image.LANCZOS).convert("RGBA")

    # Las esquinas se redondean con una máscara suavizada (dibujada al
    # cuádruple y reducida) para que la miniatura acompañe la curva de
    # la cara del pad en vez de quedar como un recuadro pegado encima.
    mascara = Image.new("L", (ancho_obj * 4, alto_obj * 4), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        [0, 0, ancho_obj * 4 - 1, alto_obj * 4 - 1], radius=max(1, radio) * 4, fill=255
    )
    imagen.putalpha(mascara.resize((ancho_obj, alto_obj), Image.LANCZOS))
    return imagen


def _obtener_imagen_decodificada(ruta_imagen):
    """Devuelve la imagen ya abierta y decodificada por Pillow (con
    exif_transpose y conversión de modo aplicados), cacheada por ruta
    de archivo. Esta es la parte cara (leer el archivo del disco y
    decodificarlo) y sólo se hace una vez por archivo, sin importar
    cuántas veces se pida después con distintos tamaños de pad."""
    if ruta_imagen in E._imagenes_decodificadas_cache:
        return E._imagenes_decodificadas_cache[ruta_imagen]

    imagen = Image.open(ruta_imagen)
    imagen = ImageOps.exif_transpose(imagen)
    if imagen.mode not in ("RGB", "RGBA"):
        imagen = imagen.convert("RGBA")

    # Si el archivo original es enorme (foto de celular, captura 4K),
    # la reducimos una sola vez acá a un tamaño "de sobra" para
    # cualquier pad, así las decodificaciones y resizes posteriores
    # trabajan siempre sobre una imagen chica en vez de la original.
    TAMANO_MAXIMO_CACHE = (900, 900)
    if imagen.width > TAMANO_MAXIMO_CACHE[0] or imagen.height > TAMANO_MAXIMO_CACHE[1]:
        imagen.thumbnail(TAMANO_MAXIMO_CACHE, Image.BOX)

    E._imagenes_decodificadas_cache[ruta_imagen] = imagen
    return imagen


def cargar_miniatura(indice, ruta_imagen, tamano, radio=None):
    """Carga (con caché) la imagen del pad ``indice`` ya redimensionada
    para entrar completa dentro de ``tamano`` = (ancho, alto), sin
    recortarla. Funciona con imágenes de cualquier tamaño de origen: las
    grandes (fotos de celular, capturas 4K, etc.) se abren igual y se
    reducen acá mismo antes de mostrarlas.

    La apertura y decodificación del archivo (lo caro) está separada
    en _obtener_imagen_decodificada y cacheada por ruta; acá sólo se
    cachea, por (indice, tamano), el PhotoImage final ya al tamaño del
    pad, que es una operación barata de repetir."""
    clave_cache = (indice, tamano, radio)
    if clave_cache in E.miniaturas_cargadas:
        return E.miniaturas_cargadas[clave_cache]

    ancho_obj, alto_obj = tamano

    try:
        if HAY_PILLOW:
            imagen = _obtener_imagen_decodificada(ruta_imagen)
            imagen = _redimensionar_para_entrar(imagen, ancho_obj, alto_obj, radio)
            foto = ImageTk.PhotoImage(imagen)
        else:
            foto = tk.PhotoImage(file=ruta_imagen)

        E.miniaturas_cargadas[clave_cache] = foto
        return foto
    except Exception as e:
        print(f"No se pudo cargar la imagen del botón {indice}: {e}")
        return None



def _refrescar_iluminacion_pad(indice):
    """Vuelve a pintar UN pad puntual con su estado actual (llama a la
    función que construir_soundboard() dejó guardada en
    _refrescos_pads). No hace nada si ese pad no está construido en
    este momento (por ejemplo, si se acaba de borrar)."""
    refrescar = E._refrescos_pads.get(indice)
    if refrescar is not None:
        refrescar()


def _fijar_pad_activo(indice):
    """Único lugar que cambia _sesion_reproduccion['indice']: además de
    guardar cuál es el pad "activo" (el que se apaga con fundido si se
    lo vuelve a tocar), prende o apaga el brillo del pad que
    corresponda en la interfaz. SIEMPRE hay que llamarla desde el hilo
    principal -si el aviso viene de un hilo de fondo, primero hay que
    pasarlo por ventana.after(0, ...)."""
    anterior = E._sesion_reproduccion.get("indice")
    if anterior == indice:
        return
    E._sesion_reproduccion["indice"] = indice
    if anterior is not None:
        _refrescar_iluminacion_pad(anterior)
    if indice is not None:
        _refrescar_iluminacion_pad(indice)


def _apagar_pad_si_token_vigente(indice, token):
    """Apaga el pad SOLO si el token que lo prendió sigue siendo el
    vigente -si mientras tanto arrancó otra reproducción (el mismo pad
    reiniciado, o cualquier otro), no tocamos nada: esa reproducción
    nueva es la que manda ahora."""
    if E._sesion_reproduccion.get("token") == token:
        _fijar_pad_activo(None)



def _columnas_disponibles():
    ancho_disponible = E.canvas_sb.winfo_width()
    ancho_celda_con_padding = mod_utilidades.medida_actual()["pad_ancho"] + 20
    if ancho_disponible <= 1 or ancho_celda_con_padding <= 0:
        return E.columnas_soundboard
    columnas_actuales = max(1, E.columnas_soundboard)
    columnas_teoricas = max(1, ancho_disponible // ancho_celda_con_padding)
    if columnas_teoricas >= columnas_actuales:
        return columnas_teoricas
    # Mismo colchón que en la grilla de fuentes (ver
    # MARGEN_HISTERESIS_COLUMNAS): que el panel se achique "apenas un
    # poco" no debe tirar de golpe una columna entera de pads a la fila
    # de abajo.
    espacio_necesario = columnas_actuales * ancho_celda_con_padding
    if espacio_necesario - ancho_disponible <= C.MARGEN_HISTERESIS_COLUMNAS:
        return columnas_actuales
    return columnas_teoricas


def _arrastre_ventana_en_curso():
    """True mientras el usuario está arrastrando el borde de LA VENTANA
    (no el divisor entre paneles) y todavía no se soltó: es la ventana
    de tiempo en la que _al_redimensionar_ventana ya mostró el velo y
    está esperando a que el arrastre se quede quieto para reconstruir
    todo de una (ver _trabajo_redimension, más abajo en el archivo).
    Se consulta con try/except porque ese nombre se define más adelante
    en el archivo (mismo motivo que el try/except de velo_redimension
    en construir_cuerpo): a esta altura de la carga del módulo todavía
    no existe, pero para cuando esta función se llegue a llamar de
    verdad (el usuario ya movió el mouse) sí."""
    try:
        return E._trabajo_redimension["id"] is not None
    except NameError:
        return False


def _al_redimensionar_soundboard(event=None):
    """Recalcula cuántas columnas entran en el ancho actual y sólo
    reconstruye la grilla si ese número cambió (o si el ancho se movió
    lo suficiente como para que las celdas ya no encajen bien, ver
    _ultimo_ancho_soundboard).

    Mientras el usuario está arrastrando el borde de LA VENTANA, este
    handler no programa nada: esta grilla destruye y vuelve a crear
    todos los pads, y hacerlo en cada pixel de arrastre (aunque sea con
    espera de 16ms) es trabajo pesado compitiendo por CPU con el propio
    arrastre, y ESO es lo que se veía como parpadeo/tironeo de la
    ventana. En vez de eso, se deja que el mecanismo de toda la ventana
    (_al_redimensionar_ventana/_aplicar_redimension, más abajo) haga UNA
    sola reconstrucción completa (construir_cuerpo → construir_soundboard)
    recién cuando el usuario suelta el borde, tapada por el velo. Fuera
    de un arrastre de ventana (por ejemplo, moviendo el divisor entre
    paneles) el comportamiento no cambia: se sigue esperando sólo el
    toque de calma de 16ms de siempre."""
    if _arrastre_ventana_en_curso():
        return
    if E._trabajo_redimension_soundboard["id"] is not None:
        E.ventana.after_cancel(E._trabajo_redimension_soundboard["id"])
    # Ídem comentario en el redimensionado del panel de fuentes: 16ms
    # es, en la práctica, "apenas se puede".
    E._trabajo_redimension_soundboard["id"] = E.ventana.after(16, _aplicar_redimension_soundboard)


def _aplicar_redimension_soundboard():
    E._trabajo_redimension_soundboard["id"] = None
    if (E._reconstruccion_en_curso["activa"] or E._arrastre_ventana["activo"]
            or E._trabajo_redimension["id"] is not None):
        # Idem grilla de fuentes: a mitad de un arrastre no se
        # reconstruye nada (la reconstrucción de fin de arrastre deja
        # todo en su lugar). El reintento se agota solo.
        E._trabajo_redimension_soundboard["id"] = E.ventana.after(150, _aplicar_redimension_soundboard)
        return
    nuevas_columnas = _columnas_disponibles()
    ancho_actual = E.canvas_sb.winfo_width()
    ancho_referencia = E._ultimo_ancho_soundboard["valor"]
    ancho_se_corrio_de_mas = (
        ancho_actual > 1
        and ancho_referencia is not None
        and abs(ancho_actual - ancho_referencia) > C.MARGEN_REAJUSTE_ANCHO_SOUNDBOARD
    )
    if nuevas_columnas != E.columnas_soundboard or ancho_se_corrio_de_mas:
        E.columnas_soundboard = nuevas_columnas
        construir_soundboard()


def construir_soundboard():
    E._ultimo_ancho_soundboard["valor"] = E.canvas_sb.winfo_width()
    for widget in E.panel_soundboard.winfo_children():
        widget.destroy()

    columnas = max(1, E.columnas_soundboard)
    medida = mod_utilidades.medida_actual()

    ancho_preferido = medida["pad_ancho"]
    ancho_disponible = E.canvas_sb.winfo_width()
    padding_por_celda = 20
    if ancho_disponible > 1:
        ancho_celda = max(ancho_preferido, (ancho_disponible // columnas) - padding_por_celda)
    else:
        ancho_celda = ancho_preferido

    ancho_imagen_pad_base = ancho_celda - 12
    pie_celda = 76
    alto_celda = ancho_imagen_pad_base + pie_celda

    marco_grid = tk.Frame(E.panel_soundboard, bg=C.COLOR_PANEL_SOUNDBOARD)
    marco_grid.pack(fill="x")

    E._celdas_pads.clear()
    E._refrescos_pads.clear()

    for i in range(E.num_pads_soundboard):
        fila = i // columnas
        col = i % columnas

        datos = E.config_soundboard.get(str(i))
        tiene_sonido = bool(datos and datos.get("archivo"))

        def _detener(idx=i):
            mod_audio_reproduccion.detener_sonido(idx)

        def _reiniciar(idx=i):
            mod_audio_reproduccion.reiniciar_sonido(idx)

        color_etiqueta_pad = datos.get("color") if datos else None
        # La celda ya no es una "tarjeta" gris: es transparente contra el
        # panel, así lo único que se ve es la placa de vidrio del pad.
        # El color de la etiqueta YA NO se pinta acá afuera (eso se veía
        # como un cuadrado suelto rodeando la placa): ahora se aplica
        # directamente sobre el marco metálico de la propia placa, más
        # abajo, vía "color_marco".
        celda = tk.Frame(
            marco_grid, bg=C.COLOR_PANEL_SOUNDBOARD, width=ancho_celda, height=alto_celda,
            highlightbackground=C.COLOR_PANEL_SOUNDBOARD, highlightthickness=2
        )
        celda.grid(row=fila, column=col, padx=6, pady=6)
        celda.grid_propagate(False)
        celda.indice_pad = i
        E._celdas_pads[i] = celda
        # Clic izquierdo sostenido y arrastrado = mover el pad de lugar
        # (soltarlo sobre otro pad los intercambia); clic simple sin
        # arrastre = reproducir. Clic derecho = menú con el resto de las
        # acciones.
        celda.bind("<ButtonPress-1>", lambda e, idx=i: _iniciar_arrastre_pad(idx, e))
        celda.bind("<B1-Motion>", lambda e, idx=i: _mover_arrastre_pad(idx, e))
        celda.bind("<ButtonRelease-1>", lambda e, idx=i: _soltar_arrastre_pad(idx, e))
        celda.bind("<Button-3>", lambda e, idx=i: _abrir_menu_contextual_pad(idx, e))

        ancho_imagen_pad = ancho_celda - 12
        alto_pad_principal = ancho_imagen_pad
        pad_canvas = tk.Canvas(
            celda, width=ancho_imagen_pad, height=alto_pad_principal,
            bg=C.COLOR_PANEL_SOUNDBOARD, highlightthickness=0, cursor="hand2"
        )
        pad_canvas.pack(pady=(8, 4))

        # Color de acento del pad: el que eligió el usuario si puso uno,
        # el verde de la consola si tiene sonido, y nada (gris de fábrica)
        # si está vacío.
        acento_pad = color_etiqueta_pad or ("#2fd693" if tiene_sonido else None)

        pad_esta_sonando = E._sesion_reproduccion.get("indice") == i
        placa_normal = mod_ui_dibujo._placa_tk(ancho_imagen_pad, alto_pad_principal, acento_pad, tiene_sonido,
                                  color_marco=color_etiqueta_pad, reproduciendo=pad_esta_sonando)
        if placa_normal is not None:
            pad_canvas.imagen_placa = placa_normal
            id_placa = pad_canvas.create_image(0, 0, anchor="nw", image=placa_normal)

            def _pintar_placa(canvas=pad_canvas, id_img=id_placa, w=ancho_imagen_pad,
                              h=alto_pad_principal, acento=acento_pad, enc=tiene_sonido,
                              hover=False, presionado=False, reproduciendo=False,
                              color_marco=color_etiqueta_pad):
                foto = mod_ui_dibujo._placa_tk(w, h, acento, enc, hover, presionado, color_marco=color_marco,
                                  reproduciendo=reproduciendo)
                if foto is not None:
                    canvas.imagen_placa = foto
                    canvas.itemconfig(id_img, image=foto)
        else:
            # Respaldo sin Pillow: se sigue usando el dibujo viejo de Tk.
            mod_ui_dibujo._dibujar_boton_vidrio(
                pad_canvas, 1, 1, ancho_imagen_pad - 1, alto_pad_principal - 1,
                ("#146b58" if tiene_sonido else "#2a3243"), grosor=3
            )
            _pintar_placa = None

        # Estado del mouse sobre este pad puntual, para poder
        # combinarlo con "reproduciendo" (que puede cambiar en
        # cualquier momento, sin que el mouse se haya movido) cada vez
        # que se repinta la placa.
        _estado_mouse_pad = {"hover": False, "presionado": False}

        def _refrescar_pad(hover=None, presionado=None, f=_pintar_placa, idx=i, estado=_estado_mouse_pad):
            if f is None:
                return
            if hover is not None:
                estado["hover"] = hover
            if presionado is not None:
                estado["presionado"] = presionado
            f(hover=estado["hover"], presionado=estado["presionado"],
              reproduciendo=(E._sesion_reproduccion.get("indice") == idx))

        E._refrescos_pads[i] = _refrescar_pad

        if _pintar_placa is not None:
            pad_canvas.bind("<Enter>", lambda e, r=_refrescar_pad: r(hover=True))
            pad_canvas.bind("<Leave>", lambda e, r=_refrescar_pad: r(hover=False))

        ruta_imagen = datos.get("imagen") if datos else None
        # La imagen ocupa EXACTAMENTE la cara del pad (misma caja y mismo
        # radio de esquina que dibuja _imagen_placa), así llega de punta a
        # punta hasta el borde del foso sin quedar descentrada ni con las
        # esquinas cortadas en un radio distinto al del pad.
        caja_cara_img, radio_cara_img = _geometria_cara_placa(ancho_imagen_pad, alto_pad_principal)
        ancho_cara_img = max(1, round(caja_cara_img[2] - caja_cara_img[0]))
        alto_cara_img = max(1, round(caja_cara_img[3] - caja_cara_img[1]))
        miniatura = (
            cargar_miniatura(i, ruta_imagen, (ancho_cara_img, alto_cara_img), radio_cara_img)
            if ruta_imagen else None
        )

        if miniatura is not None:
            pad_canvas.create_image(caja_cara_img[0], caja_cara_img[1], anchor="nw", image=miniatura)
        else:
            # Antes se dibujaba el glifo de fuente "▶": la mayoría de las
            # tipografías no lo centran dentro de su propio cuadro de
            # letra (le sobra aire de un lado), así que a simple vista se
            # veía corrido. Acá el triángulo se arma a mano con un
            # polígono cuya caja envolvente sí queda perfectamente
            # centrada en el pad, sin depender de cómo cada fuente
            # decida dibujar el carácter.
            cx = ancho_imagen_pad / 2
            cy = alto_pad_principal / 2
            lado_pad = min(ancho_imagen_pad, alto_pad_principal)
            medio_alto_tri = lado_pad * 0.17
            medio_ancho_tri = medio_alto_tri * 0.85
            pad_canvas.create_polygon(
                cx - medio_ancho_tri, cy - medio_alto_tri,
                cx - medio_ancho_tri, cy + medio_alto_tri,
                cx + medio_ancho_tri, cy,
                fill=("#eaf4ff" if tiene_sonido else "#55637d"), outline=""
            )

        def _al_presionar(e, idx=i, r=_refrescar_pad):
            r(presionado=True)
            _iniciar_arrastre_pad(idx, e)

        def _al_soltar(e, idx=i, r=_refrescar_pad):
            r(presionado=False, hover=True)
            _soltar_arrastre_pad(idx, e)

        pad_canvas.bind("<ButtonPress-1>", _al_presionar)
        pad_canvas.bind("<B1-Motion>", lambda e, idx=i: _mover_arrastre_pad(idx, e))
        pad_canvas.bind("<ButtonRelease-1>", _al_soltar)
        pad_canvas.bind("<Button-3>", lambda e, idx=i: _abrir_menu_contextual_pad(idx, e))

        # La etiqueta mide SIEMPRE lo mismo (alto fijo de 2 renglones,
        # texto centrado): así todas las celdas quedan del mismo tamaño
        # y alineadas entre sí, tengan el nombre corto o largo.
        if tiene_sonido:
            tam_nombre_pad, nombre_mostrado = _ajustar_nombre_pad(
                datos["nombre"], E.FUENTE_UI, medida["fuente_pad_texto"], ancho_celda - 16)
        else:
            tam_nombre_pad, nombre_mostrado = medida["fuente_pad_texto"], "— VACÍO —"
        etiqueta_nombre_pad = tk.Label(
            celda,
            text=nombre_mostrado,
            bg=C.COLOR_PANEL_SOUNDBOARD,
            fg="white" if tiene_sonido else "#79859f",
            font=(E.FUENTE_UI, tam_nombre_pad, "bold"),
            wraplength=ancho_celda - 16,
            justify="center",
            anchor="center",
            height=RENGLONES_NOMBRE_PAD,
        )
        etiqueta_nombre_pad.pack(pady=(0, 4))
        etiqueta_nombre_pad.bind("<ButtonPress-1>", lambda e, idx=i: _iniciar_arrastre_pad(idx, e))
        etiqueta_nombre_pad.bind("<B1-Motion>", lambda e, idx=i: _mover_arrastre_pad(idx, e))
        etiqueta_nombre_pad.bind("<ButtonRelease-1>", lambda e, idx=i: _soltar_arrastre_pad(idx, e))
        etiqueta_nombre_pad.bind("<Button-3>", lambda e, idx=i: _abrir_menu_contextual_pad(idx, e))

        fila_botones = tk.Frame(celda, bg=C.COLOR_PANEL_SOUNDBOARD)
        fila_botones.pack()

        boton_stop = mod_ui_dibujo._crear_boton_circular(
            fila_botones, "■", medida["diametro_pad_chico"], medida["fuente_pad_icono"],
            "#ff5567", _detener
        )
        boton_stop.pack(side="left", padx=4)

        boton_reiniciar = mod_ui_dibujo._crear_boton_circular(
            fila_botones, "↻", medida["diametro_pad_chico"], medida["fuente_pad_icono"],
            "#566070", _reiniciar
        )
        boton_reiniciar.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # BOTÓN "DETECTAR SONIDOS": crea un pad por cada audio nuevo de la
    # carpeta Sondidos_pad (con su imagen gemela si existe).
    # ------------------------------------------------------------------
    marco_detectar = tk.Frame(E.panel_soundboard, bg=C.COLOR_PANEL_SOUNDBOARD)
    marco_detectar.pack(fill="x")
    boton_detectar = tk.Button(
        marco_detectar, text="🔍 DETECTAR SONIDOS DE LA CARPETA",
        bg="#242d3d", fg="#4fe3ae", activebackground="#2e3a4f",
        activeforeground="#4fe3ae", relief="flat", bd=0, pady=6,
        font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=lambda: detectar_sonidos_carpeta(avisar=True),
    )
    boton_detectar.pack(fill="x", padx=6, pady=(4, 2))

    # ------------------------------------------------------------------
    # BOTÓN "AGREGAR PAD": misma placa de vidrio, en formato barra ancha
    # ------------------------------------------------------------------
    alto_barra_agregar = max(62, round(76 * mod_utilidades.factor_escala_ui()))

    marco_agregar = tk.Frame(E.panel_soundboard, bg=C.COLOR_PANEL_SOUNDBOARD)
    marco_agregar.pack(fill="x")

    celda_mas = tk.Frame(
        marco_agregar, bg=C.COLOR_PANEL_SOUNDBOARD, height=alto_barra_agregar,
        highlightthickness=0, cursor="hand2"
    )
    celda_mas.pack(fill="x", padx=6, pady=(4, 10))
    celda_mas.pack_propagate(False)

    canvas_mas = tk.Canvas(celda_mas, bg=C.COLOR_PANEL_SOUNDBOARD, highlightthickness=0, cursor="hand2")
    canvas_mas.pack(fill="both", expand=True)

    _estado_mas = {"hover": False, "ancho": 0, "alto": 0, "pendiente": None}

    def _pintar_boton_mas(forzar=False):
        ancho_mas = canvas_mas.winfo_width() or 240
        alto_mas = canvas_mas.winfo_height() or alto_barra_agregar
        if not forzar and (ancho_mas, alto_mas) == (_estado_mas["ancho"], _estado_mas["alto"]):
            return
        _estado_mas["ancho"], _estado_mas["alto"] = ancho_mas, alto_mas
        canvas_mas.delete("all")

        # Misma placa que los pads: en reposo va sin color (gris
        # azulado, igual que un pad vacío) y sólo se tiñe de verde
        # cuando el mouse está encima, para que se lea como "acción".
        placa = mod_ui_dibujo._placa_tk(
            ancho_mas, alto_mas,
            "#2fd693" if _estado_mas["hover"] else None,
            False, _estado_mas["hover"]
        )
        if placa is not None:
            canvas_mas.imagen_placa = placa
            canvas_mas.create_image(0, 0, anchor="nw", image=placa)
        else:
            mod_ui_dibujo._dibujar_boton_vidrio(canvas_mas, 1, 1, ancho_mas - 1, alto_mas - 1, "#2a3243", grosor=3)

        # El "+" y el texto crecen con la barra (en vez de un tamaño
        # fijo chico): se miden y se centran como un solo conjunto.
        tam_mas = max(22, round(alto_mas * 0.50))
        tam_agregar = max(11, round(alto_mas * 0.30))
        texto_agregar = "AGREGAR PAD"
        fuente_mas = tkfont.Font(family=E.FUENTE_UI, size=tam_mas, weight="bold")
        fuente_agregar = tkfont.Font(family=E.FUENTE_UI, size=tam_agregar, weight="bold")
        while (fuente_mas.measure("+") + 18 + fuente_agregar.measure(texto_agregar)
               > max(120, ancho_mas - 40)) and tam_agregar > 10:
            tam_mas = max(18, tam_mas - 2)
            tam_agregar -= 1
            fuente_mas = tkfont.Font(family=E.FUENTE_UI, size=tam_mas, weight="bold")
            fuente_agregar = tkfont.Font(family=E.FUENTE_UI, size=tam_agregar, weight="bold")
        ancho_mas_txt = fuente_mas.measure("+")
        ancho_agregar_txt = fuente_agregar.measure(texto_agregar)
        x_mas = ancho_mas / 2 - (ancho_mas_txt + 18 + ancho_agregar_txt) / 2 + ancho_mas_txt / 2
        x_agregar = x_mas + ancho_mas_txt / 2 + 18 + ancho_agregar_txt / 2
        canvas_mas.create_text(
            x_mas, alto_mas / 2, text="+", fill="#4fe3ae",
            font=(E.FUENTE_UI, tam_mas, "bold")
        )
        canvas_mas.create_text(
            x_agregar, alto_mas / 2, text=texto_agregar, fill="#c3cee5",
            font=(E.FUENTE_UI, tam_agregar, "bold")
        )

    def _redibujar_boton_mas(event=None, forzar=False):
        # El render de la placa (PIL supersampleado) es lo más caro que
        # se repinta en cada evento de redimensionado: con debounce se
        # limita a ~12 renders por segundo durante el arrastre, y el
        # pendiente garantiza que igual converge al tamaño final. El
        # hover va con forzar=True (respuesta inmediata, sin espera).
        if forzar:
            if _estado_mas.get("pendiente") is not None:
                try:
                    E.ventana.after_cancel(_estado_mas["pendiente"])
                except Exception:
                    pass
                _estado_mas["pendiente"] = None
            try:
                _pintar_boton_mas(forzar=True)
            except Exception:
                pass
            return
        if _estado_mas["ancho"] == 0:
            try:
                _pintar_boton_mas(forzar=True)
            except Exception:
                pass
            return
        if _estado_mas.get("pendiente") is not None:
            try:
                E.ventana.after_cancel(_estado_mas["pendiente"])
            except Exception:
                pass
        def _pendiente():
            _estado_mas["pendiente"] = None
            try:
                _pintar_boton_mas()
            except Exception:
                pass
        _estado_mas["pendiente"] = E.ventana.after(80, _pendiente)

    def _hover_mas(_e, encendido):
        _estado_mas["hover"] = encendido
        _redibujar_boton_mas(forzar=True)

    canvas_mas.bind("<Configure>", _redibujar_boton_mas)
    canvas_mas.bind("<Enter>", lambda e: _hover_mas(e, True))
    canvas_mas.bind("<Leave>", lambda e: _hover_mas(e, False))
    canvas_mas.bind("<Button-1>", lambda e: agregar_pad_soundboard())


def agregar_pad_soundboard():
    """Suma un pad vacío más al soundboard (botón '+'), y lo deja
    guardado para que la próxima vez que se abra el programa ya
    aparezca la misma cantidad."""
    E.num_pads_soundboard += 1
    mod_configuracion.guardar_config_interfaz({"num_pads_soundboard": E.num_pads_soundboard})
    construir_soundboard()


EXTENSIONES_AUDIO = (".mp3", ".wav", ".ogg", ".flac", ".m4a")
EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg", ".gif", ".bmp")


def _normalizar_ruta(ruta):
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(ruta)))
    except Exception:
        return ruta


def _imagen_gemela(nombre_base):
    """Busca en la carpeta de imágenes un archivo con el mismo nombre
    base que el sonido (aplausos-1.mp3 -> aplausos-1.jpg). Devuelve la
    ruta o None si no hay ninguna."""
    try:
        for extension in EXTENSIONES_IMAGEN:
            candidata = os.path.join(R.CARPETA_IMAGENES_PAD, nombre_base + extension)
            if os.path.isfile(candidata):
                return candidata
    except Exception:
        pass
    return None


def _pad_ocupado(indice):
    """Un pad cuenta como ocupado si tiene un archivo de sonido asignado
    (los vacíos, los quitados o los que sólo tienen color no cuentan)."""
    datos = E.config_soundboard.get(str(indice))
    return bool(isinstance(datos, dict) and datos.get("archivo"))


def _insertar_pad_al_principio(datos_nuevos):
    """Mete el pad nuevo en la posición 0 corriendo los existentes una
    posición a la derecha, hasta el primer hueco vacío. Si no hay ningún
    hueco (todos ocupados), primero se agrega un pad nuevo al final y
    recién ahí se corre. Nunca se pierde ningún pad existente."""
    hueco = None
    for i in range(E.num_pads_soundboard):
        if not _pad_ocupado(i):
            hueco = i
            break
    if hueco is None:
        hueco = E.num_pads_soundboard
        E.num_pads_soundboard += 1
    for i in range(hueco, 0, -1):
        anterior = E.config_soundboard.pop(str(i - 1), None)
        if anterior is None:
            E.config_soundboard.pop(str(i), None)
        else:
            E.config_soundboard[str(i)] = anterior
    E.config_soundboard["0"] = datos_nuevos


def detectar_sonidos_carpeta(avisar=True):
    """Detecta el contenido de las carpetas: crea un pad por cada audio
    de Sondidos_pad que todavía no tenga pad (con su imagen gemela si
    existe) y, además, les completa la imagen a los pads que ya tienen
    sonido pero todavía no tienen imagen asignada. Los sonidos nuevos
    tienen prioridad: entran primeros (posición 0) y los que ya estaban
    se corren una posición a la derecha; sólo si no hay ningún hueco
    se agregan pads nuevos al final. Nunca borra pads existentes."""
    try:
        archivos = sorted(os.listdir(R.CARPETA_SONIDOS_PAD))
    except Exception:
        archivos = []
    existentes = set()
    for datos in E.config_soundboard.values():
        if isinstance(datos, dict) and datos.get("archivo"):
            existentes.add(_normalizar_ruta(datos["archivo"]))
    pendientes = []
    for archivo in archivos:
        if not archivo.lower().endswith(EXTENSIONES_AUDIO):
            continue
        ruta = os.path.join(R.CARPETA_SONIDOS_PAD, archivo)
        if _normalizar_ruta(ruta) in existentes:
            continue
        nombre_base = os.path.splitext(archivo)[0]
        pendientes.append({
            "nombre": nombre_base,
            "archivo": ruta,
            "imagen": _imagen_gemela(nombre_base),
            "color": None,
        })
        existentes.add(_normalizar_ruta(ruta))
    # Se insertan en orden inverso para que el primero de la lista quede
    # primero en la fila (cada inserción entra en la posición 0).
    for datos_nuevos in reversed(pendientes):
        _insertar_pad_al_principio(datos_nuevos)
    nuevos = len(pendientes)
    # Completar imágenes faltantes en pads que ya existían: se busca la
    # gemela por el nombre del ARCHIVO de sonido (no por el nombre del
    # pad, que el usuario puede haber renombrado).
    imagenes = 0
    for clave, datos in E.config_soundboard.items():
        if not isinstance(datos, dict) or not datos.get("archivo") or datos.get("imagen"):
            continue
        gemela = _imagen_gemela(os.path.splitext(os.path.basename(datos["archivo"]))[0])
        if gemela:
            datos["imagen"] = gemela
            try:
                indice_int = int(clave)
            except (TypeError, ValueError):
                indice_int = None
            for mini in [c for c in E.miniaturas_cargadas if c[0] == indice_int]:
                E.miniaturas_cargadas.pop(mini, None)
            imagenes += 1
    if nuevos or imagenes:
        mod_configuracion.guardar_config_soundboard()
        mod_configuracion.guardar_config_interfaz({"num_pads_soundboard": E.num_pads_soundboard})
        construir_soundboard()
    if avisar:
        partes = []
        if nuevos:
            partes.append(f"{nuevos} pad(s) nuevo(s) al principio")
        if imagenes:
            partes.append(f"{imagenes} imagen(es) asignada(s)")
        if partes:
            messagebox.showinfo("Carpetas detectadas", "Desde las carpetas: " + ", ".join(partes) + ".")
        else:
            messagebox.showinfo(
                "Carpetas detectadas",
                "No hay sonidos ni imágenes nuevas en las carpetas."
            )
    return nuevos
