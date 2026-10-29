import math
"""Pestaña Audio de Ajustes (versión moderna).

Tarjetas con interruptores en lugar de listas desplegables Sí/No, y en
'Volumen de salida' una barra de volumen (la misma de los pads) arriba
de cada medidor:

- Volumen OBS (stream): mueve los faders de Efectos y Música en OBS.
- Volumen parlantes (PC): volumen general de lo que suena en esta PC.

La lógica de volumen vive en audio/volumen_salida.py; acá sólo hay
interfaz.
"""

import time
import tkinter as tk

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs.audio import musica as mod_audio_musica
from consola_obs.audio import reproduccion as mod_audio_reproduccion
from consola_obs.audio import volumen_salida as mod_volumen_salida
from consola_obs.audio import estado_audio_local as mod_estado_audio_local
from consola_obs.audio import prueba_local as mod_prueba_local
from consola_obs.ui import medidores as mod_ui_medidores


COLOR_TARJETA = "#1a2130"
COLOR_BORDE = "#2b3548"
COLOR_AYUDA = "#8fa0bd"
COLOR_INTERRUPTOR_APAGADO = "#3a4358"
# Ancho de la barra de volumen y del medidor (iguales para que la
# escala quede alineada).
ANCHO_BARRAS = 380
ALTO_MEDIDOR = 12
# Cada cuánto se relee el volumen de OBS para mover la barra (si lo
# cambiaron desde una tarjeta o desde el propio OBS).
REFRESCO_BARRA_OBS_S = 0.25


