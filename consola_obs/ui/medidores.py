import math
import time
import tkinter as tk

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs.audio import motor_local as mod_motor_local
from consola_obs.ui import dibujo as mod_ui_dibujo


def _dibujar_segmentos_led(canvas, ancho_segmentos, alto, bg_apagado="#10161f", offset_y=0):
    """Dibuja los 'segmentos' (LEDs) del medidor y devuelve la lista con
    sus ids y colores: cada LED tiene un color fijo según su posición
    (verde abajo, amarillo en el medio, rojo arriba), igual que en un
    mixer de verdad, y se prende o apaga según el nivel actual. También
    guarda un color gris equivalente por segmento (más claro arriba,
    más oscuro abajo) para cuando la fuente está atenuada (fuera de
    escena o muteada, ver _actualizar_estado_gris): ahí el medidor deja
    de usar los colores normales y pasa a tonos de gris, para que
    coincida con el resto del pad.

    'offset_y' corre todo el dibujo hacia abajo esa cantidad de
    píxeles, dejando ese margen libre arriba (y el mismo abajo, si el
    canvas se hizo más alto que 'alto' en esa medida) para que las
    etiquetas "0" y "-60" de los extremos no queden pegadas al borde
    del canvas y termine viéndose la mitad del número cortada."""
    segmentos = []
    gap = 2
    alto_seg = alto / C.NUM_SEGMENTOS_VU
    radio_led = max(1, min(3, (ancho_segmentos - 2) * 0.35))
    for i in range(C.NUM_SEGMENTOS_VU):
        y0 = i * alto_seg
        y1 = y0 + alto_seg - gap
        y_medio = (y0 + y1) / 2
        db_seg = -(y_medio / alto) * 60.0
        if db_seg >= -9:
            color_on = "#ff5d6c"
            color_on_gris = "#cbd2e6"
        elif db_seg >= -20:
            color_on = "#f2c464"
            color_on_gris = "#8e9ab3"
        else:
            color_on = "#2fd693"
            color_on_gris = "#6b7492"
        rect_id = mod_ui_dibujo._dibujar_rect_redondeado(
            canvas, 1, y0 + offset_y, ancho_segmentos - 1, y1 + offset_y, radio=radio_led, fill=bg_apagado, outline=""
        )
        segmentos.append({"id": rect_id, "db": db_seg, "color_on": color_on, "color_on_gris": color_on_gris})
    return segmentos


def _actualizar_medidor_led(canvas, segmentos, db_visual, atenuado=False, bg_apagado="#10161f", saturado=False,
                            estado=None):
    """Prende los LEDs hasta el nivel actual. ... (ver docstring original).

    Optimización: si nada cambió desde el último cuadro (misma cantidad
    de LEDs encendidos, mismo saturado/atenuado) no se toca el canvas.
    Si cambió, sólo se repintan los LEDs que cambian de color, no los 24."""
    n_total = len(segmentos)
    # Los segmentos vienen ordenados de arriba (0 dB) hacia abajo
    # (-60 dB): los encendidos son siempre los últimos `n` de la lista.
    n_encendidos = 0
    for seg in segmentos:
        if db_visual >= seg["db"]:
            n_encendidos += 1
    if estado is not None:
        anterior = estado.get("ultimo")
        actual = (n_encendidos, saturado, atenuado)
        if anterior == actual:
            return
        estado["ultimo"] = actual
        primero_viejo = n_total - (anterior[0] if anterior else 0)
        mismo_modo = (anterior is not None and anterior[1] == saturado
                      and anterior[2] == atenuado)
    else:
        primero_viejo = 0
        mismo_modo = False
    primero_nuevo = n_total - n_encendidos
    # Sólo cambia la franja entre el borde viejo y el nuevo; más allá
    # del borde mayor todo sigue igual, salvo que haya cambiado el
    # modo (saturado/atenuado), que recolorea el tramo encendido.
    desde = min(primero_viejo, primero_nuevo)
    hasta = max(primero_viejo, primero_nuevo) if mismo_modo else n_total
    color_sat = C.COLOR_LED_SATURADO_GRIS if atenuado else C.COLOR_LED_SATURADO
    for seg in segmentos[desde:hasta]:
        if db_visual >= seg["db"]:
            if saturado:
                color = color_sat
            else:
                color = seg["color_on_gris"] if atenuado else seg["color_on"]
        else:
            color = bg_apagado
        canvas.itemconfig(seg["id"], fill=color)


def _y_para_db(db, alto=C.ALTO_CANAL):
    """Convierte un valor en dB (0 a -60) a una coordenada Y del canvas,
    con 0 dB arriba de todo y -60 dB abajo de todo, igual que en OBS."""
    db = max(-60, min(0, db))
    return (-db / 60.0) * alto


# Escala del medidor estilo OBS (tema Moderna).
MARCAS_DB_OBS = [0, -6, -12, -18, -24, -30, -36, -48, -60]

_cache_barra_obs = {}


# Geometría del medidor Moderna: dos canales (L/R) con divisora fina
# del color del fondo en el medio, como en OBS.
ANCHO_BARRA_MODERNA_TOTAL = 16
ANCHO_DIVISORA_MODERNA = 2


