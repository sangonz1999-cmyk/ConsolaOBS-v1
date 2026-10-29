"""Menú contextual único de toda la app (estilo moderno).

Antes había dos estilos: el popup propio del pad (moderno) y varios
tk.Menu nativos (los de las fuentes, la música, etc.). Ahora TODOS los
clic derecho pasan por acá, así que se ven y se comportan igual.

Uso:

    def _construir(m):
        m.item("menu/menu_renombrar.svg", "Renombrar…", "✏  Renombrar…", cmd)
        m.separador()
        m.flyout_colores("menu/menu_etiqueta.svg", "Color de etiqueta",
                         "🏷  Color de etiqueta", E.PALETA_ETIQUETAS,
                         actual, al_elegir)
        m.bloque(lambda marco: ...)   # widgets propios (ej. barra de volumen)

    menu_moderno.abrir(event, _construir)

Los submenús (flyouts) se despliegan solos al pasar el mouse por la
fila, hacia la derecha, con una animación suave. Si por cualquier
motivo el popup propio no se puede armar, la MISMA función de
construcción arma un tk.Menu clásico: el clic derecho nunca queda
muerto.
"""

import time
import tkinter as tk

from consola_obs import estado as E
from consola_obs.ui import dibujo as mod_ui_dibujo


COLOR_FONDO = "#151a24"
COLOR_HOVER = "#323b4c"
COLOR_BORDE = "#2b3548"
COLOR_SEPARADOR = "#232c3d"
COLOR_TEXTO = "white"
COLOR_TEXTO_APAGADO = "#6f7d99"
ANCHO_MINIMO = 214
ANCHO_MINIMO_FLYOUT = 150
LADO_ICONO = 16
# Animación del flyout: duración total y pausa entre cuadros.
DURACION_FLYOUT_S = 0.16
PAUSA_CUADRO_MS = 12
# Pausa antes de abrir un flyout al pasar el mouse (evita que se abra
# al cruzar la fila de pasada).
RETARDO_ABRIR_FLYOUT_MS = 70

_ESTILO_TK = dict(tearoff=0, bg=COLOR_FONDO, fg="white",
                  activebackground=COLOR_HOVER, activeforeground="white")

# Menú abierto ahora (uno solo a la vez), momento de apertura y si ya
# se enganchó el cierre por clic fuera.
_estado = {"menu": None, "t": 0.0, "bind": False}


# ---------------------------------------------------------------------
# Cierre
# ---------------------------------------------------------------------

def cerrar(*_):
    """Cierra el menú abierto (y su flyout, que cuelga de él)."""
    menu = _estado.get("menu")
    _estado["menu"] = None
    if menu is None:
        return
    menu._cerrado = True
    try:
        menu.popup.destroy()
    except Exception:
        pass


def _clic_fuera(event):
    """Cualquier clic fuera del menú lo cierra. Los primeros 250 ms se
    ignoran: el mismo clic derecho que abrió el menú sigue
    propagándose al toplevel."""
    menu = _estado.get("menu")
    if menu is None:
        return
    if time.monotonic() - _estado.get("t", 0.0) < 0.25:
        return
    try:
        destino = str(event.widget)
        base = str(menu.popup)
        # El flyout es hijo del popup, así que su ruta también empieza
        # con la del popup.
        if destino == base or destino.startswith(base + "."):
            return
    except Exception:
        pass
    cerrar()


# ---------------------------------------------------------------------
# Iconos
# ---------------------------------------------------------------------

def _icono(svg, foto=None):
    """(imagen, es_real). Toda fila lleva imagen (real o transparente):
    así el texto arranca siempre en la misma x y queda alineado. Si el
    icono real no se pudo cargar, es_real=False y la fila usa el texto
    de respaldo (con emoji)."""
    if foto is not None:
        return foto, True
    real = None
    if svg:
        try:
            real = mod_ui_dibujo._imagen_svg_menu(svg, LADO_ICONO)
        except Exception:
            real = None
    if real is not None:
        return real, True
    try:
        return mod_ui_dibujo._imagen_vacia(LADO_ICONO), False
    except Exception:
        return None, False


