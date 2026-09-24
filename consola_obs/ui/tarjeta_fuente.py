import math
import threading
import tkinter as tk

from tkinter import messagebox, simpledialog
from tkinter import font as tkfont

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import configuracion as mod_configuracion
from consola_obs import utilidades as mod_utilidades
from consola_obs.obs import cliente as mod_obs_cliente
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.audio import filtros as mod_audio_filtros
from consola_obs.audio import propiedades as mod_audio_propiedades
from consola_obs.ui import dibujo as mod_ui_dibujo
from consola_obs.ui import medidores as mod_ui_medidores
from consola_obs.ui import ventana as mod_ui_ventana


class _FaderOBS:
    """Fader vertical estilo OBS (tema Moderna): pista oscura, relleno
    azul y perilla circular blanca. Misma interfaz mínima que el
    tk.Scale que reemplaza (get/set/pack/bind), para que el resto del
    programa no cambie."""
    ANCHO = 30
    PILDORA_ANCHO = 14
    PILDORA_ALTO = 28
    # Recorrido más largo que la barra de nivel (como en OBS).
    FADER_EXTRA_PX = 40
    # La pista deja arriba y abajo justo la mitad de la pastilla: la
    # pastilla llega hasta los extremos sin cortarse.
    # Pista negra (no gris) y marcas perpendiculares grises.
    COLOR_PISTA = "#0a0a0a"
    COLOR_MARCA_FADER = "#565c6c"
    COLOR_LLENO_FADER = "#4365cb"
    MARCAS_FADER_DB = (0, -10, -20, -30, -40, -50)

    def __init__(self, parent, alto, bg, al_cambiar):
        self.alto = max(60, int(alto) + self.FADER_EXTRA_PX + self.PILDORA_ALTO)
        self.al_cambiar = al_cambiar
        self._db = -60.0
        # La pastilla viaja contenida entre los extremos de la pista:
        # toca los bordes sin sobrepasarlos.
        self._margen = self.PILDORA_ALTO
        self.canvas = tk.Canvas(parent, width=self.ANCHO, height=self.alto,
                                bg=bg, highlightthickness=0, cursor="hand2")
        cx = self.ANCHO / 2
        self._cx = cx
        m = self._margen
        # La pista va de mitad de pastilla a mitad de pastilla (el viaje
        # es más corto: la pastilla queda contenida).
        pb = self.PILDORA_ALTO // 2
        foto_pista = mod_ui_dibujo._imagen_pista_fader(
            self.alto - pb * 2, self.COLOR_PISTA, self.COLOR_LLENO_FADER)
        if foto_pista is not None:
            self.canvas.imagen_pista = foto_pista
            self.canvas.create_image(cx - 4, pb, anchor="nw", image=foto_pista)
            self.id_fill_cap = None
        else:
            # Sin Pillow: pista y puntas con primitivas de canvas.
            self.canvas.create_rectangle(cx - 2, pb, cx + 2, self.alto - pb,
                                         fill=self.COLOR_PISTA, outline="")
            self.canvas.create_oval(cx - 2, pb - 2, cx + 2, pb + 2,
                                    fill=self.COLOR_PISTA, outline="")
            self.canvas.create_oval(cx - 2, self.alto - pb - 2, cx + 2, self.alto - pb + 2,
                                    fill=self.COLOR_PISTA, outline="")
            self.canvas.create_oval(cx - 2, self.alto - pb - 2, cx + 2, self.alto - pb + 2,
                                    fill=self.COLOR_LLENO_FADER, outline="")
            self.id_fill_cap = self.canvas.create_oval(
                cx - 2, self.alto - pb - 2, cx + 2, self.alto - pb + 2,
                fill=self.COLOR_LLENO_FADER, outline="")
        self.id_fill = self.canvas.create_rectangle(
            cx - 2, self.alto - pb, cx + 2, self.alto - pb,
            fill=self.COLOR_LLENO_FADER, outline="")
        # Marcas sobre el largo total de la pista (el 0 arriba del todo),
        # independientes del recorrido de la pastilla.
        _span_pista = self.alto - self.PILDORA_ALTO
        for _db_marca in self.MARCAS_FADER_DB:
            _y = self.PILDORA_ALTO // 2 + (-_db_marca / 60.0) * _span_pista
            for _lado in (-1, 1):
                self.canvas.create_line(
                    cx + _lado * 3, _y, cx + _lado * 7, _y,
                    fill=self.COLOR_MARCA_FADER, width=2)
        foto = mod_ui_dibujo._imagen_pildora_blanca(self.PILDORA_ANCHO, self.PILDORA_ALTO)
        if foto is not None:
            self.canvas.imagen_perilla = foto
            self.id_handle = self.canvas.create_image(cx, self.alto - m, image=foto)
            self._handle_es_foto = True
        else:
            # Sin Pillow: un óvalo en caja alargada ya es una pastilla
            # (con los bordes de siempre, pero la forma correcta).
            self.id_handle = self.canvas.create_oval(
                cx - self.PILDORA_ANCHO / 2, self.alto - m - self.PILDORA_ALTO / 2,
                cx + self.PILDORA_ANCHO / 2, self.alto - m + self.PILDORA_ALTO / 2,
                fill="#f2f5fa", outline="#9aa4b2")
            self._handle_es_foto = False
        self.canvas.bind("<ButtonPress-1>", self._al_arrastrar)
        self.canvas.bind("<B1-Motion>", self._al_arrastrar)

    def _recorrido(self):
        return max(1, self.alto - 2 * self._margen)

    def _y_de_db(self, db):
        db = max(-60.0, min(0.0, db))
        return self._margen + (-db / 60.0) * self._recorrido()

    def _db_de_y(self, y):
        t = (max(self._margen, min(self.alto - self._margen, y)) - self._margen) / self._recorrido()
        return round(max(-60.0, min(0.0, -t * 60.0)) * 2) / 2

    def set(self, db):
        try:
            self._db = max(-60.0, min(0.0, float(db)))
        except Exception:
            self._db = -60.0
        self._repintar()

    def get(self):
        return self._db

    def pack(self, *args, **kwargs):
        return self.canvas.pack(*args, **kwargs)

    def bind(self, *args, **kwargs):
        return self.canvas.bind(*args, **kwargs)

    def _repintar(self):
        y = self._y_de_db(self._db)
        pw, ph = self.PILDORA_ANCHO, self.PILDORA_ALTO
        m = self._margen
        # El relleno arranca en el borde superior de la pastilla: a 0 dB
        # llega hasta arriba del todo sin que la pastilla se pase.
        arriba = max(m - ph // 2, y - ph // 2)
        self.canvas.coords(self.id_fill, self._cx - 2, arriba, self._cx + 2, self.alto - self.PILDORA_ALTO // 2)
        if self.id_fill_cap is not None:
            self.canvas.coords(self.id_fill_cap, self._cx - 2, arriba - 2, self._cx + 2, arriba + 2)
        if self._handle_es_foto:
            self.canvas.coords(self.id_handle, self._cx, y)
        else:
            self.canvas.coords(self.id_handle, self._cx - pw / 2, y - ph / 2, self._cx + pw / 2, y + ph / 2)

    def _al_arrastrar(self, event):
        self.set(self._db_de_y(event.y))
        try:
            self.al_cambiar(self._db)
        except Exception:
            pass


def _ancho_preferido_fuente():
    """Ancho 'de catálogo' (mínimo) de una tarjeta de fuente, según el
    tamaño de ícono elegido (Chico/Mediano/Grande) y el factor de escala
    de ventana actual, SIN estirar todavía para llenar la fila."""
    return mod_utilidades.medida_actual()["fuente_ancho"]


def _ancho_contenedor_fuente():
    """Ancho real (con su padding) que ocupa una tarjeta de fuente en la
    grilla: tarjeta + sombra (18) + padx de grilla (6+6). Es el paso de
    columna que usa _reubicar_fuentes, así el cálculo de columnas
    coincide con lo que se ve y la tarjeta que no entra baja de fila
    en vez de quedar tapada."""
    return _ancho_preferido_fuente() + 30                  


def _columnas_disponibles_fuentes():
    """Cuántas tarjetas de fuente entran por fila: piso estricto, sin
    tolerancia más que 2px. Apenas una tarjeta quedaría tapada (aunque
    sea un píxel más allá de esos 2px), baja a la fila de abajo. Así
    ninguna fuente queda nunca a medio ver ni se oculta: siempre se
    ve entera, en su fila."""
    ancho_disponible = E.canvas.winfo_width()
    celda = _ancho_contenedor_fuente()
    if ancho_disponible <= 1 or celda <= 0:
        return E.columnas_fuentes
    return max(1, int((ancho_disponible + 2) // celda))


def _ancho_celda_fuentes():
    """Ancho de cada tarjeta de fuente: SIEMPRE el tamaño 'de catálogo'
    para el tamaño de ícono elegido (Chico/Mediano/Grande) y el factor
    de escala de ventana actual (ver _ancho_preferido_fuente). Las
    tarjetas ya NO se estiran ni se achican para llenar el ancho
    disponible del panel -antes sí lo hacían, lo que hacía que cada
    fuente pareciera "redimensionarse sola" al mover el borde de la
    ventana-. Lo único que cambia con el ancho disponible es CUÁNTAS
    tarjetas entran por fila (ver _columnas_disponibles_fuentes): si
    deja de entrar una columna entera, esa tarjeta pasa a la fila de
    abajo tal cual estaba, sin cambiar de tamaño."""
    return _ancho_preferido_fuente()


def _fila_col_fuente(nombre):
    """Posición (fila, columna) de una fuente dentro de la grilla, según
    el orden en que fue apareciendo y la cantidad de columnas que entran
    en el ancho actual. Las fuentes se acomodan en varias filas, en vez
    de una sola fila larga con scroll horizontal, para que entren todas
    en pantalla."""
    if nombre not in E.orden_fuentes:
        E.orden_fuentes.append(nombre)
    idx = E.orden_fuentes.index(nombre)
    columnas = max(1, E.columnas_fuentes)
    return idx // columnas, idx % columnas


def _reajustar_fuente_nombre_tarjeta(nombre, ancho_disponible):
    """Recalcula el tamaño de letra del nombre de 'nombre' para el nuevo
    ancho disponible (se llama cuando la tarjeta cambia de tamaño), con
    la misma lógica de achicar-antes-que-cortar que usa crear_fader_fuente.
    La cabecera mantiene su alto fijo (ver _titulo_en_caja_fija): los
    títulos largos se achican y, si hace falta, se recortan con '…',
    para que ninguna tarjeta se desaliñe del resto."""
    widgets = E.fuentes.get(nombre)
    if not widgets:
        return
    nombre_visible = widgets.get("nombre_visible", nombre)
    tam_max = widgets.get("fuente_tam_max", mod_utilidades.medida_actual()["fuente_nombre"])
    tam_min = widgets.get("fuente_tam_min", max(7, tam_max - 5))
    alto_cabecera_base = widgets.get("alto_cabecera_base", 26)
    ancho_texto = max(70, ancho_disponible)

    tam, ancho_wrap_texto, lineas_nombre = _ajustar_texto_tarjeta(
        nombre_visible, E.FUENTE_TITULO, tam_max, ancho_texto, tam_min
    )
    if lineas_nombre >= 3:
        tam, ancho_wrap_texto, texto_mostrado = _titulo_en_caja_fija(
            nombre_visible, tam, ancho_texto)
    else:
        texto_mostrado = nombre_visible

    cabecera_canal = widgets["cabecera"]
    fuente_nueva = (E.FUENTE_TITULO, tam, "bold")
    cabecera_canal.itemconfig(widgets["id_texto_nombre"], font=fuente_nueva, width=ancho_wrap_texto, text=texto_mostrado)
    cabecera_canal.itemconfig(widgets["id_texto_sombra"], font=fuente_nueva, width=ancho_wrap_texto, text=texto_mostrado)

    alto_cabecera = alto_cabecera_base
    if int(cabecera_canal.cget("height")) != int(alto_cabecera):
        cabecera_canal.config(height=alto_cabecera)
        redibujar = widgets.get("redibujar_cabecera")
        if redibujar:
            redibujar()


def _reubicar_fuentes(forzar=False):
    """Reacomoda (sin recrear) las tarjetas de fuente ya existentes según
    la cantidad de columnas actual. No recrear evita perder el estado
    del fader mientras el usuario lo está arrastrando.

    El ancho de cada tarjeta (ver _ancho_celda_fuentes) es siempre el
    tamaño 'de catálogo': ya no se estira ni se achica según el espacio
    disponible. Lo que SÍ puede cambiar con el ancho del panel es la
    cantidad de columnas (ver _columnas_disponibles_fuentes); cuando
    eso pasa, esta función reposiciona las tarjetas en su nueva fila/
    columna, pero ninguna tarjeta cambia de tamaño por eso."""
    columnas = max(1, E.columnas_fuentes)
    ancho_celda = _ancho_celda_fuentes()
    ancho_sin_cambios = (not forzar) and (E._ultimo_ancho_celda_fuentes["valor"] == ancho_celda)
    E._ultimo_ancho_celda_fuentes["valor"] = ancho_celda
    # La clave incluye el orden: reordenar (drag & drop) no cambia ni
    # columnas ni ancho, y sin esto el early return de abajo se tragaba
    # el reorden y la grilla nunca se movía (la lista se guardaba bien,
    # pero las tarjetas quedaban en su lugar).
    clave_grilla = (columnas, ancho_celda, tuple(E.orden_fuentes))
    # Si no cambió ni la cantidad de columnas ni el ancho, las posiciones
    # son idénticas: no hay nada que mover.
    if (not forzar) and E._ultima_grilla_fuentes.get("clave") == clave_grilla:
        mod_ui_ventana.actualizar_scroll()
        return
    E._ultima_grilla_fuentes["clave"] = clave_grilla
    for idx, nombre in enumerate(E.orden_fuentes):
        if nombre not in E.fuentes:
            continue
        try:
            if not E.fuentes[nombre]["tarjeta_sombra"].winfo_exists():
                continue
        except Exception:
            continue
        fila = idx // columnas
        col = idx % columnas
        tarjeta_sombra = E.fuentes[nombre]["tarjeta_sombra"]
        contenedor = E.fuentes[nombre]["contenedor"]
        if not ancho_sin_cambios:
            tarjeta_sombra.config(width=ancho_celda + 18)
            tarjeta_sombra.delete("sombra_difusa")
            mod_ui_dibujo._dibujar_sombra_difusa(
                tarjeta_sombra, 6, 6, ancho_celda + 4, contenedor.winfo_reqheight() + 4,
                radio=10, capas=3, color_fondo_panel="#131825"
            )
            contenedor.config(width=ancho_celda)
            _reajustar_fuente_nombre_tarjeta(nombre, ancho_celda - 24)
        # Reposicionar en la grilla es barato (no crea nada nuevo), así
        # que se hace siempre, haya cambiado el ancho o no: es lo que
        # de verdad mueve una tarjeta a otra fila/columna. Las tarjetas
        # siempre se ven enteras: la que no entra baja de fila (ver
        # _columnas_disponibles_fuentes), nunca se oculta.
        tarjeta_sombra.grid(row=fila, column=col, padx=6, pady=6, sticky="n")
    mod_ui_ventana.actualizar_scroll()


def _al_redimensionar_fuentes(event=None):
    """Si cambió el TAMAÑO (resize real): se OCULTA la grilla y el
    reacomodo se difiere entero al asentado. Oculto no hay nada que se
    pueda pintar roto (inmune a cadencia de eventos, fotos y escalas).
    Sin cambio de tamaño (scrollbars, contenido): reacomodo barato
    inmediato como antes, sin ocultar."""
    mod_ui_ventana.entrar_modo_super()
    try:
        tam = None
        if event is not None and getattr(event, "width", 0) > 1:
            tam = (event.width, event.height)
    except Exception:
        tam = None
    try:
        cambio = tam is not None and E._ultimo_tamano_canvas_fuentes.get("valor") != tam
    except Exception:
        cambio = False
    if cambio:
        try:
            E._ultimo_tamano_canvas_fuentes["valor"] = tam
        except Exception:
            pass
        mod_ui_ventana._tapar_fuentes_con_foto()
        mod_ui_ventana._programar_asentado_fuentes()
        return
    if E._trabajo_redimension_fuentes["id"] is not None:
        E.ventana.after_cancel(E._trabajo_redimension_fuentes["id"])
    E._trabajo_redimension_fuentes["id"] = E.ventana.after(15, _aplicar_redimension_fuentes)


def _aplicar_redimension_fuentes():
    E._trabajo_redimension_fuentes["id"] = None
    nuevas_columnas = _columnas_disponibles_fuentes()
    if nuevas_columnas != E.columnas_fuentes:
        E.columnas_fuentes = nuevas_columnas
    # Se reacomoda siempre, no sólo cuando cambia la cantidad de
    # columnas: aunque siga entrando la misma cantidad por fila, el
    # ancho de cada tarjeta se recalcula según el espacio disponible
    # ahora mismo (ver _reubicar_fuentes), así ninguna tarjeta queda
    # sobresaliendo del borde visible del panel cuando éste se achica o
    # agranda un poco. _reubicar_fuentes ya evita el trabajo de más si
    # el ancho no cambió de verdad.
    _reubicar_fuentes()


def _envolver_texto_por_ancho(texto, fuente, ancho_max):
    """Parte 'texto' en líneas que entran en 'ancho_max' píxeles con
    'fuente', cortando por palabra completa (nunca a mitad de palabra)."""
    palabras = texto.split()
    if not palabras:
        return [texto]
    lineas = []
    actual = palabras[0]
    for palabra in palabras[1:]:
        candidato = f"{actual} {palabra}"
        if fuente.measure(candidato) <= ancho_max:
            actual = candidato
        else:
            lineas.append(actual)
            actual = palabra
    lineas.append(actual)
    return lineas


def _ajustar_texto_tarjeta(texto, familia, tam_max, ancho_max, tam_min=8, max_lineas=2, peso="bold"):
    """Decide con qué tamaño de letra y si hace falta envolver el nombre
    de una fuente para que entre en el ancho disponible. Devuelve
    (tamaño, ancho_de_envoltura, cantidad_de_renglones).

    Para cada tamaño (de grande a chico) primero se prueba una sola
    línea y, si no entra, se prueba envolviendo por palabra: apenas
    alguna de las dos formas entra, se usa ESE tamaño, así un nombre de
    dos palabras puede quedar tan grande como uno de una sola palabra
    que sí entra entero. Sólo se achica la letra cuando ni envolviendo
    entra en 'max_lineas' renglones; si ni al tamaño mínimo alcanza
    (nombres larguísimos), se devuelve igual la cantidad real de
    renglones que hacen falta, para que quien llama pueda agrandar el
    alto disponible en vez de recortar el texto."""
    tam_max = max(tam_min, int(tam_max))
    for tam in range(tam_max, tam_min - 1, -1):
        fuente = tkfont.Font(family=familia, size=tam, weight=peso)
        if fuente.measure(texto) <= ancho_max:
            return tam, 0, 1
        lineas = _envolver_texto_por_ancho(texto, fuente, ancho_max)
        if len(lineas) <= max_lineas and all(fuente.measure(l) <= ancho_max for l in lineas):
            return tam, ancho_max, len(lineas)
    fuente_min = tkfont.Font(family=familia, size=tam_min, weight=peso)
    lineas_min = _envolver_texto_por_ancho(texto, fuente_min, ancho_max)
    return tam_min, ancho_max, max(1, len(lineas_min))


def _ajustar_titulo_largo(nombre_visible, tam_actual, ancho_texto):
    """Segunda pasada para títulos que necesitan 3 renglones o más:
    se reintenta con más aire a los costados (para que no toque los
    bordes) permitiendo hasta 4 renglones y letra más chica (mínimo 6).
    Devuelve (tamaño, ancho_de_envoltura, cantidad_de_renglones).

    El texto ya queda centrado verticalmente solo: la cabecera crece
    según el alto real y el texto está anclado al centro del canvas
    (ver _redibujar_gradiente_cabecera_fuente)."""
    ancho_respirado = max(50, ancho_texto - 16)
    tam, wrap, lineas = _ajustar_texto_tarjeta(
        nombre_visible, E.FUENTE_TITULO, max(6, int(tam_actual)),
        ancho_respirado, 6, 3, "bold")
    if lineas <= 3:
        return tam, wrap, lineas
    return _ajustar_texto_tarjeta(
        nombre_visible, E.FUENTE_TITULO, max(6, int(tam_actual)),
        ancho_respirado, 6, 4, "bold")


def _recortar_a_dos_lineas(texto, fuente, ancho_max):
    """Recorta 'texto' a 2 renglones como máximo (con '…' al final si
    se cortó algo), midiendo con 'fuente' para no superar 'ancho_max'.
    Es el último recurso para que un título largo entre en la cabecera
    de alto fijo sin agrandarla y desalinear el resto de la tarjeta."""
    palabras = texto.split()
    if not palabras:
        return texto
    # Renglón 1: todas las palabras que entren.
    linea1 = palabras[0]
    i = 1
    while i < len(palabras) and fuente.measure(linea1 + " " + palabras[i]) <= ancho_max:
        linea1 += " " + palabras[i]
        i += 1
    if fuente.measure(linea1) > ancho_max:
        # Una sola palabra más ancha que la caja: se corta por letra.
        while linea1 and fuente.measure(linea1 + "…") > ancho_max:
            linea1 = linea1[:-1]
        return (linea1 + "…") if linea1 else "…"
    if i >= len(palabras):
        return linea1
    # Renglón 2: lo que entre + "…".
    linea2 = palabras[i]
    i += 1
    while i < len(palabras) and fuente.measure(linea2 + " " + palabras[i] + "…") <= ancho_max:
        linea2 += " " + palabras[i]
        i += 1
    while linea2 and fuente.measure(linea2 + "…") > ancho_max:
        linea2 = linea2.rsplit(" ", 1)[0] if " " in linea2 else linea2[:-1]
    return linea1 + "\n" + (linea2 + "…" if linea2 else "…")


def _titulo_en_caja_fija(nombre_visible, tam_actual, ancho_texto):
    """Título que entra SIEMPRE en la cabecera de alto fijo (2 renglones
    como máximo): primero achica la letra (ver _ajustar_titulo_largo);
    si ni así entra, reintenta con todo el ancho útil (sin el aire
    extra de adentro) bajando hasta 5; sólo si tampoco entra recorta
    con '…' (ver _recortar_a_dos_lineas).
    Devuelve (tamaño, ancho_de_envoltura, texto_mostrado)."""
    tam, wrap, lineas = _ajustar_titulo_largo(nombre_visible, tam_actual, ancho_texto)
    if lineas <= 2:
        return tam, wrap, nombre_visible
    ancho_util = max(50, ancho_texto - 4)
    tam2, wrap2, lineas2 = _ajustar_texto_tarjeta(
        nombre_visible, E.FUENTE_TITULO, min(tam, 7), ancho_util, 5, 2, "bold")
    fuente2 = tkfont.Font(family=E.FUENTE_TITULO, size=tam2, weight="bold")
    envueltas = _envolver_texto_por_ancho(nombre_visible, fuente2, ancho_util)
    if lineas2 <= 2 and len(envueltas) <= 2 and all(
            fuente2.measure(l) <= ancho_util for l in envueltas):
        return tam2, wrap2 or ancho_util, nombre_visible
    return tam2, wrap2 or ancho_util, _recortar_a_dos_lineas(nombre_visible, fuente2, ancho_util)


def crear_fader_fuente(nombre, vol_db, muted, tipo_monitor, nombre_visible=None):

    if nombre_visible is None:
        nombre_visible = nombre

    medida_icono = mod_utilidades.medida_actual()
    alto_canal = medida_icono["fuente_alto_canal"]
    ancho_barra_vu = medida_icono["fuente_ancho_vu"]
    if E.es_moderna():
        # Medidor de dos canales con divisora (ver medidores.py).
        ancho_barra_vu = mod_ui_medidores.ANCHO_BARRA_MODERNA_TOTAL
    ancho_contenedor = _ancho_celda_fuentes()
    alto_contenedor = medida_icono["fuente_alto"]

    color_etiqueta = E.colores_fuentes.get(nombre)
    if E.es_moderna():
        if color_etiqueta:
            _base_suave = mod_ui_dibujo._desaturar_color(color_etiqueta)
            color_cabecera_base = _base_suave
            color_cuerpo = mod_ui_dibujo._oscurecer_color_pct(_base_suave, 0.50)
            color_meta = mod_ui_dibujo._oscurecer_color_pct(_base_suave, 0.35)
        else:
            color_cabecera_base = C.MOD_CABECERA
            color_cuerpo = C.MOD_TARJETA
            color_meta = C.MOD_FONDO
    else:
        color_cabecera_base = color_etiqueta or "#3d4d66"
        color_cuerpo = mod_ui_dibujo._oscurecer_color_pct(color_etiqueta, 0.42) if color_etiqueta else "#202633"
        color_meta = mod_ui_dibujo._oscurecer_color_pct(color_etiqueta, 0.30) if color_etiqueta else "#141a26"

    es_principal_inicial = nombre in E.fuentes_principales
    color_borde_principal = C.MOD_ACENTO if E.es_moderna() else C.COLOR_BORDE_PRINCIPAL
    color_borde = color_borde_principal if es_principal_inicial else "#0e1219"
    grosor_borde = 3 if es_principal_inicial else 2

    tarjeta_sombra = tk.Canvas(
        E.panel_fuentes, bg=E.color_fondo_panel(),
        width=ancho_contenedor + 18, height=alto_contenedor + 18,
        highlightthickness=0
    )
    # OJO: no se grilla acá a propósito. La tarjeta se muestra al final
    # de esta función, ya con todo su contenido construido y pintado,
    # para que el primer cuadro que se ve sea la versión cargada y
    # nunca la tarjeta vacía.
    tarjeta_sombra.grid_propagate(False)

    mod_ui_dibujo._dibujar_sombra_difusa(
        tarjeta_sombra, 6, 6, ancho_contenedor + 4, alto_contenedor + 4,
        radio=10, capas=3, color_fondo_panel="#131825"
    )

    contenedor = tk.Frame(
        tarjeta_sombra,
        bg=color_cuerpo,
        width=ancho_contenedor,
        height=alto_contenedor,
        highlightbackground=color_borde,
        highlightthickness=grosor_borde
    )
    contenedor.pack_propagate(False)
    tarjeta_sombra.create_window(6, 6, anchor="nw", window=contenedor)

    ancho_texto = max(70, ancho_contenedor - 24)
    fuente_nombre_tam_max = medida_icono["fuente_nombre"]
    fuente_nombre_tam_min = max(7, fuente_nombre_tam_max - 5)

    # El nombre se achica automáticamente sólo cuando hace falta: primero
    # se intenta en una sola línea, después envolviendo por palabra (sin
    # cortar a mitad de palabra), y recién si ni así entra se lo achica
    # (ver _ajustar_texto_tarjeta).
    fuente_nombre_tam, ancho_wrap_texto, lineas_nombre = _ajustar_texto_tarjeta(
        nombre_visible, E.FUENTE_TITULO, fuente_nombre_tam_max, ancho_texto, fuente_nombre_tam_min
    )

    # La cabecera mide SIEMPRE lo mismo (lugar para 2 renglones al
    # tamaño máximo): el título se adapta a la caja —achicándose y, si
    # ni así entra en 2 renglones, recortándose con '…' (ver
    # _titulo_en_caja_fija)—, nunca al revés. Así todas las tarjetas
    # quedan alineadas sin importar cuán largo sea cada nombre.
    _fuente_medicion = tkfont.Font(family=E.FUENTE_TITULO, size=fuente_nombre_tam_max, weight="bold")
    alto_cabecera_base = max(26, _fuente_medicion.metrics("linespace") * 2 + 16)
    if lineas_nombre >= 3:
        fuente_nombre_tam, ancho_wrap_texto, texto_mostrado = _titulo_en_caja_fija(
            nombre_visible, fuente_nombre_tam, ancho_texto)
    else:
        texto_mostrado = nombre_visible
    alto_cabecera = alto_cabecera_base
    cabecera_canal = tk.Canvas(contenedor, height=alto_cabecera, highlightthickness=0, bg=color_cabecera_base, cursor="fleur")
    cabecera_canal.pack(fill="x")
    cabecera_canal.pack_propagate(False)
    cabecera_canal.datos_color_actual = color_cabecera_base

    id_texto_sombra = cabecera_canal.create_text(
        0, 0, text=texto_mostrado, fill=mod_ui_dibujo._oscurecer_color(color_cabecera_base, 70),
        font=(E.FUENTE_TITULO, fuente_nombre_tam, "bold"),
        width=ancho_wrap_texto, justify="center", tags=("texto_sombra",)
    )
    id_texto_nombre = cabecera_canal.create_text(
        0, 0, text=texto_mostrado, fill="white",
        font=(E.FUENTE_TITULO, fuente_nombre_tam, "bold"),
        width=ancho_wrap_texto, justify="center", tags=("texto_nombre",)
    )

    def _redibujar_gradiente_cabecera_fuente(event=None, cv=cabecera_canal, id_sombra=id_texto_sombra, id_nombre=id_texto_nombre):
        ancho_cab = cv.winfo_width()
        alto_cab = cv.winfo_height()
        if ancho_cab < 2 or alto_cab < 2:
            return
        color_base = cv.datos_color_actual
        cx, cy = ancho_cab / 2, alto_cab / 2
        cv.coords(id_sombra, cx + 1, cy + 2)
        cv.coords(id_nombre, cx, cy + 1)
        if E.es_moderna():
            # Cabecera lisa en Moderna (sin degradado): sólo se centra el texto.
            return
        if E._modo_super.get("activo"):
            # En modo super el texto se recentra pero las bandas no se
            # tocan: se repintan todas juntas al salir del modo.
            return
        # Las bandas del degradado sólo se redibujan si el tamaño cambió
        # de verdad (tolerancia 6px): durante un redimensionado llegan
        # decenas de <Configure> por segundo y recrear las 14 bandas en
        # cada uno es lo que producía los cortes.
        ultimo = getattr(cv, "datos_ultimo_gradiente", None)
        if (ultimo is not None and ultimo[0] == color_base
                and abs(ancho_cab - ultimo[1]) < 6 and abs(alto_cab - ultimo[2]) < 6):
            return
        cv.datos_ultimo_gradiente = (color_base, ancho_cab, alto_cab)
        cv.delete("degradado_cabecera")
        color_claro = mod_ui_dibujo._aclarar_color(color_base, 40)
        color_oscuro = mod_ui_dibujo._oscurecer_color(color_base, 15)
        ids = mod_ui_dibujo._gradiente_vertical(cv, 0, 0, ancho_cab, alto_cab, color_claro, color_oscuro, pasos=min(14, max(2, alto_cab)))
        for iid in ids:
            cv.itemconfig(iid, tags=("degradado_cabecera",))
        cv.tag_lower("degradado_cabecera")

    cabecera_canal.bind("<Configure>", _redibujar_gradiente_cabecera_fuente)
    # Doble clic sobre el título = renombrar. Clic derecho en cualquier
    # parte de la tarjeta = menú con el resto de las acciones (color de
    # etiqueta, filtros, marcar como principal, renombrar), que antes
    # eran botones sueltos siempre a la vista. Clic izquierdo sostenido
    # y arrastrado sobre la cabecera = mover la tarjeta de lugar.
    cabecera_canal.bind("<Double-Button-1>", lambda e: _iniciar_renombrar_fuente(nombre))
    cabecera_canal.bind("<ButtonPress-1>", lambda e: _iniciar_arrastre_fuente(nombre, e))
    cabecera_canal.bind("<B1-Motion>", lambda e: _mover_arrastre_fuente(nombre, e))
    cabecera_canal.bind("<ButtonRelease-1>", lambda e: _soltar_arrastre_fuente(nombre, e))
    cabecera_canal.bind("<Button-3>", lambda e: _abrir_menu_contextual_fuente(nombre, e))

    # División entre el título y el resto: en Moderna es una línea fina
    # de acento siempre visible; en Profesional, la tira meta de siempre.
    fila_meta = tk.Frame(
        contenedor,
        bg=(E.color_acento() if E.es_moderna() else color_meta),
        height=(2 if E.es_moderna() else 8))
    fila_meta.pack(fill="x")
    fila_meta.pack_propagate(False)
    fila_meta.bind("<Button-3>", lambda e: _abrir_menu_contextual_fuente(nombre, e))

    # El chasis entero también reconoce el clic derecho, para no
    # obligar a apuntarle justo a la cabecera o la tira fina.
    contenedor.nombre_fuente = nombre
    contenedor.bind("<Button-3>", lambda e: _abrir_menu_contextual_fuente(nombre, e))

    col_db_activo = C.MOD_TEXTO if E.es_moderna() else "#2fd693"
    col_db_silencio = C.MOD_APAGADO if E.es_moderna() else "#828da6"
    etiqueta_db = tk.Label(
        contenedor,
        text="SILENCIO" if vol_db <= E.UMBRAL_SILENCIO else f"{vol_db:.1f} dB",
        bg=color_cuerpo,
        fg=col_db_silencio if vol_db <= E.UMBRAL_SILENCIO else col_db_activo,
        font=(E.FUENTE_UI, 10)
    )
    etiqueta_db.pack(pady=(3, 1))


    fila_vertical = tk.Frame(contenedor, bg=color_cuerpo)
    fila_vertical.pack(pady=1)

    # Margen vertical para que las etiquetas "0" y "-60" (arriba y abajo
    # del todo) tengan lugar completo para dibujarse: antes el canvas
    # medía exactamente 'alto_canal' y el texto se centraba justo en el
    # borde (y=0 e y=alto_canal), así que la mitad de esos números
    # quedaba recortada por el borde del canvas. Se calcula con las
    # métricas reales de la fuente (no un número fijo) para que
    # funcione bien sea cual sea el tamaño de letra o la plataforma.
    _fuente_marcas_db = tkfont.Font(family=E.FUENTE_UI, size=6)
    margen_marcas_db = math.ceil(_fuente_marcas_db.metrics("linespace") / 2) + 1

    # En Moderna el medidor mide lo mismo que la barra de volumen (que
    # es más larga que el alto del canal); en Profesional coinciden.
    alto_medidor = alto_canal + (_FaderOBS.FADER_EXTRA_PX if E.es_moderna() else 0)

    tam_marcas_db = 6
    if E.es_moderna():
        # Números dB más grandes: se mide el ancho real que necesitan y
        # se agranda el canvas para que no se corten; si no entran en
        # la tarjeta se vuelve al tamaño chico.
        tam_marcas_db = 7
        _f_marcas = tkfont.Font(family=E.FUENTE_UI, size=tam_marcas_db)
        ancho_marcas = max(_f_marcas.measure(str(m)) for m in mod_ui_medidores.MARCAS_DB_OBS) + 5
        if ancho_barra_vu + ancho_marcas + 4 + _FaderOBS.ANCHO > ancho_contenedor - 6:
            tam_marcas_db = 6
            _f_marcas = tkfont.Font(family=E.FUENTE_UI, size=tam_marcas_db)
            ancho_marcas = max(_f_marcas.measure(str(m)) for m in mod_ui_medidores.MARCAS_DB_OBS) + 5
        margen_marcas_db = math.ceil(_f_marcas.metrics("linespace") / 2) + 1
        # Desplazamiento superior del medidor: lugar para la etiqueta
        # "0" más 7px para que la barra arranque a la misma altura que
        # la pista del fader (ver el pack con pady calculado abajo).
        off_nivel = margen_marcas_db + 7
        vu_canvas = tk.Canvas(
            fila_vertical, width=ancho_barra_vu + ancho_marcas,
            height=alto_medidor + off_nivel + margen_marcas_db,
            bg=color_cuerpo, highlightthickness=0
        )
        vu_canvas.pack(side="left", anchor="n")
        vu_obs = mod_ui_medidores._dibujar_barra_obs(
            vu_canvas, ancho_barra_vu, alto_medidor, bg=color_cuerpo, offset_y=off_nivel)
        vu_segmentos = []
        marcas_db = mod_ui_medidores.MARCAS_DB_OBS
        color_marcas = C.MOD_MARCA_DB
    else:
        vu_canvas = tk.Canvas(
            fila_vertical, width=ancho_barra_vu + 16, height=alto_canal + margen_marcas_db * 2,
            bg="#0e1219", highlightthickness=0
        )
        vu_canvas.pack(side="left", anchor="n")
        vu_obs = None
        vu_segmentos = mod_ui_medidores._dibujar_segmentos_led(vu_canvas, ancho_barra_vu, alto_canal, offset_y=margen_marcas_db)
        marcas_db = E.MARCAS_DB
        color_marcas = "#79859f"
        off_nivel = margen_marcas_db

    for marca in marcas_db:
        y = mod_ui_medidores._y_para_db(marca, alto_medidor) + off_nivel
        if E.es_moderna():
            # Marcas perpendiculares pegadas a la barra, con el dB al lado.
            vu_canvas.create_line(
                ancho_barra_vu, y, ancho_barra_vu + 4, y,
                fill=C.MOD_MARCA_DB, width=1)
        vu_canvas.create_text(
            ancho_barra_vu + (6 if E.es_moderna() else 3), y, text=str(marca),
            fill=color_marcas, font=(E.FUENTE_UI, tam_marcas_db if E.es_moderna() else 6),
            anchor="w"
        )

    def cambiar_volumen(valor):
        if not E.conectado:
            return
        try:
            db = float(valor)
            if db <= E.UMBRAL_SILENCIO:
                E.cliente_obs.set_input_volume(nombre, vol_mul=0)
                etiqueta_db.config(text="SILENCIO", fg=col_db_silencio)
            else:
                E.cliente_obs.set_input_volume(nombre, vol_db=db)
                etiqueta_db.config(text=f"{db:.1f} dB", fg=col_db_activo)
            if nombre == C.NOMBRE_FUENTE_EFECTOS:
                # El fader movido a mano es el nivel base al que vuelve
                # cada fundido (import lazy: audio importa UI).
                try:
                    from consola_obs.audio import reproduccion as mod_audio_reproduccion
                    mod_audio_reproduccion.nota_volumen_usuario(db)
                except Exception:
                    pass
        except Exception as e:
            print(f"Error cambiando volumen de {nombre}: {e}")

    if E.es_moderna():
        escala = _FaderOBS(fila_vertical, alto_canal, color_cuerpo, cambiar_volumen)
    else:
        escala = tk.Scale(
            fila_vertical,
            from_=0,
            to=-60,
            resolution=0.5,
            orient="vertical",
            length=alto_canal,
            width=14,
            sliderlength=20,
            showvalue=False,
            bg="#2a3243",
            fg="white",
            troughcolor="#141a26",
            highlightthickness=0,
            activebackground="#4fe3ae"
        )
        escala.config(command=cambiar_volumen)
    escala.set(vol_db)
    # En Moderna el canvas arranca a la altura que deja la pista del
    # fader alineada con la barra de nivel (ver off_nivel).
    if E.es_moderna():
        escala.pack(side="left", padx=(4, 0), pady=(max(0, off_nivel - 14), 0), anchor="n")
    else:
        escala.pack(side="left", padx=(4, 0), pady=(margen_marcas_db, 0), anchor="n")

    escala.bind("<ButtonPress-1>", lambda e: E.fuentes[nombre].__setitem__("arrastrando", True))
    escala.bind("<ButtonRelease-1>", lambda e: E.fuentes[nombre].__setitem__("arrastrando", False))


    fila_iconos = tk.Frame(contenedor, bg=color_cuerpo)
    fila_iconos.pack(pady=(3, 4))

    if E.es_moderna():
        boton_mute = mod_ui_dibujo._crear_icono_plano(
            fila_iconos,
            "🔇" if muted else "🔊",
            medida_icono["fuente_boton"] + 1,
            mod_ui_dibujo._color_mute(muted),
            lambda: cambiar_mute(nombre)
        )
        boton_mute.pack(side="left", padx=6)

        boton_monitor = mod_ui_dibujo._crear_icono_plano(
            fila_iconos,
            "🎧",
            medida_icono["fuente_boton"] + 4,
            mod_ui_dibujo._cuadrado_monitor(tipo_monitor),
            lambda: cambiar_monitor(nombre),
            cuadrado=True
        )
        boton_monitor.pack(side="left", padx=6)
    else:
        boton_mute = mod_ui_dibujo._crear_boton_circular(
            fila_iconos,
            "🔇" if muted else "🔊",
            medida_icono["diametro_boton"],
            medida_icono["fuente_boton"],
            "#ff5567" if muted else "#394151",
            lambda: cambiar_mute(nombre)
        )
        boton_mute.pack(side="left", padx=6)

        boton_monitor = mod_ui_dibujo._crear_boton_circular(
            fila_iconos,
            "🎧",
            medida_icono["diametro_boton"],
            medida_icono["fuente_boton"],
            C.COLORES_MONITOREO.get(tipo_monitor, "#394151"),
            lambda: cambiar_monitor(nombre)
        )
        boton_monitor.pack(side="left", padx=6)

    def _abrir_menu_monitor(evento, n=nombre):
        _menu_monitor(n, evento)
        return "break"

    boton_monitor.bind("<Button-3>", _abrir_menu_monitor)

    E.fuentes[nombre] = {
        "contenedor": contenedor,
        "tarjeta_sombra": tarjeta_sombra,
        "cabecera": cabecera_canal,
        "id_texto_nombre": id_texto_nombre,
        "id_texto_sombra": id_texto_sombra,
        "redibujar_cabecera": _redibujar_gradiente_cabecera_fuente,
        "fila_meta": fila_meta,
        "fila_vertical": fila_vertical,
        "fila_iconos": fila_iconos,
        "fader": escala,
        "db": etiqueta_db,
        "mute": boton_mute,
        "monitor": boton_monitor,
        "vu_canvas": vu_canvas,
        "vu_segmentos": vu_segmentos,
        "vu_obs": vu_obs,
        "vu_alto": alto_medidor,
        "vu_visual_db": -60.0,                                                              
        "muted": muted,
        "tipo_monitor": tipo_monitor,
        "nombre_visible": nombre_visible,
        "fuente_tam_max": fuente_nombre_tam_max,
        "fuente_tam_min": fuente_nombre_tam_min,
        "alto_cabecera_base": alto_cabecera_base,
        "arrastrando": False,
        "en_escena": True,
    }

    _actualizar_estado_gris(nombre)

    # Ajuste final anti-recorte: la tarjeta mide un alto fijo de
    # catálogo, pero según las métricas de fuente de cada PC el
    # contenido puede pasarse unos píxeles (y lo primero que se corta
    # son los iconos, lo último en apilarse). Si el contenido supera
    # el alto fijo, la tarjeta crece lo justo para entrar entera: como
    # la cabecera es de alto fijo, TODAS crecen lo mismo en esa PC y
    # siguen alineadas entre sí.
    try:
        contenedor.update_idletasks()
        contenido = (cabecera_canal.winfo_reqheight() + fila_meta.winfo_reqheight()
                     + etiqueta_db.winfo_reqheight() + 7
                     + fila_vertical.winfo_reqheight() + 2
                     + fila_iconos.winfo_reqheight() + 10)
        if contenido > alto_contenedor:
            alto_contenedor = contenido
            contenedor.config(height=alto_contenedor)
            tarjeta_sombra.config(height=alto_contenedor + 18)
            tarjeta_sombra.delete("sombra_difusa")
            mod_ui_dibujo._dibujar_sombra_difusa(
                tarjeta_sombra, 6, 6, ancho_contenedor + 4, alto_contenedor + 4,
                radio=10, capas=3, color_fondo_panel="#131825")
    except Exception:
        pass

    # Recién ahora, con la tarjeta completa, se la ubica en la grilla y
    # se fuerza su pintado: el primer cuadro visible ya es la versión
    # cargada (degradado, nombre centrado, VU, fader y botones), nunca
    # la tarjeta vacía.
    fila, col = _fila_col_fuente(nombre)
    tarjeta_sombra.grid(row=fila, column=col, padx=6, pady=6, sticky="n")
    try:
        tarjeta_sombra.update_idletasks()
        _redibujar_gradiente_cabecera_fuente()
    except Exception:
        pass


def _actualizar_estado_gris(nombre):
    """Pinta la tarjeta de 'nombre' con un tono gris claro -aplicado a
    TODO el chasis, con el mismo mecanismo que una etiqueta de color
    (ver _actualizar_estado_gris más abajo y crear_fader_fuente)- si
    esa fuente NO está en la escena que está al aire ahora mismo (y no
    es una fuente marcada como 'principal', que siempre cuenta como
    activa), o si está muteada. Antes esto sólo oscurecía el cartel de
    arriba, una señal visual pobre; ahora se nota el pad entero, y
    también el medidor VU pasa a tonos de gris (ver
    actualizar_vu_meters_ui). El resto de los controles (fader, mute,
    filtros) siguen funcionando igual: el gris es sólo para que de un
    vistazo se note cuál fuente está realmente sonando en el programa y
    cuál no."""
    widgets = E.fuentes.get(nombre)
    if not widgets:
        return

    es_principal = nombre in E.fuentes_principales
    muted = widgets.get("muted", False)
    en_escena = es_principal or (not E.escena_actual_obtenida) or (nombre in E.escena_actual_nombres)
    widgets["en_escena"] = en_escena

    atenuado = muted or not en_escena
    widgets["atenuado"] = atenuado

    color_etiqueta = E.colores_fuentes.get(nombre)
    if atenuado:
        color_cabecera = C.COLOR_GRIS_ATENUADO
        color_texto = "#202633"
        color_cuerpo = mod_ui_dibujo._oscurecer_color_pct(C.COLOR_GRIS_ATENUADO, 0.42)
        color_meta = mod_ui_dibujo._oscurecer_color_pct(C.COLOR_GRIS_ATENUADO, 0.30)
    elif E.es_moderna():
        if color_etiqueta:
            _base_suave = mod_ui_dibujo._desaturar_color(color_etiqueta)
            color_cabecera = _base_suave
            color_cuerpo = mod_ui_dibujo._oscurecer_color_pct(_base_suave, 0.50)
            color_meta = mod_ui_dibujo._oscurecer_color_pct(_base_suave, 0.35)
        else:
            color_cabecera = C.MOD_CABECERA
            color_cuerpo = C.MOD_TARJETA
            color_meta = C.MOD_FONDO
        color_texto = C.MOD_TEXTO
    else:
        color_cabecera = color_etiqueta or "#3d4d66"
        color_texto = "white"
        color_cuerpo = mod_ui_dibujo._oscurecer_color_pct(color_etiqueta, 0.42) if color_etiqueta else "#202633"
        color_meta = mod_ui_dibujo._oscurecer_color_pct(color_etiqueta, 0.30) if color_etiqueta else "#141a26"

    widgets["cabecera"].config(bg=color_cabecera)
    widgets["cabecera"].datos_color_actual = color_cabecera
    widgets["cabecera"].itemconfig(widgets["id_texto_nombre"], fill=color_texto)
    widgets["cabecera"].itemconfig(widgets["id_texto_sombra"], fill=mod_ui_dibujo._oscurecer_color(color_cabecera, 70))
    widgets["redibujar_cabecera"]()
    for hijo in widgets["cabecera"].winfo_children():
        if isinstance(hijo, tk.Canvas):
            hijo.config(bg=color_cabecera)

    widgets["contenedor"].config(
        bg=color_cuerpo,
        highlightbackground=((C.MOD_ACENTO if E.es_moderna() else C.COLOR_BORDE_PRINCIPAL) if es_principal else "#0e1219"),
        highlightthickness=(3 if es_principal else 2)
    )
    widgets["db"].config(bg=color_cuerpo)
    widgets["fila_vertical"].config(bg=color_cuerpo)
    widgets["fila_iconos"].config(bg=color_cuerpo)
    # El fader acompaña el color del cuerpo (Tk no tiene fondo
    # transparente): así no queda un recuadro de otro color.
    try:
        fader = widgets.get("fader")
        if isinstance(fader, _FaderOBS):
            fader.canvas.config(bg=color_cuerpo)
        elif fader is not None:
            fader.config(bg=color_cuerpo)
    except Exception:
        pass
    # El medidor también sigue al fondo actual: canvas y divisora se
    # tiñen con el color del cuerpo.
    try:
        dib = widgets.get("vu_obs")
        if dib:
            widgets["vu_canvas"].config(bg=color_cuerpo)
            if dib.get("id_divisora") is not None:
                widgets["vu_canvas"].itemconfig(dib["id_divisora"], fill=color_cuerpo)
            dib["bg"] = color_cuerpo
    except Exception:
        pass
    for hijo in widgets["fila_iconos"].winfo_children():
        if isinstance(hijo, tk.Canvas):
            hijo.config(bg=color_cuerpo)
        elif getattr(hijo, "es_plano", False):
            hijo.config(bg=color_cuerpo)

    widgets["fila_meta"].config(bg=(E.color_acento() if E.es_moderna() else color_meta))


def _abrir_menu_contextual_panel_fuentes(event):
    """Menú de clic derecho sobre una zona VACÍA del panel de fuentes
    (el fondo, no una tarjeta): es el equivalente al clic derecho en la
    lista de fuentes de OBS. Lo principal es "Agregar fuente", con un
    submenú de los tipos de entrada de AUDIO que esa instancia de OBS
    tiene registrados, con los mismos nombres que usa el menú de OBS.

    Si el clic cayó encima de una tarjeta, no se hace nada acá: esa
    tarjeta ya tiene su propio menú (_abrir_menu_contextual_fuente) y
    Tk manda el evento primero al widget de más adentro."""
    # Import acá adentro y no arriba del archivo a propósito:
    # consola_obs.audio.fuentes importa este mismo módulo (necesita
    # actualizar() para refrescar la consola después de crear), así que
    # importarlo arriba sería una dependencia circular.
    from consola_obs.audio import fuentes as mod_audio_fuentes

    menu = tk.Menu(
        E.ventana, tearoff=0, bg="#151a24", fg="white",
        activebackground="#323b4c", activeforeground="white"
    )

    if not E.conectado:
        menu.add_command(label="Conectate a OBS para agregar fuentes", state="disabled")
    else:
        submenu_tipos = tk.Menu(
            menu, tearoff=0, bg="#151a24", fg="white",
            activebackground="#323b4c", activeforeground="white"
        )
        tipos = mod_audio_fuentes.tipos_de_audio_para_menu()
        if tipos:
            submenu_tipos._imagenes = []
            for nombre_amigable, icono, kind in tipos:
                foto = mod_ui_dibujo._imagen_svg(icono, 16)
                if foto is None:
                    submenu_tipos.add_command(
                        label=nombre_amigable,
                        command=lambda k=kind, n=nombre_amigable: (
                            mod_audio_fuentes.agregar_fuente_de_tipo(k, n)
                        )
                    )
                else:
                    submenu_tipos._imagenes.append(foto)
                    submenu_tipos.add_command(
                        label=nombre_amigable, image=foto, compound="left",
                        command=lambda k=kind, n=nombre_amigable: (
                            mod_audio_fuentes.agregar_fuente_de_tipo(k, n)
                        )
                    )
            submenu_tipos.add_separator()
        submenu_tipos.add_command(
            label="⋯  Otros tipos de fuente…",
            command=mod_audio_fuentes.abrir_selector_nueva_fuente
        )
        menu.add_cascade(label="➕  Agregar fuente", menu=submenu_tipos)
        menu.add_separator()
        menu.add_command(label="↻  Actualizar fuentes", command=actualizar)

    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _abrir_menu_contextual_fuente(nombre, event):
    """Menú de clic derecho de una tarjeta de fuente: agrupa acá todo lo
    que antes eran botones sueltos siempre visibles en la tarjeta
    (etiqueta de color, filtros, marcar como principal, renombrar), para
    que la tarjeta se vea limpia y esas acciones aparezcan sólo cuando
    se las pide."""
    if nombre not in E.fuentes:
        return
    es_principal = nombre in E.fuentes_principales

    menu = tk.Menu(E.ventana, tearoff=0, bg="#151a24", fg="white", activebackground="#323b4c", activeforeground="white")
    menu._imagenes = []

    def _item(svg, texto, texto_respaldo, comando):
        try:
            foto = mod_ui_dibujo._imagen_svg_menu(svg, 16)
        except Exception:
            foto = None
        if foto is None:
            menu.add_command(label=texto_respaldo, command=comando)
        else:
            menu._imagenes.append(foto)
            menu.add_command(label=texto, image=foto, compound="left", command=comando)

    def _cascada(svg, texto, texto_respaldo, submenu):
        try:
            foto = mod_ui_dibujo._imagen_svg_menu(svg, 16)
        except Exception:
            foto = None
        if foto is None:
            menu.add_cascade(label=texto_respaldo, menu=submenu)
        else:
            menu._imagenes.append(foto)
            menu.add_cascade(label=texto, image=foto, compound="left", menu=submenu)

    _item("menu/menu_renombrar.svg", "Renombrar…", "✏  Renombrar…",
          lambda: _iniciar_renombrar_fuente(nombre))
    _item("menu/menu_favorito_on.svg" if es_principal else "menu/menu_favorito_off.svg",
          ("Quitar de principales" if es_principal else "Marcar como principal"),
          ("☆  Quitar de principales" if es_principal else "★  Marcar como principal"),
          lambda: _alternar_principal(nombre))
    _item("menu/menu_filtros.svg", "Filtros…", "🎚  Filtros…",
          lambda: mod_audio_filtros.abrir_filtros(nombre))
    _item("menu/menu_propiedades.svg", "Propiedades…", "⚙  Propiedades…",
          lambda: mod_audio_propiedades.abrir_propiedades(nombre))
    menu.add_separator()

    submenu_color = tk.Menu(menu, tearoff=0, bg="#151a24", fg="white", activebackground="#323b4c")
    submenu_color.add_command(label="Sin etiqueta", command=lambda: _asignar_color_fuente(nombre, None))
    submenu_color.add_separator()
    for color in E.PALETA_ETIQUETAS:
        if color is None:
            continue
        submenu_color.add_command(
            label="        ", background=color, activebackground=color,
            command=lambda c=color: _asignar_color_fuente(nombre, c)
        )
    _cascada("menu/menu_etiqueta.svg", "Color de etiqueta", "🏷  Color de etiqueta", submenu_color)

    menu.add_separator()
    _item("menu/menu_eliminar.svg", "Quitar de todas las escenas…", "Quitar de todas las escenas…",
          lambda: _quitar_fuente_de_escenas(nombre))
    _item("menu/menu_eliminar.svg", "Eliminar fuente…", "🗑  Eliminar fuente…",
          lambda: _eliminar_fuente(nombre))

    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _fuente_bajo_puntero(x_root, y_root):
    """Devuelve el nombre de la fuente cuya tarjeta está bajo el
    puntero (en coordenadas absolutas de pantalla), o None."""
    try:
        widget = E.ventana.winfo_containing(x_root, y_root)
    except Exception:
        return None
    while widget is not None:
        nombre = getattr(widget, "nombre_fuente", None)
        if nombre is not None:
            return nombre
        widget = widget.master
    return None


def _resaltar_destino_fuente(nombre_nuevo):
    anterior = E._arrastre_fuente["destino_resaltado"]
    if anterior == nombre_nuevo:
        return
    if anterior is not None and anterior in E.fuentes:
        _actualizar_estado_gris(anterior)
    if nombre_nuevo is not None and nombre_nuevo in E.fuentes:
        E.fuentes[nombre_nuevo]["contenedor"].config(
            highlightbackground=C.MOD_ACENTO if E.es_moderna() else "#2fd693",
            highlightthickness=3)
    E._arrastre_fuente["destino_resaltado"] = nombre_nuevo


def _limpiar_resaltado_fuentes():
    anterior = E._arrastre_fuente["destino_resaltado"]
    if anterior is not None and anterior in E.fuentes:
        _actualizar_estado_gris(anterior)
    E._arrastre_fuente["destino_resaltado"] = None


def _iniciar_arrastre_fuente(nombre, event):
    E._arrastre_fuente["nombre"] = nombre
    E._arrastre_fuente["arrastrando"] = False
    E._arrastre_fuente["x_inicio"] = event.x_root
    E._arrastre_fuente["y_inicio"] = event.y_root


def _mover_arrastre_fuente(nombre, event):
    datos = E._arrastre_fuente
    if datos["nombre"] != nombre:
        return
    if not datos["arrastrando"]:
        dx = abs(event.x_root - datos["x_inicio"])
        dy = abs(event.y_root - datos["y_inicio"])
        if dx < C.UMBRAL_ARRASTRE_PX and dy < C.UMBRAL_ARRASTRE_PX:
            return
        datos["arrastrando"] = True
    _resaltar_destino_fuente(_fuente_bajo_puntero(event.x_root, event.y_root))


def _soltar_arrastre_fuente(nombre, event):
    datos = E._arrastre_fuente
    if datos["nombre"] != nombre:
        return
    fue_arrastre = datos["arrastrando"]
    datos["nombre"] = None
    datos["arrastrando"] = False
    _limpiar_resaltado_fuentes()
    if not fue_arrastre:
        return
    destino = _fuente_bajo_puntero(event.x_root, event.y_root)
    if destino is None or destino == nombre:
        return
    _reordenar_fuente(nombre, destino)


def _reordenar_fuente(nombre_origen, nombre_destino):
    """Mueve 'nombre_origen' a la posición de 'nombre_destino' dentro de
    orden_fuentes (arrastrar y soltar para reordenar las tarjetas), y
    reacomoda la grilla y guarda el nuevo orden.

    Antes esto sólo funcionaba bien arrastrando de derecha a izquierda:
    al sacar el origen de la lista para reinsertarlo, si el origen
    estaba ANTES que el destino, todo lo que había entre medio (destino
    incluido) se corría un lugar hacia atrás, así que insertarlo "en la
    posición del destino" lo dejaba apenas un lugar más adelante en vez
    de en el lugar donde se soltó. Moviendo de izquierda a derecha hay
    que insertarlo DESPUÉS de la nueva posición del destino para que
    termine de verdad donde el usuario lo soltó."""
    if nombre_origen not in E.orden_fuentes or nombre_destino not in E.orden_fuentes:
        return
    idx_origen = E.orden_fuentes.index(nombre_origen)
    idx_destino_original = E.orden_fuentes.index(nombre_destino)
    if idx_origen == idx_destino_original:
        return
    moviendo_hacia_adelante = idx_origen < idx_destino_original
    E.orden_fuentes.remove(nombre_origen)
    idx_destino = E.orden_fuentes.index(nombre_destino)
    if moviendo_hacia_adelante:
        idx_destino += 1
    E.orden_fuentes.insert(idx_destino, nombre_origen)
    mod_configuracion.guardar_config_interfaz({"orden_fuentes": list(E.orden_fuentes)})
    _reubicar_fuentes()


def _asignar_color_fuente(nombre, color):
    if color is None:
        E.colores_fuentes.pop(nombre, None)
    else:
        E.colores_fuentes[nombre] = color
    mod_configuracion.guardar_config_interfaz({"colores_fuentes": E.colores_fuentes})
    _actualizar_estado_gris(nombre)


def _alternar_principal(nombre):
    """Marca/desmarca una fuente como 'principal'. Las principales son
    las ÚNICAS que este programa fuerza a crear y mantener activas en
    TODAS las escenas; el resto sólo se muestran tal cual estén."""
    if nombre in E.fuentes_principales:
        E.fuentes_principales.discard(nombre)
    else:
        E.fuentes_principales.add(nombre)
    mod_configuracion.guardar_config_interfaz({"fuentes_principales": sorted(E.fuentes_principales)})
    _actualizar_estado_gris(nombre)
    if nombre in E.fuentes_principales and E.conectado:
        threading.Thread(
            target=mod_obs_cliente._asegurar_fuente_en_todas_las_escenas, args=(nombre,), daemon=True
        ).start()


def sincronizar_fuente(nombre, vol_db, muted, tipo_monitor):
    """Actualiza los widgets de una fuente que ya existe, por si el estado
    cambió desde OBS directamente (otro control, otra escena, etc.)."""

    widgets = E.fuentes[nombre]

    widgets["fader"].set(vol_db)
    if vol_db <= E.UMBRAL_SILENCIO:
        widgets["db"].config(text="SILENCIO", fg=C.MOD_APAGADO if E.es_moderna() else "#828da6")
    else:
        widgets["db"].config(text=f"{vol_db:.1f} dB", fg=C.MOD_TEXTO if E.es_moderna() else "#2fd693")

    widgets["muted"] = muted
    mod_ui_dibujo._actualizar_boton_circular(
        widgets["mute"],
        texto_nuevo=("🔇" if muted else "🔊"),
        color_nuevo=mod_ui_dibujo._color_mute(muted)
    )

    widgets["tipo_monitor"] = tipo_monitor
    mod_ui_dibujo._actualizar_boton_circular(
        widgets["monitor"],
        color_nuevo=(mod_ui_dibujo._cuadrado_monitor(tipo_monitor) if E.es_moderna()
                     else C.COLORES_MONITOREO.get(tipo_monitor, "#394151"))
    )

    _actualizar_estado_gris(nombre)



def cambiar_mute(nombre):
    if not E.conectado:
        return
    try:
        respuesta = E.cliente_obs.toggle_input_mute(nombre)
        nuevo_estado = respuesta.input_muted
        widgets = E.fuentes[nombre]
        widgets["muted"] = nuevo_estado
        mod_ui_dibujo._actualizar_boton_circular(
            widgets["mute"],
            texto_nuevo=("🔇" if nuevo_estado else "🔊"),
            color_nuevo=mod_ui_dibujo._color_mute(nuevo_estado)
        )
        _actualizar_estado_gris(nombre)
    except Exception as e:
        print(f"Error cambiando mute de {nombre}: {e}")


def _fijar_monitor(nombre, tipo):
    """Pone el monitoreo de la fuente en 'tipo' (uno de TIPOS_MONITOREO)
    y actualiza el color del botón. Lo usan el toggle, el menú y vale
    para cualquier estado, incluido el azul."""
    if not E.conectado:
        return
    try:
        E.cliente_obs.set_input_audio_monitor_type(nombre, tipo)

        widgets = E.fuentes[nombre]
        widgets["tipo_monitor"] = tipo
        mod_ui_dibujo._actualizar_boton_circular(
            widgets["monitor"], color_nuevo=(
                mod_ui_dibujo._cuadrado_monitor(tipo) if E.es_moderna()
                else C.COLORES_MONITOREO.get(tipo, "#394151")))
    except Exception as e:
        print(f"Error cambiando monitoreo de {nombre}: {e}")


def cambiar_monitor(nombre):
    """Clic IZQUIERDO del auricular: alterna sólo entre apagado y verde
    (monitoreo + salida). A propósito nunca pasa por el azul (solo
    monitoreo), porque ese estado saca la fuente del stream y llegar a
    él de paso cortaría el audio un instante."""
    if not E.conectado:
        return
    try:
        actual = E.cliente_obs.get_input_audio_monitor_type(nombre).monitor_type
    except Exception:
        actual = E.fuentes.get(nombre, {}).get("tipo_monitor", "OBS_MONITORING_TYPE_NONE")
    if actual == "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT":
        _fijar_monitor(nombre, "OBS_MONITORING_TYPE_NONE")
    else:
        _fijar_monitor(nombre, "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT")


def _menu_monitor(nombre, event):
    """Clic DERECHO del auricular: menú para elegir entre los tres
    estados (apagado, solo yo/azul, yo + stream/verde)."""
    if nombre not in E.fuentes:
        return
    menu = tk.Menu(E.ventana, tearoff=0, bg="#151a24", fg="white",
                   activebackground="#323b4c", activeforeground="white")
    for tipo in E.TIPOS_MONITOREO:
        menu.add_command(
            label=C.ETIQUETAS_MONITOREO.get(tipo, tipo),
            command=lambda t=tipo: _fijar_monitor(nombre, t)
        )
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _renombrar_fuente_localmente(nombre_viejo, nombre_nuevo):
    """Mueve toda la información interna que está indexada por nombre
    (la tarjeta en pantalla, el color de etiqueta, si está marcada
    como 'principal', su posición en el orden, los niveles de audio
    que se venían graficando) de nombre_viejo a nombre_nuevo, y
    reconstruye la tarjeta desde cero con el nombre nuevo.

    Hace falta reconstruirla entera (no alcanza con cambiarle el
    texto): todos los botones de la tarjeta (mute, monitoreo, filtros,
    el fader, la estrella de 'principal') quedan atados al nombre real
    de la fuente en el momento en que se crean, así que si sólo se
    cambiara el texto visible, esos botones seguirían intentando
    controlar en OBS una fuente que ya no existe con ese nombre.

    Se usa tanto para un renombre hecho DESDE este programa (después
    de que OBS confirma el cambio) como para uno hecho desde OBS
    directamente (a través de on_input_name_changed): es indistinto
    de dónde vino, el resultado final tiene que ser el mismo."""
    if nombre_viejo == nombre_nuevo:
        return

    widgets = E.fuentes.get(nombre_viejo)
    if widgets is None:
        # O ya se migró por el otro camino (renombre local + eco del
        # evento de OBS llegando después), o esta fuente ni está
        # cargada en esta instancia. No hay nada que hacer.
        return

    try:
        vol_db = widgets["fader"].get()
    except Exception:
        vol_db = -60.0
    muted = widgets.get("muted", False)
    tipo_monitor = widgets.get("tipo_monitor", "OBS_MONITORING_TYPE_NONE")

    widgets["tarjeta_sombra"].destroy()
    del E.fuentes[nombre_viejo]

    E.niveles_actuales[nombre_nuevo] = E.niveles_actuales.pop(nombre_viejo, 0.0)
    E.niveles_crudos[nombre_nuevo] = E.niveles_crudos.pop(nombre_viejo, 0.0)
    E.niveles_entrada[nombre_nuevo] = E.niveles_entrada.pop(nombre_viejo, 0.0)
    E.niveles_antes_mute[nombre_nuevo] = E.niveles_antes_mute.pop(nombre_viejo, 0.0)
    E.ultima_actualizacion_nivel[nombre_nuevo] = E.ultima_actualizacion_nivel.pop(nombre_viejo, 0.0)
    if nombre_viejo in E.ultima_vez_saturado:
        E.ultima_vez_saturado[nombre_nuevo] = E.ultima_vez_saturado.pop(nombre_viejo)

    if nombre_viejo in E.colores_fuentes:
        E.colores_fuentes[nombre_nuevo] = E.colores_fuentes.pop(nombre_viejo)
        mod_configuracion.guardar_config_interfaz({"colores_fuentes": E.colores_fuentes})

    if nombre_viejo in E.fuentes_principales:
        E.fuentes_principales.discard(nombre_viejo)
        E.fuentes_principales.add(nombre_nuevo)
        mod_configuracion.guardar_config_interfaz({"fuentes_principales": sorted(E.fuentes_principales)})

    if nombre_viejo in E.orden_fuentes:
        E.orden_fuentes[E.orden_fuentes.index(nombre_viejo)] = nombre_nuevo

    if nombre_viejo in E.escena_actual_nombres:
        E.escena_actual_nombres.discard(nombre_viejo)
        E.escena_actual_nombres.add(nombre_nuevo)

    crear_fader_fuente(nombre_nuevo, vol_db, muted, tipo_monitor, nombre_visible=nombre_nuevo)
    _al_redimensionar_fuentes()
    _reubicar_fuentes()


def _iniciar_renombrar_fuente(nombre):
    """Doble clic en el nombre de una fuente: pide el nombre nuevo y,
    si es válido, se lo manda a OBS. La tarjeta en pantalla no se
    renombra en este momento -eso lo termina de hacer
    _renombrar_fuente_localmente, disparada por on_input_name_changed
    apenas OBS confirma el cambio- así que si OBS lo rechaza (por
    ejemplo, por nombre repetido) la interfaz nunca llega a mostrar
    algo que no sea cierto."""
    if not E.conectado:
        messagebox.showinfo("Sin conexión", "Conectate a OBS antes de renombrar una fuente.")
        return
    if nombre == C.NOMBRE_FUENTE_EFECTOS:
        messagebox.showinfo(
            "No se puede renombrar",
            "Esta es la fuente interna del soundboard y el programa depende de que se llame así. No se puede renombrar."
        )
        return
    if nombre == C.NOMBRE_FUENTE_MUSICA:
        messagebox.showinfo(
            "No se puede renombrar",
            "Esta es la fuente interna de la música y el programa depende de que se llame así. No se puede renombrar."
        )
        return

    nuevo_nombre = simpledialog.askstring(
        "Renombrar fuente",
        f"Nuevo nombre para \"{nombre}\":",
        initialvalue=nombre
    )
    if nuevo_nombre is None:
        return
    nuevo_nombre = nuevo_nombre.strip()
    if not nuevo_nombre or nuevo_nombre == nombre:
        return
    if nuevo_nombre in E.fuentes:
        messagebox.showerror("Nombre en uso", f"Ya existe una fuente llamada \"{nuevo_nombre}\".")
        return

    threading.Thread(target=_renombrar_fuente_en_hilo, args=(nombre, nuevo_nombre), daemon=True).start()


def _renombrar_fuente_en_hilo(nombre_viejo, nombre_nuevo):
    try:
        E.cliente_obs.set_input_name(nombre_viejo, nombre_nuevo)
    except Exception as e:
        E.ventana.after(0, lambda e=e: messagebox.showerror(
            "Error al renombrar",
            f"No se pudo renombrar la fuente en OBS.\n\n{e}"
        ))


def _eliminar_fuente(nombre):
    """Clic derecho > 'Eliminar fuente…': a diferencia de todo lo demás
    en este menú, esto borra la fuente de OBS de verdad (no sólo la
    tarjeta de la consola), así que primero se avisa bien claro y
    después se chequea si es una fuente 'global' (Mic/Aux, Audio de
    escritorio: las que vienen de Configuración > Audio de OBS, no de
    una escena puntual), porque borrar esas no es lo mismo que borrar
    una fuente común y puede dejar ese canal roto en OBS -así que no se
    permite desde acá-. La tarjeta se termina de sacar sola cuando
    llegue el evento on_input_removed, igual que si se hubiera borrado
    directamente desde OBS."""
    if not E.conectado:
        messagebox.showwarning("Sin conexión", "Conectate a OBS para eliminar una fuente.")
        return
    if nombre == C.NOMBRE_FUENTE_EFECTOS:
        messagebox.showinfo(
            "No se puede eliminar",
            "Esta es la fuente interna del soundboard y el programa depende de que exista. "
            "No se puede eliminar."
        )
        return
    if nombre == C.NOMBRE_FUENTE_MUSICA:
        messagebox.showinfo(
            "No se puede eliminar",
            "Esta es la fuente interna de la música y el programa depende de que exista. "
            "No se puede eliminar."
        )
        return

    # La consulta de si es una fuente global se hace en un hilo (como
    # cualquier otro pedido a OBS) para no trabar la interfaz mientras
    # se espera la respuesta; recién con eso resuelto se sigue con el
    # aviso o la confirmación, ya de vuelta en el hilo principal.
    threading.Thread(target=_chequear_global_y_eliminar_fuente, args=(nombre,), daemon=True).start()


def _chequear_global_y_eliminar_fuente(nombre):
    try:
        globales = mod_obs_cliente._leer_fuentes_globales_obs()
    except Exception:
        globales = set()
    E.ventana.after(0, lambda: _continuar_eliminar_fuente(nombre, nombre in globales))


def _continuar_eliminar_fuente(nombre, es_global):
    if nombre not in E.fuentes:
        # Pudo haber desaparecido mientras se consultaba si era global.
        return

    if es_global:
        messagebox.showinfo(
            "No se puede eliminar",
            f"\"{nombre}\" es un canal de audio global de OBS (Mic/Aux o Audio de escritorio, "
            "de Configuración > Audio), no una fuente común de una escena. Borrarlo desde acá "
            "puede dejar ese canal roto en OBS, así que no está permitido desde la consola: "
            "si hace falta, se cambia desde la propia Configuración > Audio de OBS."
        )
        return

    if not messagebox.askyesno(
        "Eliminar fuente",
        f"Se va a borrar la fuente \"{nombre}\" de OBS por completo -no sólo de la consola-. "
        "Esta acción no se puede deshacer.\n\n¿Confirmar?"
    ):
        return

    threading.Thread(target=_eliminar_fuente_en_hilo, args=(nombre,), daemon=True).start()


def _eliminar_fuente_en_hilo(nombre):
    try:
        E.cliente_obs.remove_input(nombre)
    except Exception as e:
        E.ventana.after(0, lambda e=e: messagebox.showerror(
            "Error al eliminar",
            f"No se pudo eliminar la fuente en OBS.\n\n{e}"
        ))


def _quitar_fuente_de_escenas(nombre):
    """Clic derecho > 'Quitar de todas las escenas…': saca la fuente de
    todas las escenas de OBS pero NO la borra (sigue existiendo como
    input y se puede reagregar desde OBS). La tarjeta queda atenuada
    hasta que vuelva a alguna escena."""
    if not E.conectado:
        messagebox.showwarning("Sin conexión", "Conectate a OBS para modificar las escenas.")
        return
    if nombre == C.NOMBRE_FUENTE_EFECTOS:
        messagebox.showinfo(
            "No se puede quitar",
            "Esta es la fuente interna del soundboard y el programa depende de que esté en escena. "
            "No se puede quitar."
        )
        return
    if nombre == C.NOMBRE_FUENTE_MUSICA:
        messagebox.showinfo(
            "No se puede quitar",
            "Esta es la fuente interna de la música y el programa depende de que esté en escena. "
            "No se puede quitar."
        )
        return
    if nombre not in E.fuentes:
        return
    if nombre in E.fuentes_principales:
        messagebox.showinfo(
            "Es una fuente principal",
            f"\"{nombre}\" está marcada como principal y el programa la mantiene en todas las "
            "escenas. Quitala de principales primero si la querés sacar de escena."
        )
        return
    if not messagebox.askyesno(
        "Quitar de todas las escenas",
        f"Se va a quitar \"{nombre}\" de todas las escenas de OBS.\n"
        "La fuente NO se borra: sigue existiendo y se puede reagregar desde OBS."
        "\n\n¿Confirmar?"
    ):
        return
    threading.Thread(target=_quitar_de_escenas_en_hilo, args=(nombre,), daemon=True).start()


def _quitar_de_escenas_en_hilo(nombre):
    try:
        cuantas = mod_obs_cliente.quitar_fuente_de_todas_las_escenas(nombre)
    except Exception as e:
        E.ventana.after(0, lambda e=e: messagebox.showerror(
            "Error al quitar",
            f"No se pudo quitar la fuente de las escenas.\n\n{e}"
        ))
        return

    def _avisar():
        try:
            actualizar()
        except Exception:
            pass
        if cuantas:
            messagebox.showinfo(
                "Listo",
                f"\"{nombre}\" se quitó de {cuantas} escena(s).")
        else:
            messagebox.showinfo(
                "Sin cambios",
                f"\"{nombre}\" no estaba en ninguna escena.")

    E.ventana.after(0, _avisar)



def actualizar():
    if not E.conectado:
        messagebox.showinfo(
            "Sin conexión",
            "Conectate a OBS antes de actualizar."
        )
        return

    E.boton_actualizar.config(state="disabled", text="ACTUALIZANDO...")

    threading.Thread(target=_actualizar_en_hilo, daemon=True).start()


def _actualizar_en_hilo():
    datos_fuentes = []
    error_general = None

    try:
        mod_obs_cliente.preparar_fuente_efectos()
    except Exception as e:
        print(f"No se pudo preparar la fuente de efectos: {e}")

    try:
        mod_obs_cliente.preparar_fuente_musica()
    except Exception as e:
        print(f"No se pudo preparar la fuente de música: {e}")

    try:
        mod_obs_cliente.asegurar_fuentes_principales_en_todas_las_escenas()
    except Exception as e:
        print(f"No se pudo asegurar las fuentes principales en todas las escenas: {e}")

    try:
        # STOP de orden: solo sin sesión activa (con un efecto en curso
        # lo mataría: era parte del bug de "agregar fuente corta todo").
        if not mod_obs_cliente._sesion_efecto_activa():
            E.cliente_obs.trigger_media_input_action(
                C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
            )
    except Exception:
        pass

    try:
        entradas = E.cliente_obs.get_input_list().inputs
    except Exception as e:
        error_general = str(e)
        entradas = []

    for entrada in entradas:
        try:
            nombre = mod_obs_eventos._valor(entrada, "input_name", "inputName")

            if not nombre:
                continue

            try:
                respuesta_volumen = E.cliente_obs.get_input_volume(nombre)
                vol_db = mod_obs_eventos._valor(respuesta_volumen, "input_volume_db", "inputVolumeDb")
                if vol_db is None:
                    vol_db = -60.0
            except Exception as e:
                print(f"No se pudo leer el volumen de '{nombre}': {e}")
                vol_db = -60.0

            try:
                respuesta_mute = E.cliente_obs.get_input_mute(nombre)
                muted = mod_obs_eventos._valor(respuesta_mute, "input_muted", "inputMuted")
                if muted is None:
                    muted = False
            except Exception as e:
                print(f"No se pudo leer el mute de '{nombre}': {e}")
                muted = False

            try:
                respuesta_monitor = E.cliente_obs.get_input_audio_monitor_type(nombre)
                tipo_monitor = mod_obs_eventos._valor(respuesta_monitor, "monitor_type", "monitorType")
                if not tipo_monitor:
                    tipo_monitor = "OBS_MONITORING_TYPE_NONE"
            except Exception as e:
                print(f"No se pudo leer el monitoreo de '{nombre}': {e}")
                tipo_monitor = "OBS_MONITORING_TYPE_NONE"

            datos_fuentes.append({
                "nombre": nombre,
                "vol_db": vol_db,
                "muted": muted,
                "tipo_monitor": tipo_monitor
            })

        except Exception as e:
            print(f"No se pudo leer una fuente: {e}")
            continue

    nombres_en_escena = set()
    escena_leida_ok = False
    try:
        respuesta_escena = E.cliente_obs.get_current_program_scene()
        escena_actual = mod_obs_eventos._valor(
            respuesta_escena,
            "current_program_scene_name", "currentProgramSceneName",
            "scene_name", "sceneName"
        )
        if escena_actual:
            items = E.cliente_obs.get_scene_item_list(escena_actual).scene_items
            for it in items:
                nombre_item = mod_obs_eventos._valor(it, "source_name", "sourceName")
                habilitado = mod_obs_eventos._valor(it, "scene_item_enabled", "sceneItemEnabled")
                if nombre_item and habilitado:
                    nombres_en_escena.add(nombre_item)
            escena_leida_ok = True
    except Exception as e:
        print(f"No se pudo leer la escena activa: {e}")

    try:
        nombres_en_escena |= mod_obs_cliente._leer_fuentes_globales_obs()
    except Exception as e:
        print(f"No se pudo leer las fuentes de audio globales de OBS: {e}")

    E.ventana.after(0, lambda: _aplicar_actualizacion(datos_fuentes, error_general, nombres_en_escena, escena_leida_ok))


def _aplicar_actualizacion(datos_fuentes, error, nombres_en_escena=None, escena_leida_ok=False):

    E.boton_actualizar.config(state="normal", text="ACTUALIZAR FUENTES")

    if error is not None:
        messagebox.showerror(
            "Error al actualizar",
            f"No se pudieron obtener las fuentes.\n\n{error}"
        )
        return

    if escena_leida_ok:
        E.escena_actual_nombres = nombres_en_escena or set()
        E.escena_actual_obtenida = True

    nombres_activos = [d["nombre"] for d in datos_fuentes]

    for nombre_existente in list(E.fuentes.keys()):
        if nombre_existente not in nombres_activos:
            E.fuentes[nombre_existente]["tarjeta_sombra"].destroy()
            del E.fuentes[nombre_existente]
            E.niveles_actuales.pop(nombre_existente, None)
            E.niveles_crudos.pop(nombre_existente, None)
            E.niveles_entrada.pop(nombre_existente, None)
            E.ultima_vez_saturado.pop(nombre_existente, None)
            if nombre_existente in E.orden_fuentes:
                E.orden_fuentes.remove(nombre_existente)
            _limpiar_referencias_fuente_borrada(nombre_existente)

    for datos in datos_fuentes:
        nombre = datos["nombre"]
        try:
            if nombre in E.fuentes:
                sincronizar_fuente(
                    nombre, datos["vol_db"], datos["muted"], datos["tipo_monitor"]
                )
            else:
                if nombre == C.NOMBRE_FUENTE_EFECTOS:
                    nombre_visible = C.ETIQUETA_FUENTE_EFECTOS
                elif nombre == C.NOMBRE_FUENTE_MUSICA:
                    nombre_visible = C.ETIQUETA_FUENTE_MUSICA
                else:
                    nombre_visible = nombre
                crear_fader_fuente(
                    nombre, datos["vol_db"], datos["muted"], datos["tipo_monitor"],
                    nombre_visible=nombre_visible
                )
        except Exception as e:
            print(f"Error creando/actualizando '{nombre}': {e}")

    _al_redimensionar_fuentes()
    _reubicar_fuentes()


def _limpiar_referencias_fuente_borrada(nombre):
    """Cuando una fuente desaparece de OBS -sea porque se la borró
    desde 'Eliminar fuente…' acá mismo, sea porque se la borró
    directamente desde OBS- no alcanza con sacar la tarjeta: antes esto
    dejaba basura colgada (la fuente seguía marcada como 'principal' o
    con color de etiqueta en la config guardada para siempre, y si
    tenía una ventana de Filtros o Propiedades abierta, esa ventana
    quedaba editando una fuente que ya no existe). Se limpia todo acá,
    en un único lugar, para que valga tanto si el borrado se hizo desde
    la consola como desde OBS."""
    cambios_interfaz = {}
    if nombre in E.fuentes_principales:
        E.fuentes_principales.discard(nombre)
        cambios_interfaz["fuentes_principales"] = sorted(E.fuentes_principales)
    if nombre in E.colores_fuentes:
        E.colores_fuentes.pop(nombre, None)
        cambios_interfaz["colores_fuentes"] = E.colores_fuentes
    if cambios_interfaz:
        mod_configuracion.guardar_config_interfaz(cambios_interfaz)

    if E._dialogo_filtros_abierto.get("nombre") == nombre:
        ventana_filtros = E._dialogo_filtros_abierto.get("ventana")
        E._dialogo_filtros_abierto["nombre"] = None
        E._dialogo_filtros_abierto["refrescar"] = None
        E._dialogo_filtros_abierto["ventana"] = None
        if ventana_filtros is not None:
            try:
                ventana_filtros.destroy()
            except Exception:
                pass

    if E._dialogo_propiedades_abierto.get("nombre") == nombre:
        ventana_propiedades = E._dialogo_propiedades_abierto.get("ventana")
        E._dialogo_propiedades_abierto["nombre"] = None
        E._dialogo_propiedades_abierto["ventana"] = None
        if ventana_propiedades is not None:
            try:
                ventana_propiedades.destroy()
            except Exception:
                pass