def _mezclar_rgb(c1, c2, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


# Color y degradado de la barra se editan en constantes.py
# (BARRA_MODERNA / BARRA_MODERNA_MEZCLA). El clip de saturación siempre
# es rojo (gris claro en variante gris).
_BARRA_MODERNA_DEFECTO = {"alta": (255, 59, 48), "media": (242, 196, 100), "baja": (47, 214, 147)}
# Gris funcional (mute/otra escena): editable en constantes.py
# (BARRA_MODERNA_GRIS), con los mismos valores por defecto.
_PALETA_BARRA_GRIS_DEFECTO = {
    "rojo": (232, 235, 242), "amarillo": (154, 164, 178), "verde": (91, 100, 120),
}


def _gris_barra_actual():
    return _normalizar_paleta(getattr(C, "BARRA_MODERNA_GRIS", None),
                              _PALETA_BARRA_GRIS_DEFECTO)


def _rgb_valido(v):
    return (isinstance(v, (tuple, list)) and len(v) == 3
            and all(isinstance(x, (int, float)) and 0 <= x <= 255 for x in v))


_EQUIV_ZONAS = {"alta": "rojo", "media": "amarillo", "baja": "verde",
                "rojo": "rojo", "amarillo": "amarillo", "verde": "verde"}


def _normalizar_paleta(d, defecto):
    """Lee una paleta aceptando claves alta/media/baja O
    rojo/amarillo/verde (para que un desliz editando no la rompa en
    silencio): devuelve siempre claves rojo/amarillo/verde válidas."""
    out = {}
    for clave in ("rojo", "amarillo", "verde"):
        v = None
        if isinstance(d, dict):
            for k, std in _EQUIV_ZONAS.items():
                if std == clave and k in d:
                    v = d[k]
                    break
        out[clave] = tuple(int(x) for x in v) if _rgb_valido(v) else defecto[clave]
    return out


def _esquema_barra_actual():
    normalizado = _normalizar_paleta(getattr(C, "BARRA_MODERNA", None),
                                     {"rojo": (255, 59, 48), "amarillo": (242, 196, 100),
                                      "verde": (47, 214, 147)})
    return {"alta": normalizado["rojo"], "media": normalizado["amarillo"],
            "baja": normalizado["verde"]}


def _mezcla_degradado_actual():
    try:
        m = getattr(C, "BARRA_MODERNA_MEZCLA", None)
        m1, m2 = float(m[0]), float(m[1])
        if m1 >= 0 and m2 >= 0:
            return (m1, m2)
    except Exception:
        pass
    return (1.5, 2.0)
_PALETA_BARRA_COLOR_TENUE = C.GUIA_BARRA_COLOR
_PALETA_BARRA_GRIS_TENUE = C.GUIA_BARRA_GRIS
_GUIA_DEFECTO = {"rojo": (9, 7, 6), "amarillo": (9, 8, 6), "verde": (7, 10, 8)}


def _color_zona_barra(db, paleta, mezcla=(1.5, 2.0)):
    """Color para un dB dado. `mezcla` = (ancho1, ancho2) en dB de los
    degradados entre zonas; (0, 0) son cortes duros."""
    m1, m2 = mezcla
    if db >= -9.0:
        return paleta["rojo"]
    if m1 > 0 and db >= -9.0 - m1:
        return _mezclar_rgb(paleta["amarillo"], paleta["rojo"], (db + 9.0 + m1) / m1)
    if db >= -18.5:
        return paleta["amarillo"]
    if m2 > 0 and db >= -18.5 - m2:
        return _mezclar_rgb(paleta["verde"], paleta["amarillo"], (db + 18.5 + m2) / m2)
    return paleta["verde"]


def _imagen_barra_obs(ancho, alto, gris=False, tenue=False):
    """Tira vertical de la GUÍA de fondo (colores oscuros, editables en
    constantes.py), cacheada por tamaño. None sin Pillow."""
    try:
        from consola_obs.compat import HAY_PILLOW, Image, ImageTk
    except Exception:
        return None
    if not HAY_PILLOW:
        return None
    clave = (ancho, alto, gris, tenue)
    if clave in _cache_barra_obs:
        return _cache_barra_obs[clave]
    try:
        paleta = _normalizar_paleta(
            _PALETA_BARRA_GRIS_TENUE if gris else _PALETA_BARRA_COLOR_TENUE, _GUIA_DEFECTO)
        ancho, alto = max(2, int(ancho)), max(2, int(alto))
        tira = Image.new("RGB", (1, alto))
        px = tira.load()
        for y in range(alto):
            db = -(y / max(1, alto - 1)) * 60.0
            # Cortes duros también en la guía (sin difuminado).
            px[0, y] = _color_zona_barra(db, paleta, (0.0, 0.0))
        foto = ImageTk.PhotoImage(tira.resize((ancho, alto)))
        _cache_barra_obs[clave] = foto
        return foto
    except Exception:
        return None


def _dibujar_barra_obs(canvas, ancho_barra, alto, bg="#080b10", offset_y=0):
    """Barra de nivel de dos canales estilo OBS: guía tenue de fondo con
    divisora negra y, encima, una fila por píxel y por canal con cortes
    duros de color (sin difuminado) que se muestran/ocultan hasta el
    nivel. Más línea de pico y testigo de clip rojo. Devuelve el dict
    de ids (id_filas guarda pares [izquierdo, derecho] por fila)."""
    x0, x1 = 1, max(2, ancho_barra - 1)
    y0, y1 = offset_y, offset_y + alto
    div = ANCHO_DIVISORA_MODERNA
    ancho_canal = max(2, (x1 - x0 - div) // 2)
    x_div0 = x0 + (x1 - x0 - div) // 2
    x_div1 = x_div0 + div
    canvas.create_rectangle(x0, y0, x1, y1, fill=bg, outline="")
    id_img_tenue = id_img = None
    foto_tenue = _imagen_barra_obs(x1 - x0, alto, gris=False, tenue=True)
    if foto_tenue is not None:
        canvas.imagen_barra_obs_tenue = foto_tenue
        id_img_tenue = canvas.create_image(x0, y0, anchor="nw", image=foto_tenue)
    # Divisora del color del fondo entre los canales (tapa la guía en
    # la franja del medio; las filas del frente ya dejan ese hueco).
    id_divisora = canvas.create_rectangle(x_div0, y0, x_div1, y1, fill=bg, outline="")
    colores = []
    colores_gris = []
    esquema = _esquema_barra_actual()
    paleta = {"rojo": esquema["alta"], "amarillo": esquema["media"], "verde": esquema["baja"]}
    gris_cfg = _gris_barra_actual()
    # Cortes duros entre zonas como en OBS (BARRA_MODERNA_MEZCLA queda
    # sin efecto a propósito).
    mezcla = (0.0, 0.0)
    for i in range(alto):
        db = -(i / max(1, alto - 1)) * 60.0
        colores.append("#%02x%02x%02x" % _color_zona_barra(db, paleta, mezcla))
        colores_gris.append("#%02x%02x%02x" % _color_zona_barra(db, gris_cfg, mezcla))
    id_filas = []
    for i in range(alto):
        id_izq = canvas.create_rectangle(
            x0, y0 + i, x0 + ancho_canal, y0 + i + 1, fill=colores[i], outline="", state="hidden")
        id_der = canvas.create_rectangle(
            x1 - ancho_canal, y0 + i, x1, y0 + i + 1, fill=colores[i], outline="", state="hidden")
        id_filas.append((id_izq, id_der))
    id_barra = None
    id_clip = canvas.create_rectangle(x0, y0, x1, y0 + 3, fill=C.MOD_CLIP, outline="", state="hidden")
    id_pico = canvas.create_line(x0, y1, x1, y1, fill=C.MOD_PICO, width=2)
    id_borde = canvas.create_rectangle(x0, y0, x1, y1, fill="", outline="#0a1830", width=1)
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "alto": alto,
            "bg": bg, "id_img": id_img, "id_img_tenue": id_img_tenue,
            "id_divisora": id_divisora,
            "id_barra": id_barra, "id_filas": id_filas,
            "colores": colores, "colores_gris": colores_gris,
            "id_clip": id_clip, "id_pico": id_pico, "id_borde": id_borde,
            "gris": False}


def _actualizar_barra_obs(canvas, dib, db_visual, db_pico, atenuado=False, saturado=False, estado=None):
    """Muestra las filas hasta el nivel, el pico en su marca y, si
    satura, tiñe de rojo (gris claro en variante gris) todo el tramo
    visible, como el aviso de clipping del otro diseño. En gris
    (mute/otra escena) filas y guía usan los tonos grises. Sólo toca
    las filas que cambian."""
    if not dib:
        return
    alto = dib["alto"]
    y_nivel = int(round(_y_para_db(db_visual, alto)))
    y_pico = int(round(_y_para_db(db_pico, alto)))
    actual = (y_nivel, y_pico, saturado, atenuado)
    anterior = estado.get("ultimo") if estado is not None else None
    if anterior == actual:
        return
    if estado is not None:
        estado["ultimo"] = actual
    filas = dib.get("id_filas") or []
    if atenuado != dib.get("gris"):
        colores = dib["colores_gris"] if atenuado else dib["colores"]
        sat_fill = C.COLOR_LED_SATURADO_GRIS if atenuado else C.MOD_CLIP
        for i, par in enumerate(filas):
            relleno = sat_fill if (saturado and i >= y_nivel) else colores[i]
            for iid in par:
                canvas.itemconfig(iid, fill=relleno)
        foto_tenue = _imagen_barra_obs(dib["x1"] - dib["x0"], alto,
                                       gris=atenuado, tenue=True)
        if foto_tenue is not None and dib.get("id_img_tenue") is not None:
            canvas.imagen_barra_obs_tenue = foto_tenue
            canvas.itemconfig(dib["id_img_tenue"], image=foto_tenue)
        dib["gris"] = atenuado
    # Filas visibles: desde y_nivel hasta abajo. Sólo flippean las que
    # están entre el borde viejo y el nuevo (o todas si no hay previo
    # o si cambió la saturación, que recolorea el tramo visible).
    y_viejo = anterior[0] if anterior else 0
    desde = max(0, min(y_viejo, y_nivel))
    hasta = min(alto, max(y_viejo, y_nivel))
    if anterior is None or anterior[2] != saturado:
        desde = min(desde, y_nivel)
        hasta = alto
    color_sat = C.COLOR_LED_SATURADO_GRIS if atenuado else C.MOD_CLIP
    colores = dib["colores_gris"] if atenuado else dib["colores"]
    for i in range(desde, hasta):
        par = filas[i]
        if i >= y_nivel:
            relleno = color_sat if saturado else colores[i]
            for iid in par:
                canvas.itemconfig(iid, fill=relleno, state="normal")
        else:
            for iid in par:
                canvas.itemconfig(iid, state="hidden")
    canvas.coords(dib["id_pico"], dib["x0"], dib["y0"] + y_pico, dib["x1"], dib["y0"] + y_pico)
    canvas.itemconfig(dib["id_pico"], fill=C.MOD_PICO_GRIS if atenuado else C.MOD_PICO)
    canvas.itemconfig(dib["id_clip"], state="normal" if saturado else "hidden")


# ---------------------------------------------------------------------
# Control de volumen horizontal (clic derecho sobre un pad)
# ---------------------------------------------------------------------

class _ControlVolumenHorizontal:
    """Barra de volumen horizontal estilo OBS: la hermana acostada de
    _FaderOBS (pista negra, relleno azul, perilla circular blanca),
    pero sin marcas ni lineas blancas, y que trabaja en porcentaje.
    Muestra el porcentaje al pasar el mouse sobre la perilla."""
    ALTO = 26
    PERILLA = 16
    COLOR_PISTA = "#0a0a0a"
    COLOR_LLENO = "#4365cb"

    def __init__(self, parent, ancho, bg, al_cambiar, pct_inicial=100.0, max_pct=100):
        self.ancho = max(80, int(ancho))
        self.alto = self.ALTO
        self.al_cambiar = al_cambiar
        self.max_pct = max_pct
        self._pct = max(0.0, min(float(max_pct), float(pct_inicial)))
        self._margen = self.PERILLA // 2 + 2
        self.canvas = tk.Canvas(parent, width=self.ancho, height=self.alto,
                                bg=bg, highlightthickness=0, cursor="hand2")
        cy = self.alto / 2
        self._cy = cy
        m = self._margen
        self.canvas.create_line(m, cy, self.ancho - m, cy, width=4,
                                fill=self.COLOR_PISTA, capstyle="round")
        self.id_fill = self.canvas.create_line(
            m, cy, m, cy, width=4, fill=self.COLOR_LLENO, capstyle="round")
        foto = mod_ui_dibujo._imagen_pildora_blanca(self.PERILLA, self.PERILLA)
        r = self.PERILLA / 2
        if foto is not None:
            self.canvas.imagen_perilla = foto
            self.id_handle = self.canvas.create_image(m, cy, image=foto)
            self._handle_es_foto = True
        else:
            self.id_handle = self.canvas.create_oval(
                m - r, cy - r, m + r, cy + r, fill="#f2f5fa", outline="#9aa4b2")
            self._handle_es_foto = False
        self._tooltip = None
        self._tooltip_label = None
        self._vigilante = None
        self.arrastrando = False
        self.canvas.bind("<ButtonPress-1>", self._al_presionar)
        self.canvas.bind("<B1-Motion>", self._al_arrastrar)
        self.canvas.bind("<ButtonRelease-1>", self._al_soltar_interno)
        self.canvas.bind("<Motion>", self._al_hover)
        self.canvas.bind("<Leave>", self._al_leave)
        self.canvas.bind("<Enter>", self._al_enter)
        # El cartelito del porcentaje es una ventanita aparte: si el
        # control desaparece (cambio de pestaña, se cierra Ajustes) tiene
        # que morir con él, si no queda "volando" sobre la ventana.
        self.canvas.bind("<Destroy>", lambda e: self._ocultar_tooltip(), add="+")
        self.canvas.bind("<Unmap>", lambda e: self._ocultar_tooltip(), add="+")
        self._hover = False
        self._repintar()

    def _recorrido(self):
        return max(1, self.ancho - 2 * self._margen)

    def _x_de_pct(self, pct):
        pct = max(0.0, min(self.max_pct, pct))
        return self._margen + (pct / self.max_pct) * self._recorrido()

    def _pct_de_x(self, x):
        t = (max(self._margen, min(self.ancho - self._margen, x)) - self._margen) / self._recorrido()
        return max(0.0, min(self.max_pct, t * self.max_pct))

    def set(self, pct):
        try:
            self._pct = max(0.0, min(self.max_pct, float(pct)))
        except Exception:
            self._pct = 100.0 if self.max_pct >= 100 else self.max_pct
        self._repintar()

    def get(self):
        return self._pct

    def pack(self, *args, **kwargs):
        return self.canvas.pack(*args, **kwargs)

    def bind(self, sequence=None, func=None, add="+"):
        # add="+" por defecto: quien enganche un evento desde afuera (por
        # ejemplo <Leave> en Ajustes) no debe pisar los internos.
        return self.canvas.bind(sequence, func, add)

    def _repintar(self):
        x = self._x_de_pct(self._pct)
        m = self._margen
        cy = self._cy
        # Thicker bar and bigger handle on hover
        ancho_linea = 6 if self._hover else 4
        self.canvas.itemconfig(self.id_fill, width=ancho_linea)
        # Update the track line width too
        # (the track is the first line created, id_fill is the second)
        self.canvas.coords(self.id_fill, m, cy, x, cy)
        if self._handle_es_foto:
            self.canvas.coords(self.id_handle, x, cy)
        else:
            r = (self.PERILLA / 2) + (2 if self._hover else 0)
            self.canvas.coords(self.id_handle, x - r, cy - r, x + r, cy + r)

    def _avisar(self):
        try:
            self.al_cambiar(self._pct)
        except Exception as e:
            print(f"Error en el control de volumen: {e}")

    def _al_presionar(self, event):
        self.arrastrando = True
        self._al_arrastrar(event)

    def _al_soltar_interno(self, event):
        self.arrastrando = False
        # Al soltar, el cartelito sólo sigue si el mouse quedó sobre la perilla.
        if abs(event.x - self._x_de_pct(self._pct)) >= self.PERILLA + 4:
            self._ocultar_tooltip()

    def _al_arrastrar(self, event):
        self.set(self._pct_de_x(event.x))
        self._avisar()
        # Durante el arrastre el cartelito acompaña a la perilla.
        self._mostrar_tooltip(event.x_root, event.y_root)

    def _al_hover(self, event):
        if self.arrastrando:
            return
        x_ball = self._x_de_pct(self._pct)
        if abs(event.x - x_ball) < self.PERILLA + 4:
            self.canvas.configure(cursor="sb_h_double_arrow")
            self._mostrar_tooltip(event.x_root, event.y_root)
        else:
            self.canvas.configure(cursor="hand2")
            self._ocultar_tooltip()

    def _al_leave(self, event):
        self._hover = False
        if not self.arrastrando:
            self._ocultar_tooltip()
        self.canvas.configure(cursor="hand2")
        self._repintar()

    def _al_enter(self, event):
        self._hover = True
        self._repintar()

    def _mostrar_tooltip(self, x, y):
        try:
            if self._tooltip is None:
                top = tk.Toplevel(self.canvas.winfo_toplevel())
                top.overrideredirect(True)
                top.attributes("-topmost", True)
                lbl = tk.Label(top, bg="#222", fg="white",
                               font=(E.FUENTE_UI, 9), padx=6, pady=2)
                lbl.pack()
                self._tooltip = top
                self._tooltip_label = lbl
                self._vigilar_tooltip()
            self._tooltip_label.configure(text="%.0f%%" % self._pct)
            self._tooltip.geometry("+%d+%d" % (x + 12, y - 34))
            self._tooltip.lift()
        except Exception:
            self._ocultar_tooltip()

    def _puntero_sobre_control(self):
        """True si el mouse sigue encima del control y éste es visible."""
        try:
            if not self.canvas.winfo_exists() or not self.canvas.winfo_viewable():
                return False
            px, py = self.canvas.winfo_pointerxy()
            x0, y0 = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
            return (x0 - 2 <= px <= x0 + self.canvas.winfo_width() + 2
                    and y0 - 2 <= py <= y0 + self.canvas.winfo_height() + 2)
        except Exception:
            return False

    def _vigilar_tooltip(self):
        """Red de seguridad: mientras el cartelito exista, cada tanto se
        comprueba que el mouse siga sobre el control (o se esté
        arrastrando). Si no, se cierra. Evita que quede flotando aunque
        se pierda un evento <Leave>."""
        self._vigilante = None
        if self._tooltip is None:
            return
        if not self.arrastrando and not self._puntero_sobre_control():
            self._ocultar_tooltip()
            return
        try:
            self._vigilante = self.canvas.after(120, self._vigilar_tooltip)
        except Exception:
            self._ocultar_tooltip()

    def _ocultar_tooltip(self):
        if self._vigilante is not None:
            try:
                self.canvas.after_cancel(self._vigilante)
            except Exception:
                pass
            self._vigilante = None
        if self._tooltip is not None:
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None
            self._tooltip_label = None


def construir_control_volumen_pad(padre, al_cambiar, pct_inicial=100.0, ancho=190, bg="#151a24", max_pct=100):
    """Barra de volumen horizontal para el popup de un pad o para los
    ajustes. 'al_cambiar' recibe el porcentaje (0 a max_pct) mientras se
    arrastra."""
    return _ControlVolumenHorizontal(padre, ancho, bg, al_cambiar, pct_inicial, max_pct)


# ---------------------------------------------------------------------
# Medidores horizontales de solo lectura (Ajustes > Audio)
# ---------------------------------------------------------------------

# Alto extra bajo la barra para los números de la escala (-60 ... 0).
ALTO_ETIQUETAS_MEDIDOR_H = 14
# Zonas del medidor de izquierda (-60) a derecha (0), mismos cortes de
# color que la barra vertical (ver _color_zona_barra).
_ZONAS_MEDIDOR_H = (("verde", -60.0, -18.5), ("amarillo", -18.5, -9.0), ("rojo", -9.0, 0.0))


def _hex_rgb(rgb):
    return "#%02x%02x%02x" % tuple(int(x) for x in rgb)


def dibujar_medidor_horizontal(canvas, ancho, alto, db_inicial=-60.0, bg="#080b10"):
    """Barra de nivel horizontal estilo OBS (cortes duros de color sobre
    una guía tenue, pico y escala en dB debajo). El canvas tiene que
    medir 'alto' + ALTO_ETIQUETAS_MEDIDOR_H de alto. Devuelve el dict
    que usa actualizar_medidor_horizontal (con el canvas adentro)."""
    x0, x1 = 1, max(4, int(ancho) - 1)
    y0, y1 = 1, 1 + int(alto)
    ancho_util = x1 - x0

    def x_de(db):
        return x0 + ((max(-60.0, min(0.0, db)) + 60.0) / 60.0) * ancho_util

    canvas.create_rectangle(x0, y0, x1, y1, fill=bg, outline="")
    guia = _normalizar_paleta(_PALETA_BARRA_COLOR_TENUE, _GUIA_DEFECTO)
    esquema = _esquema_barra_actual()
    colores = {"rojo": esquema["alta"], "amarillo": esquema["media"], "verde": esquema["baja"]}
    zonas = []
    for nombre, desde, hasta in _ZONAS_MEDIDOR_H:
        canvas.create_rectangle(x_de(desde), y0, x_de(hasta), y1,
                                fill=_hex_rgb(guia[nombre]), outline="")
        id_zona = canvas.create_rectangle(
            x_de(desde), y0, x_de(desde), y1, fill=_hex_rgb(colores[nombre]),
            outline="", state="hidden")
        zonas.append({"id": id_zona, "desde": desde, "hasta": hasta})
    id_pico = canvas.create_line(x0, y0, x0, y1, fill=C.MOD_PICO, width=2, state="hidden")
    canvas.create_rectangle(x0, y0, x1, y1, fill="", outline="#0a1830", width=1)
    for marca in MARCAS_DB_OBS:
        x = x_de(marca)
        canvas.create_line(x, y1, x, y1 + 3, fill=C.MOD_MARCA_DB, width=1)
        ancla = "nw" if marca <= -60 else ("ne" if marca >= 0 else "n")
        canvas.create_text(x, y1 + 3, text=str(marca), fill=C.MOD_MARCA_DB,
                           font=(E.FUENTE_UI, 7), anchor=ancla)
    dib = {"canvas": canvas, "x0": x0, "x1": x1, "y0": y0, "y1": y1,
           "zonas": zonas, "id_pico": id_pico, "x_de": x_de,
           "ultimo": None, "visual_db": -60.0, "pico_db": -60.0, "pico_t": 0.0}
    actualizar_medidor_horizontal(dib, db_inicial, db_inicial)
    return dib


def actualizar_medidor_horizontal(dib, db, pico):
    """Muestra la barra hasta 'db' y el pico en su marca. Sólo toca el
    canvas si cambió algo (al píxel)."""
    if not dib:
        return
    canvas = dib["canvas"]
    x_de = dib["x_de"]
    x_nivel = x_de(db)
    x_pico = x_de(pico)
    clave = (int(round(x_nivel)), int(round(x_pico)))
    if dib.get("ultimo") == clave:
        return
    dib["ultimo"] = clave
    for zona in dib["zonas"]:
        izq = x_de(zona["desde"])
        der = min(x_nivel, x_de(zona["hasta"]))
        if db <= zona["desde"] or der <= izq:
            canvas.itemconfig(zona["id"], state="hidden")
        else:
            canvas.coords(zona["id"], izq, dib["y0"], der, dib["y1"])
            canvas.itemconfig(zona["id"], state="normal")
    if pico <= -59.0:
        canvas.itemconfig(dib["id_pico"], state="hidden")
    else:
        canvas.coords(dib["id_pico"], x_pico, dib["y0"], x_pico, dib["y1"])
        canvas.itemconfig(dib["id_pico"], state="normal")


def _db_de_mul(mul):
    mul = max(0.0, min(1.0, mul))
    if mul <= 0.0001:
        return -60.0
    return max(-60.0, min(0.0, 20 * math.log10(mul)))


def _nivel_mul_vigente(nombre, ahora):
    """Nivel que OBS reporta para una fuente (ya con fader, mute y
    filtros), o 0 si los datos están viejos."""
    if (ahora - E.ultima_actualizacion_nivel.get(nombre, 0.0)) > C.UMBRAL_DATOS_VIEJOS_SEG:
        return 0.0
    return E.niveles_actuales.get(nombre, 0.0)


def _seguir_nivel_horizontal(dib, db_objetivo, ahora):
    """Caída suave y pico sostenido 0,8 s (igual que la barra vertical)."""
    visual = dib["visual_db"]
    if db_objetivo >= visual:
        visual = db_objetivo
    else:
        visual = max(db_objetivo, visual - E.CAIDA_POR_CUADRO)
    pico, pico_t = dib["pico_db"], dib["pico_t"]
    if db_objetivo >= pico:
        pico, pico_t = db_objetivo, ahora
    elif ahora - pico_t > 0.8:
        pico = max(db_objetivo, pico - E.CAIDA_POR_CUADRO)
    dib["visual_db"], dib["pico_db"], dib["pico_t"] = visual, pico, pico_t
    return visual, pico


def _actualizar_medidores_ajustes(ahora):
    """Los dos medidores de Ajustes > Audio. OBS (stream): lo más fuerte
    entre efectos y música. Parlantes (PC): sólo lo que de verdad sale
    por los parlantes (efectos con 'Escuchar acá', música con 'Música en
    PC' y sonando). Sólo se pintan si la pestaña está a la vista."""
    dib_obs = getattr(E, "medidor_volumen_obs", None)
    dib_pc = getattr(E, "medidor_volumen_pc", None)
    if not dib_obs and not dib_pc:
        return
    try:
        if not (dib_obs or dib_pc)["canvas"].winfo_ismapped():
            return
    except Exception:
        return
    # La barra de volumen de OBS (arriba del medidor) sigue a los faders.
    refrescar_controles = getattr(E, "_refrescar_controles_audio", None)
    if refrescar_controles is not None:
        refrescar_controles(ahora)
    efectos = _nivel_mul_vigente(C.NOMBRE_FUENTE_EFECTOS, ahora)
    musica = _nivel_mul_vigente(C.NOMBRE_FUENTE_MUSICA, ahora)
    nivel_obs = max(efectos, musica)
    nivel_pc = 0.0
    if getattr(E, "escuchar_en_pc", False):
        nivel_pc = max(nivel_pc, efectos)
    if getattr(E, "musica_en_parlantes", False) and mod_motor_local.sonando():
        nivel_pc = max(nivel_pc, musica)
    for dib, nivel in ((dib_obs, nivel_obs), (dib_pc, nivel_pc)):
        if not dib:
            continue
        visual, pico = _seguir_nivel_horizontal(dib, _db_de_mul(nivel), ahora)
        actualizar_medidor_horizontal(dib, visual, pico)


def apagar_medidores():
    """Apaga todos los medidores de una sola vez. Se usa al entrar en
    modo super-optimizador; al salir, el próximo cuadro VU los repinta
    completos (el estado se invalida acá)."""
    for widgets in list(E.fuentes.values()):
        try:
            canvas = widgets.get("vu_canvas")
            if canvas is None:
                continue
            dib = widgets.get("vu_obs")
            if dib:
                for par in dib.get("id_filas") or []:
                    for iid in par:
                        canvas.itemconfig(iid, state="hidden")
                canvas.coords(dib["id_pico"], dib["x0"], dib["y1"], dib["x1"], dib["y1"])
                canvas.itemconfig(dib["id_clip"], state="hidden")
                widgets.setdefault("vu_obs_estado", {}).pop("ultimo", None)
                continue
            segmentos = widgets.get("vu_segmentos") or []
            for seg in segmentos:
                canvas.itemconfig(seg["id"], fill="#10161f")
            widgets.setdefault("vu_led_estado", {}).pop("ultimo", None)
        except Exception:
            pass


def _log_debug_vu(nombre, nivel_mul_crudo, datos_vigentes, saturado, ahora):
    if C.DEBUG_VU_FUENTE is None or nombre != C.DEBUG_VU_FUENTE:
        return
    if (ahora - E._ultimo_debug_vu["t"]) < C.INTERVALO_DEBUG_VU_SEG:
        return
    E._ultimo_debug_vu["t"] = ahora
    if nivel_mul_crudo <= 0.0001:
        db_txt = "-inf"
    else:
        db_txt = f"{20 * math.log10(nivel_mul_crudo):6.1f}"
    print(
        f"[DEBUG VU] {nombre!r}  nivel={nivel_mul_crudo:.4f}  db={db_txt}  "
        f"datos_vigentes={datos_vigentes}  saturado={saturado}"
    )


def actualizar_vu_meters_ui():
    # Se programa el próximo cuadro ANTES de trabajar: así la cadencia
    # es fija (33ms) y el costo del cuadro actual no suma delay.
    try:
        E.ventana.after(C.INTERVALO_VU_MS, actualizar_vu_meters_ui)
    except Exception as e:
        print("VU after error:", e)
        return
    ahora = time.monotonic()
    if E.fuentes:
        print("VU: fuentes =", list(E.fuentes.keys()))
    for nombre, widgets in list(E.fuentes.items()):
        atenuado = widgets.get("atenuado", False)
        datos_vigentes = (ahora - E.ultima_actualizacion_nivel.get(nombre, 0.0)) <= C.UMBRAL_DATOS_VIEJOS_SEG

        # Reflejo directo de OBS: usamos el mismo nivel que OBS ya
        # calcula y reporta para esta fuente (niveles_actuales, que
        # sale de 'valor_canal' en on_input_volume_meters) -es decir,
        # el nivel DESPUÉS de fader, mute Y CUALQUIER filtro (Ganancia,
        # Compresor, etc.)-, sin reconstruir nada a mano ni aplicar
        # ninguna calibración propia. Es la manera de garantizar que
        # el medidor de acá sea IDÉNTICO al de OBS en todo momento, sea
        # cual sea la fuente y tenga o no filtros puestos: en vez de
        # adivinar cuánta ganancia suman el fader y los filtros y
        # tratar de reconstruir el resultado, usamos el resultado que
        # OBS ya calculó.
        #
        # ÚNICA excepción: mientras la fuente está MUTEADA. La mayoría
        # de las veces, mutear SÍ corta 'niveles_actuales' a silencio
        # de verdad (el mute corta la señal antes de que OBS la
        # reporte), así que ahí se reconstruye el nivel con
        # 'niveles_crudos' (el nivel "de entrada" que manda OBS aparte,
        # que sigue llegando en vivo aunque la fuente esté muteada -es
        # el mismo dato que hace que el cuadradito de "input level" del
        # mixer de OBS se siga moviendo con una fuente muteada-). Ese
        # valor YA viene con los filtros aplicados (Ganancia,
        # Compresor, etc. -comprobado: con un filtro de Ganancia
        # activo, sumarle además la ganancia del filtro a mano contaba
        # esa ganancia DOS VECES, lo que hacía que la barra se pasara
        # ~20dB para arriba y quedara pegada contra el techo casi sin
        # moverse-), así que NO hay que aplicarle de nuevo
        # 'ganancia_filtros_db'. Lo único que sí le falta para quedar
        # comparable a la barra activa es la ganancia del fader actual
        # (el valor de OBS es de ANTES del fader) y el ajuste fino de
        # CALIBRACION_VU_MUTEADO_DB (más arriba en el archivo) para lo
        # que no se puede leer de OBS.
        #
        # IMPORTANTE: para esta cuenta se usa 'niveles_crudos', que
        # guarda el mismo dato SIN recortarlo a 1.0 (a diferencia de
        # 'niveles_entrada', que sí lo recorta y está pensado para otra
        # cosa -mostrar un número acotado-). Si acá se usara la versión
        # recortada, cualquier fuente cuyo filtro de Ganancia empuje la
        # señal por encima de 0dB (algo habitual en audio de
        # escritorio, que suele entrar más "caliente" que un
        # micrófono) quedaría SIEMPRE tope en 1.0 antes de multiplicar
        # por el fader, y el resultado nunca podría superar
        # exactamente la ganancia del fader -aunque el audio real siga
        # subiendo y bajando, el medidor se queda clavado justo en la
        # posición de la barra de volumen, sin reaccionar-. Usando el
        # valor sin recortar, un pasaje que satura de verdad puede dar,
        # por ejemplo, 2.5 o 3.0 (varios dB por encima de 0dB), y al
        # multiplicarlo por el fader el resultado también puede superar
        # 1.0 con toda razón; el recorte a [0.0, 1.0] para el dibujo se
        # hace más abajo igual que para cualquier otro nivel (ver
        # 'nivel_mul'), así que no se pierde nada, sólo se lo posterga
        # hasta después de la multiplicación en vez de hacerlo antes.
        #
        # PERO: cuando la fuente muteada tiene puesto un filtro que
        # toca la ganancia (Ganancia, Compresor), 'niveles_actuales'
        # NO cae a silencio -OBS lo sigue reportando en vivo igual que
        # con la fuente sin mutear-, y en ese caso hay que usar
        # DIRECTAMENTE ese valor (ver UMBRAL_NIVEL_MUTEADO_DIRECTO, más
        # arriba en el archivo) en vez de reconstruirlo a mano. En
        # cuanto 'niveles_actuales' vuelve a estar realmente en 0 (se
        # destilencia la fuente, o es una fuente sin este tipo de
        # filtro), se usa de nuevo el reflejo exacto de OBS de arriba.
        muted = widgets.get("muted", False)
        if widgets.get("oculta"):
            # Fuente oculta: el indicador no se muestra hasta
            # desocultar. Se fuerza silencio directo (sin la
            # reconstrucción de 'elif muted', que seguiría moviendo
            # la barra con la señal de entrada aunque esté muteada).
            nivel_mul_crudo = 0.0
        elif not datos_vigentes:
            nivel_mul_crudo = 0.0
        elif muted:
            # Antes de reconstruir nada a mano, nos fijamos si
            # 'niveles_actuales' -el mismo dato que se usa dos líneas
            # más abajo para la fuente SIN mutear, y que ahí funciona
            # perfecto- ya viene vivo por su cuenta (ver
            # UMBRAL_NIVEL_MUTEADO_DIRECTO más arriba en el archivo).
            # Con algunas fuentes OBS sigue reportando ahí el nivel
            # real aunque la fuente esté muteada, y usar ese dato
            # directamente es estrictamente mejor que reconstruirlo: es
            # el valor exacto que ya calculó OBS, sin ninguna
            # aproximación de acá. Sólo si de verdad está en 0 (mute
            # que sí corta la señal) se cae a la reconstrucción manual
            # con 'niveles_crudos'.
            nivel_directo = E.niveles_actuales.get(nombre, 0.0)
            if nivel_directo > C.UMBRAL_NIVEL_MUTEADO_DIRECTO:
                nivel_mul_crudo = nivel_directo
            else:
                nivel_entrada_crudo = E.niveles_crudos.get(nombre, 0.0)
                vol_db_actual = widgets["fader"].get()
                if vol_db_actual <= E.UMBRAL_SILENCIO:
                    ganancia_fader = 0.0
                else:
                    ganancia_fader = 10 ** (vol_db_actual / 20.0)
                ganancia_calibracion = 10 ** (C.CALIBRACION_VU_MUTEADO_DB / 20.0)
                nivel_mul_crudo = nivel_entrada_crudo * ganancia_fader * ganancia_calibracion
        else:
            nivel_mul_crudo = E.niveles_actuales.get(nombre, 0.0)

        # Si el nivel que reporta OBS llega o supera 0 dB, la fuente
        # está saturando de verdad (así lo ve OBS) y el medidor se
        # pone todo en rojo (ver _actualizar_medidor_led). Esto es
        # redundante con la detección que ya hace
        # on_input_volume_meters sobre el mismo dato crudo de OBS
        # -cualquiera de las dos alcanza-, se deja así por las dudas
        # de que el ciclo de refresco de acá agarre un valor que el
        # otro todavía no procesó.
        if nivel_mul_crudo >= C.UMBRAL_SATURACION_MUL:
            E.ultima_vez_saturado[nombre] = ahora

        nivel_mul = max(0.0, min(1.0, nivel_mul_crudo))

        if nivel_mul <= 0.0001:
            db_objetivo = -60.0
        else:
            db_objetivo = max(-60.0, min(0.0, 20 * math.log10(nivel_mul)))

        db_visual = widgets.get("vu_visual_db", -60.0)
        if db_objetivo >= db_visual:
            db_visual = db_objetivo
        else:
            db_visual = max(db_objetivo, db_visual - E.CAIDA_POR_CUADRO)
        if widgets.get("oculta"):
            # Apagado instantáneo (sin la caída animada): oculta =
            # indicador apagado hasta desocultar.
            db_visual = -60.0

        widgets["vu_visual_db"] = db_visual

        # Si la fuente está atenuada (fuera de escena / con el medidor
        # en gris) la saturación se sigue marcando igual -ver
        # _actualizar_medidor_led-, sólo que en gris en vez de rojo,
        # para no perder el aviso de saturación por estar en modo gris.
        # En oculta no hay aviso: el indicador está apagado del todo.
        saturado = ((ahora - E.ultima_vez_saturado.get(nombre, -math.inf)) <= C.DURACION_SATURACION_SEG
                    and not widgets.get("oculta"))

        _log_debug_vu(nombre, nivel_mul_crudo, datos_vigentes, saturado, ahora)

        if E._modo_super.get("activo"):
            # En modo super sólo se sigue el nivel (matemática barata);
            # el pintado se pausa y se invalida para repintar completo
            # al salir, sin saltos.
            widgets.setdefault("vu_led_estado", {}).pop("ultimo", None)
            widgets.setdefault("vu_obs_estado", {}).pop("ultimo", None)
            continue

        if E.es_moderna():
            # Pico con sostenido (estilo OBS): sube al instante, se queda
            # 0.8s quieto y después cae.
            pico = widgets.get("vu_pico_db", -60.0)
            pico_t = widgets.get("vu_pico_t", 0.0)
            if widgets.get("oculta"):
                pico, pico_t = -60.0, ahora
            elif db_objetivo >= pico:
                pico, pico_t = db_objetivo, ahora
            elif ahora - pico_t > 0.8:
                pico = max(db_objetivo, pico - E.CAIDA_POR_CUADRO)
            widgets["vu_pico_db"] = pico
            widgets["vu_pico_t"] = pico_t
            _actualizar_barra_obs(
                widgets["vu_canvas"], widgets.get("vu_obs"), db_visual, pico,
                atenuado=atenuado, saturado=saturado,
                estado=widgets.setdefault("vu_obs_estado", {})
            )
            continue

        _actualizar_medidor_led(
            widgets["vu_canvas"], widgets["vu_segmentos"], db_visual,
            atenuado=atenuado, saturado=saturado,
            estado=widgets.setdefault("vu_led_estado", {})
        )

    if not E._modo_super.get("activo"):
        _actualizar_medidores_ajustes(ahora)