def _puntero_en(widget, ancla):
    """True si 'widget' (lo que está bajo el puntero) es 'ancla' o un
    descendiente suyo."""
    if widget is None or ancla is None:
        return False
    ruta, base = str(widget), str(ancla)
    return ruta == base or ruta.startswith(base + ".")


# ---------------------------------------------------------------------
# API común (la misma para el popup propio y para el respaldo clásico)
# ---------------------------------------------------------------------

class _Base:
    def flyout_colores(self, svg, texto, respaldo, paleta, actual, al_elegir):
        """Fila 'Color de etiqueta' que despliega a la derecha los
        colores en vertical. al_elegir recibe el color (o None para
        quitar la etiqueta)."""
        self.flyout(svg, texto, respaldo,
                    lambda panel: panel.colores(paleta, actual, al_elegir))


# ---------------------------------------------------------------------
# Popup propio
# ---------------------------------------------------------------------

class _PanelModerno(_Base):
    """Contenido de un popup (el principal o un flyout): filas,
    separadores, colores y bloques de widgets."""

    def __init__(self, popup, cuerpo, raiz):
        self.popup = popup
        self.cuerpo = cuerpo
        self.raiz = raiz
        popup._imagenes = []

    # -- ejecutar -----------------------------------------------------
    def _ejecutar(self, comando):
        # Se cierra primero y el comando corre recién después: muchos
        # abren diálogos modales o reconstruyen la grilla.
        cerrar()
        try:
            E.ventana.after(20, comando)
        except Exception:
            pass

    # -- hover --------------------------------------------------------
    def _pintar(self, info, activo):
        color = COLOR_HOVER if activo else COLOR_FONDO
        try:
            info["frame"].configure(bg=color)
            for h in info["hijos"]:
                h.configure(bg=color)
        except Exception:
            pass

    def _entrar(self, info):
        self._pintar(info, True)

    def _salir(self, info):
        self._pintar(info, False)

    # -- filas --------------------------------------------------------
    def _fila(self, svg, texto, respaldo, comando, deshabilitado, foto,
              flecha, llenar):
        foto_, real = _icono(svg, foto)
        texto_fila = texto if real else (respaldo or texto)
        fila = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        fila.pack(fill="x")
        fg = COLOR_TEXTO_APAGADO if deshabilitado else COLOR_TEXTO
        cursor = "arrow" if deshabilitado else "hand2"
        hijos = []
        if flecha:
            # Primero la flecha (a la derecha): si se empaquetara
            # después de la etiqueta expansiva quedaría sin lugar.
            marca = tk.Label(fila, text="›", bg=COLOR_FONDO, fg=fg,
                             font=(E.FUENTE_UI, 11), padx=10, cursor=cursor)
            marca.pack(side="right")
            hijos.append(marca)
        base = dict(bg=COLOR_FONDO, fg=fg, font=(E.FUENTE_UI, 9), anchor="w",
                    padx=10, pady=5, cursor=cursor)
        if foto_ is None:
            etiqueta = tk.Label(fila, text=texto_fila, **base)
        else:
            self.popup._imagenes.append(foto_)
            etiqueta = tk.Label(fila, text="  " + texto_fila, image=foto_,
                                compound="left", **base)
        etiqueta.pack(side="left", fill="x", expand=True)
        hijos.insert(0, etiqueta)
        info = {"frame": fila, "hijos": hijos, "llenar": llenar}
        if not deshabilitado:
            for w in [fila] + hijos:
                w.bind("<Enter>", lambda e, i=info: self._entrar(i))
                w.bind("<Leave>", lambda e, i=info: self._salir(i))
                if comando is not None:
                    w.bind("<Button-1>", lambda e, c=comando: self._ejecutar(c))
        return info

    def item(self, svg, texto, respaldo=None, comando=None,
             deshabilitado=False, foto=None):
        """Fila clickeable. svg: icono de assets/iconos (o None);
        respaldo: texto con emoji si el icono no carga; foto: imagen ya
        armada (reemplaza al svg)."""
        return self._fila(svg, texto, respaldo, comando, deshabilitado,
                          foto, False, None)

    def flyout(self, svg, texto, respaldo=None, llenar=None, foto=None):
        """Fila con flecha ›: al pasar el mouse se despliega a la
        derecha un panel que llena llenar(panel) con la misma API."""
        return self._fila(svg, texto, respaldo, None, False, foto, True, llenar)

    def separador(self):
        tk.Frame(self.cuerpo, bg=COLOR_SEPARADOR, height=1).pack(fill="x", pady=3)

    def bloque(self, construir):
        """Marco libre para widgets propios (ej. una barra de volumen).
        construir(marco) los arma. Devuelve el marco."""
        marco = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        marco.pack(fill="x", padx=10, pady=(2, 6))
        construir(marco)
        return marco

    # -- colores ------------------------------------------------------
    def colores(self, paleta, actual, al_elegir):
        """'Sin etiqueta' + una barra de color por cada color de la
        paleta, en vertical. El color vigente lleva una tilde."""
        self.item(None, "Sin etiqueta", "Sin etiqueta",
                  lambda: al_elegir(None))
        self.separador()
        for color in paleta:
            if color is None:
                continue
            self._muestra(color, color == actual, al_elegir)
        # un poco de aire abajo
        tk.Frame(self.cuerpo, bg=COLOR_FONDO, height=3).pack(fill="x")

    def _muestra(self, color, vigente, al_elegir):
        marco = tk.Frame(self.cuerpo, bg=COLOR_FONDO, cursor="hand2")
        marco.pack(fill="x", padx=8, pady=1)
        barra = tk.Label(marco, text=("✓" if vigente else ""), bg=color,
                         fg="#0c111b", font=(E.FUENTE_UI, 9, "bold"),
                         width=14, pady=2, cursor="hand2")
        barra.pack(fill="x", padx=2, pady=2)

        def _hover(activo):
            try:
                marco.configure(bg="#e8edf7" if activo else COLOR_FONDO)
            except Exception:
                pass

        for w in (marco, barra):
            w.bind("<Enter>", lambda e: _hover(True))
            w.bind("<Leave>", lambda e: _hover(False))
            w.bind("<Button-1>",
                   lambda e, c=color: self._ejecutar(lambda: al_elegir(c)))