def _mezclar(c1, c2, t):
    """Color intermedio entre dos #rrggbb (t de 0 a 1)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _texto_db(db):
    if db <= E.UMBRAL_SILENCIO:
        return "SILENCIO"
    return f"{db:.1f} dB"


class _Interruptor:
    """Interruptor tipo pÃ­ldora (como los de un celular), con la perilla
    deslizÃ¡ndose suave al cambiar. Dibujado con PIL a doble resoluciÃ³n
    para que los bordes sean suaves (anti-aliasing)."""
    ANCHO = 52
    ALTO = 28
    DURACION_S = 0.14
    _SCALE = 4  # supersampling

    def __init__(self, padre, bg, valor, al_cambiar):
        self.al_cambiar = al_cambiar
        self.valor = bool(valor)
        self._pos = 1.0 if self.valor else 0.0
        self._tarea = None
        self._bg = bg
        # Canvas a tamaÃ±o normal; la imagen se dibuja anti-aliased.
        self.canvas = tk.Canvas(padre, width=self.ANCHO, height=self.ALTO, bg=bg,
                                highlightthickness=0, cursor="hand2")
        self._img_id = None
        self._foto = None
        self.canvas.bind("<Button-1>", self._alternar)
        self._pintar()

    def pack(self, *args, **kwargs):
        return self.canvas.pack(*args, **kwargs)

    def _render(self, pos):
        from PIL import Image, ImageDraw, ImageTk
        w = self.ANCHO * self._SCALE
        h = self.ALTO * self._SCALE
        s = self._SCALE
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img, "RGBA")
        # Pista
        cy = h // 2
        x0, x1 = 14 * s, (self.ANCHO - 14) * s
        radio_pista = (self.ALTO - 4) * s // 2
        color_off = (58, 67, 88, 255)
        color_on = (67, 101, 203, 255)
        # Interpolar color
        r = int(color_off[0] + (color_on[0] - color_off[0]) * pos)
        g = int(color_off[1] + (color_on[1] - color_off[1]) * pos)
        b = int(color_off[2] + (color_on[2] - color_off[2]) * pos)
        # Dibujar pista redondeada
        d.rounded_rectangle(
            [x0 - radio_pista, cy - radio_pista, x1 + radio_pista, cy + radio_pista],
            radius=radio_pista, fill=(r, g, b, 255))
        # Perilla
        px = int((14 + pos * (self.ANCHO - 28)) * s)
        pr = 9 * s
        d.ellipse([px - pr, cy - pr, px + pr, cy + pr],
                  fill=(242, 245, 250, 255), outline=(192, 200, 216, 255), width=1 * s)
        # Redimensionar a tamaÃ±o normal con anti-aliasing
        img = img.resize((self.ANCHO, self.ALTO), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _pintar(self):
        foto = self._render(self._pos)
        self._foto = foto
        if self._img_id is None:
            self._img_id = self.canvas.create_image(0, 0, anchor="nw", image=foto)
        else:
            self.canvas.itemconfig(self._img_id, image=foto)

    def _alternar(self, _evento=None):
        self.valor = not self.valor
        try:
            self.al_cambiar(self.valor)
        except Exception as e:
            print(f"Error al cambiar la opciÃ³n de audio: {e}")
        self._animar()

    def _animar(self):
        if self._tarea is not None:
            try:
                self.canvas.after_cancel(self._tarea)
            except Exception:
                pass
        self._tarea = self.canvas.after(16, self._paso_animacion)

    def _paso_animacion(self):
        objetivo = 1.0 if self.valor else 0.0
        if abs(self._pos - objetivo) < 0.05:
            self._pos = objetivo
            self._pintar()
            self._tarea = None
            return
        self._pos += (objetivo - self._pos) * 0.3
        self._pintar()
        self._tarea = self.canvas.after(16, self._paso_animacion)


def _seccion(marco, texto):
    contenedor = tk.Frame(marco, bg=C.COLOR_MENU_FONDO)
    contenedor.pack(fill="x", padx=16, pady=(14, 4))
    tk.Label(contenedor, text=texto, bg=C.COLOR_MENU_FONDO, fg=C.COLOR_MENU_TITULO,
             font=(E.FUENTE_UI, 8, "bold")).pack(side="left")
    tk.Frame(contenedor, bg="#232c3d", height=1).pack(
        side="left", fill="x", expand=True, padx=(10, 0), pady=(6, 0))


def _tarjeta(padre):
    """Tarjeta con borde fino; devuelve el marco interior con aire."""
    borde = tk.Frame(padre, bg=COLOR_BORDE)
    borde.pack(fill="x", padx=16, pady=4)
    cuerpo = tk.Frame(borde, bg=COLOR_TARJETA)
    cuerpo.pack(fill="x", padx=1, pady=1)
    interior = tk.Frame(cuerpo, bg=COLOR_TARJETA)
    interior.pack(fill="x", padx=14, pady=10)
    return interior


def _tarjeta_interruptor(padre, titulo, ayuda, valor, al_cambiar):
    interior = _tarjeta(padre)
    textos = tk.Frame(interior, bg=COLOR_TARJETA)
    textos.pack(side="left", fill="x", expand=True)
    tk.Label(textos, text=titulo, bg=COLOR_TARJETA, fg="white",
             font=(E.FUENTE_UI, 9, "bold"), anchor="w").pack(fill="x")
    tk.Label(textos, text=ayuda, bg=COLOR_TARJETA, fg=COLOR_AYUDA,
             font=(E.FUENTE_UI, 8), anchor="w", justify="left",
             wraplength=300).pack(fill="x", pady=(2, 0))
    interruptor = _Interruptor(interior, COLOR_TARJETA, valor, al_cambiar)
    interruptor.pack(side="right", padx=(12, 0))
    return interruptor


# Curva de la barra: db = -60 * (1 - p)^1.5, con p = porcentaje/100.
# Continua de punta a punta: 100 % = 0 dB (máximo), 0 % = silencio, y en
# el medio baja de a poco (no hay un punto donde "se corte" el sonido).
_EXPONENTE_CURVA = 1.5


def _db_a_pct(db):
    if db is None or db <= -60.0:
        return 0.0
    if db >= 0.0:
        return 100.0
    return max(0.0, min(100.0, 100.0 * (1.0 - (-db / 60.0) ** (1.0 / _EXPONENTE_CURVA))))


def _pct_a_db(pct):
    if pct <= 0:
        return -60.0
    if pct >= 100:
        return 0.0
    p = pct / 100.0
    return max(-60.0, min(0.0, -60.0 * (1.0 - p) ** _EXPONENTE_CURVA))


def _tarjeta_volumen(padre, titulo, ayuda, db_inicial, al_cambiar, al_soltar):
    """Titulo, barra de volumen (en porcentaje) sin medidor de colores."""
    interior = _tarjeta(padre)
    cabecera = tk.Frame(interior, bg=COLOR_TARJETA)
    cabecera.pack(fill="x")
    tk.Label(cabecera, text=titulo, bg=COLOR_TARJETA, fg="white",
             font=(E.FUENTE_UI, 9, "bold"), anchor="w").pack(side="left")
    pct_inicial = _db_a_pct(db_inicial)

    def _cambio(pct):
        try:
            db = _pct_a_db(pct)
            al_cambiar(db)
        except Exception as e:
            print("VOLUMEN ERROR:", e)
            import traceback
            traceback.print_exc()

    control = mod_ui_medidores.construir_control_volumen_pad(
        interior, _cambio, pct_inicial, ancho=ANCHO_BARRAS, bg=COLOR_TARJETA,
        max_pct=100)
    control.pack(anchor="w", pady=(6, 4))
    # add="+" (por defecto en el control): no pisa los eventos internos.
    control.bind("<ButtonRelease-1>", lambda e: al_soltar())
    tk.Label(interior, text=ayuda, bg=COLOR_TARJETA, fg=COLOR_AYUDA,
             font=(E.FUENTE_UI, 8), anchor="w", justify="left",
             wraplength=ANCHO_BARRAS).pack(fill="x", pady=(2, 0))
    return control


def construir(marco):
    """Arma la pestaña Audio dentro de 'marco'."""
    # Compatibilidad: variables Sí/No que antes usaban las listas.
    E.variable_escuchar = tk.StringVar(value="Sí" if E.escuchar_en_pc else "No")
    E.variable_nivelar = tk.StringVar(value="Sí" if E.nivelar_efectos else "No")
    E.variable_musica_pc = tk.StringVar(value="Sí" if E.musica_en_parlantes else "No")

    def _si_no(variable, funcion):
        def _aplicar(valor):
            texto = "Sí" if valor else "No"
            variable.set(texto)
            funcion(texto)
        return _aplicar

    _seccion(marco, "Reproducción")
    # (Prueba de parlantes removida.)
    E.selector_escuchar = _tarjeta_interruptor(
        marco, "Escuchar acá",
        "Los efectos suenan también por los parlantes de esta PC.",
        E.escuchar_en_pc,
        _si_no(E.variable_escuchar, mod_audio_reproduccion.cambiar_escuchar_en_pc))
    E.selector_nivelar = _tarjeta_interruptor(
        marco, "Nivelar efectos",
        "Iguala el volumen de todos los pads.",
        E.nivelar_efectos,
        _si_no(E.variable_nivelar, mod_audio_reproduccion.cambiar_nivelar_efectos))
    E.selector_musica_pc = _tarjeta_interruptor(
        marco, "Música en PC",
        "La música de fondo suena también por los parlantes de esta PC (por el "
        "stream siempre sale). Su volumen es independiente de OBS: lo regula la "
        "barra de la bocina del reproductor.",
        E.musica_en_parlantes,
        _si_no(E.variable_musica_pc, mod_audio_musica.cambiar_musica_en_parlantes))

    # (Volumen de salida removido: el audio siempre suena a volumen completo.)