class _Flyout(_PanelModerno):
    """Panel que se despliega a la derecha de una fila del menú."""

    def __init__(self, raiz, info):
        top = tk.Toplevel(raiz.popup)
        top.withdraw()
        top.overrideredirect(True)
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        top.configure(bg=COLOR_BORDE)
        cuerpo = tk.Frame(top, bg=COLOR_FONDO)
        # place: el toplevel se va a ir agrandando de a poco y el
        # cuerpo tiene que conservar su tamaño real (queda recortado).
        cuerpo.place(x=1, y=1)
        # Ancho mínimo para que un flyout corto no quede angosto.
        tk.Frame(cuerpo, width=ANCHO_MINIMO_FLYOUT, height=1,
                 bg=COLOR_FONDO).pack()
        super().__init__(top, cuerpo, raiz)
        self.info = info
        self.gracia = 0
        self._vivo = True

    def _geometria_final(self):
        top, raiz = self.popup, self.raiz
        top.update_idletasks()
        ancho = self.cuerpo.winfo_reqwidth() + 2
        alto = self.cuerpo.winfo_reqheight() + 2
        pantalla_w, pantalla_h = top.winfo_screenwidth(), top.winfo_screenheight()
        padre = raiz.popup
        x = padre.winfo_rootx() + padre.winfo_width() - 2
        if x + ancho > pantalla_w - 4:
            # Sin lugar a la derecha: se abre hacia la izquierda.
            x = padre.winfo_rootx() - ancho + 2
        x = max(0, x)
        y = self.info["frame"].winfo_rooty() - 3
        y = max(0, min(y, pantalla_h - alto - 48))
        return ancho, alto, x, y

    def mostrar(self):
        top = self.popup
        self._w, self._h, self._x, self._y = self._geometria_final()
        top.geometry(f"{self._w}x2+{self._x}+{self._y}")
        try:
            top.attributes("-alpha", 0.0)
        except Exception:
            pass
        top.deiconify()
        top.lift()
        self._t0 = time.monotonic()
        self._animar()

    def _terminar(self):
        try:
            self.popup.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")
            self.popup.attributes("-alpha", 1.0)
        except Exception:
            pass

    def _animar(self):
        """Se abre hacia abajo y aparece (alfa) con desaceleración."""
        if not self._vivo or _estado.get("menu") is not self.raiz:
            return
        try:
            t = (time.monotonic() - self._t0) / DURACION_FLYOUT_S
            if t >= 1.0:
                self._terminar()
                return
            suave = 1.0 - (1.0 - t) ** 3
            alto = max(2, int(self._h * suave))
            self.popup.geometry(f"{self._w}x{alto}+{self._x}+{self._y}")
            try:
                self.popup.attributes("-alpha", suave)
            except Exception:
                pass
            self.popup.after(PAUSA_CUADRO_MS, self._animar)
        except Exception:
            self._terminar()

    def cerrar(self):
        self._vivo = False
        try:
            self.popup.destroy()
        except Exception:
            pass


class MenuModerno(_PanelModerno):
    """Popup principal (Toplevel sin bordes)."""

    def __init__(self, x_root, y_root):
        popup = tk.Toplevel(E.ventana)
        popup.withdraw()
        popup.overrideredirect(True)
        try:
            popup.attributes("-topmost", True)
        except Exception:
            pass
        popup.configure(bg=COLOR_BORDE)
        cuerpo = tk.Frame(popup, bg=COLOR_FONDO)
        cuerpo.pack(padx=1, pady=1)
        # Ancho mínimo parejo para todos los menús.
        tk.Frame(cuerpo, width=ANCHO_MINIMO, height=1, bg=COLOR_FONDO).pack()
        super().__init__(popup, cuerpo, self)
        self._pos = (x_root, y_root)
        self._cerrado = False
        self._flyout = None
        self._pendiente = None
        self._tarea = None

    # -- flyouts ------------------------------------------------------
    def _entrar(self, info):
        self._pintar(info, True)
        if info.get("llenar") is not None:
            self._programar_flyout(info)

    def _salir(self, info):
        # Mientras su flyout está abierto, la fila queda resaltada.
        if self._flyout is not None and self._flyout.info is info:
            return
        self._pintar(info, False)

    def _programar_flyout(self, info):
        if self._pendiente is not None:
            try:
                self.popup.after_cancel(self._pendiente)
            except Exception:
                pass
            self._pendiente = None
        if self._flyout is not None and self._flyout.info is info:
            return
        try:
            self._pendiente = self.popup.after(
                RETARDO_ABRIR_FLYOUT_MS, lambda: self._abrir_flyout(info))
        except Exception:
            pass

    def _abrir_flyout(self, info):
        self._pendiente = None
        if self._cerrado or _estado.get("menu") is not self:
            return
        self._cerrar_flyout()
        flyout = None
        try:
            flyout = _Flyout(self, info)
            info["llenar"](flyout)
            self._flyout = flyout
            self._pintar(info, True)
            flyout.mostrar()
            if self._tarea is not None:
                # Un solo vigilante a la vez.
                try:
                    self.popup.after_cancel(self._tarea)
                except Exception:
                    pass
                self._tarea = None
        except Exception as e:
            print(f"No se pudo abrir el submenú: {e}")
            if flyout is not None:
                flyout.cerrar()
            self._flyout = None
            return
        self._seguir()

    def _cerrar_flyout(self):
        flyout, self._flyout = self._flyout, None
        if flyout is None:
            return
        flyout.cerrar()
        try:
            bajo_el_puntero = self.popup.winfo_containing(
                *self.popup.winfo_pointerxy())
        except Exception:
            bajo_el_puntero = None
        self._pintar(flyout.info, _puntero_en(bajo_el_puntero, flyout.info["frame"]))

    def _seguir(self):
        """Vigila el puntero mientras hay un flyout: se cierra cuando
        el mouse sale de la fila y del flyout (con un margen corto para
        no cerrar por cruzar un borde en diagonal)."""
        if self._cerrado or _estado.get("menu") is not self:
            return
        flyout = self._flyout
        if flyout is None:
            return
        try:
            bajo = self.popup.winfo_containing(*self.popup.winfo_pointerxy())
        except Exception:
            bajo = None
        if _puntero_en(bajo, flyout.popup) or _puntero_en(bajo, flyout.info["frame"]):
            flyout.gracia = 0
        else:
            flyout.gracia += 1
            if flyout.gracia >= 3:
                self._cerrar_flyout()
                return
        try:
            self._tarea = self.popup.after(80, self._seguir)
        except Exception:
            pass

    # -- mostrar ------------------------------------------------------
    def _ubicar(self):
        popup = self.popup
        popup.update_idletasks()
        ancho, alto = popup.winfo_reqwidth(), popup.winfo_reqheight()
        x = max(0, min(self._pos[0], popup.winfo_screenwidth() - ancho - 4))
        y = max(0, min(self._pos[1], popup.winfo_screenheight() - alto - 48))
        popup.geometry(f"+{x}+{y}")

    def mostrar(self):
        popup = self.popup
        self._ubicar()
        _estado["menu"] = self
        _estado["t"] = time.monotonic()
        if not _estado["bind"]:
            # Una sola vez: cualquier clic en la app fuera del menú lo cierra.
            _estado["bind"] = True
            E.ventana.bind_all("<ButtonPress>", _clic_fuera, add="+")
        popup.bind("<Escape>", cerrar)
        popup.deiconify()
        popup.lift()
        try:
            popup.focus_force()
        except Exception:
            pass
        popup.after(800, self._vigilar)

    def _vigilar(self):
        # Si la app entera pierde el foco (alt-tab, clic en otra
        # ventana), el menú se cierra solo: sigue en primer plano y
        # estorbaría.
        if self._cerrado or _estado.get("menu") is not self:
            return
        try:
            if self.popup.focus_displayof() is None:
                cerrar()
                return
        except Exception:
            pass
        try:
            self.popup.after(400, self._vigilar)
        except Exception:
            pass


# ---------------------------------------------------------------------
# Respaldo clásico (tk.Menu): misma API, mismo código de construcción
# ---------------------------------------------------------------------

class _PanelClasico(_Base):
    def __init__(self, menu):
        self.menu = menu
        menu._imagenes = []

    def _opciones(self, svg, texto, respaldo, foto):
        foto_, real = _icono(svg, foto)
        opciones = {"label": texto if real else (respaldo or texto)}
        if foto_ is not None:
            self.menu._imagenes.append(foto_)
            opciones.update(image=foto_, compound="left")
        return opciones

    def item(self, svg, texto, respaldo=None, comando=None,
             deshabilitado=False, foto=None):
        opciones = self._opciones(svg, texto, respaldo, foto)
        opciones["command"] = comando if comando is not None else (lambda: None)
        if deshabilitado:
            opciones["state"] = "disabled"
        self.menu.add_command(**opciones)

    def flyout(self, svg, texto, respaldo=None, llenar=None, foto=None):
        sub = tk.Menu(self.menu, **_ESTILO_TK)
        if llenar is not None:
            llenar(_PanelClasico(sub))
        opciones = self._opciones(svg, texto, respaldo, foto)
        self.menu.add_cascade(menu=sub, **opciones)

    def separador(self):
        self.menu.add_separator()

    def bloque(self, construir):
        # Los widgets propios (barras, etc.) sólo existen en el popup
        # moderno; en el respaldo se omiten.
        return None

    def colores(self, paleta, actual, al_elegir):
        self.menu.add_command(label="Sin etiqueta",
                              command=lambda: al_elegir(None))
        self.menu.add_separator()
        for color in paleta:
            if color is None:
                continue
            self.menu.add_command(
                label="        ", background=color, activebackground=color,
                command=lambda c=color: al_elegir(c))


def _abrir_clasico(x, y, construir):
    menu = tk.Menu(E.ventana, **_ESTILO_TK)
    construir(_PanelClasico(menu))
    try:
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()


# ---------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------

def abrir(event, construir):
    """Abre el menú en la posición del evento. construir(m) arma las
    filas. Devuelve True si salió el popup moderno, False si se usó el
    respaldo clásico."""
    cerrar()
    x, y = event.x_root, event.y_root
    menu = None
    try:
        menu = MenuModerno(x, y)
        construir(menu)
        menu.mostrar()
        return True
    except Exception as e:
        print(f"No se pudo armar el menú moderno: {e}")
        if menu is not None:
            try:
                menu.popup.destroy()
            except Exception:
                pass
        _estado["menu"] = None
    try:
        _abrir_clasico(x, y, construir)
    except Exception as e:
        print(f"No se pudo abrir el menú clásico: {e}")
    return False
