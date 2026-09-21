import os
import tkinter as tk

from tkinter import messagebox, ttk
from tkinter import font as tkfont

from consola_obs import compat
from consola_obs.compat import HAY_PILLOW, Image, ImageOps, ImageTk
from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import plataforma as P
from consola_obs import rutas as R
from consola_obs import configuracion as mod_configuracion
from consola_obs import red as mod_red
from consola_obs import utilidades as mod_utilidades
from consola_obs.obs import cliente as mod_obs_cliente
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.audio import reproduccion as mod_audio_reproduccion
from consola_obs.audio import fuentes as mod_audio_fuentes
from consola_obs.ui import dibujo as mod_ui_dibujo
from consola_obs.ui import medidores as mod_ui_medidores
from consola_obs.ui import tarjeta_fuente as mod_ui_tarjeta
from consola_obs.ui import soundboard as mod_ui_soundboard
from consola_obs.ui import ventana as mod_ui_ventana
from consola_obs.ui import cabecera as mod_ui_cabecera
from consola_obs.compat import HAY_PILLOW


"""
CONSOLA OBS
============
Panel de control para OBS Studio vía OBS WebSocket (v5), con estética de
mixer y botonera de sonidos real: medidores de nivel tipo LED, botones
circulares iluminados, pads de soundboard tipo launchpad, tamaño de
íconos ajustable y paneles que se pueden reacomodar (arriba/abajo,
izquierda/derecha) a gusto del usuario.

Requisitos:
    pip install obsws-python
    pip install pillow      (opcional, mejora las miniaturas del soundboard)

Para convertirlo en ejecutable (Windows):
    pip install pyinstaller
    pyinstaller --onefile --windowed --name ConsolaOBS consola_obs.py

El .exe queda en la carpeta "dist".
"""


def main():


    P._escribir_readme_assets(
        os.path.join(R.CARPETA_ICONOS, "LEEME.txt"),
        "ICONOS DE LA INTERFAZ\n"
        "======================\n"
        "Poné acá:\n"
        "  - app_icon.ico   -> ícono de la ventana/barra de tareas (Windows).\n"
        "  - app_icon.png   -> ícono de la ventana en Mac/Linux.\n"
        "  - logo_cabecera.png -> reemplaza el ícono dibujado de la cabecera.\n"
        "Ninguno es obligatorio: si faltan, el programa usa sus íconos\n"
        "dibujados por defecto y funciona exactamente igual.\n"
    )
    P._escribir_readme_assets(
        os.path.join(R.CARPETA_FONDOS, "LEEME.txt"),
        "FONDOS DE LA INTERFAZ\n"
        "======================\n"
        "Carpeta reservada para futuras imágenes de fondo (por ejemplo,\n"
        "texturas o wallpapers propios). No es necesaria para que el\n"
        "programa funcione: por defecto se usan degradados dibujados por\n"
        "código.\n"
    )
    P._escribir_readme_assets(
        os.path.join(R.CARPETA_FUENTES_TIPOGRAFIA, "LEEME.txt"),
        "TIPOGRAFÍA DE LA INTERFAZ\n"
        "==========================\n"
        "Poné acá cualquier archivo .ttf u .otf para personalizar la\n"
        "tipografía del programa. Por defecto se usa una tipografía moderna\n"
        "del sistema (Segoe UI / Helvetica Neue / Ubuntu, etc.), igual que\n"
        "cualquier programa de audio profesional; si querés que TODO el\n"
        "texto use la tuya en vez de la del sistema, se tiene en cuenta\n"
        "como alternativa. Si hay más de un archivo, se usa el primero (por\n"
        "orden alfabético) que el sistema operativo logre registrar; si no\n"
        "hay ninguno o falla el registro, el programa vuelve solo a elegir\n"
        "la mejor fuente instalada, sin romperse.\n"
    )


    P._registrar_fuentes_personalizadas()



    mod_configuracion.cargar_config_soundboard()
    E.config_previa = mod_configuracion.cargar_config_conexion()
    # La playlist actual arranca vacía en cada inicio: lo que sonaba
    # ayer no se reanuda solo (ni suena nada "por defecto").
    try:
        _cfg_mus = mod_configuracion.cargar_config_musica()
        if _cfg_mus.get("playlist"):
            _cfg_mus["playlist"] = []
            mod_configuracion.guardar_config_musica(_cfg_mus)
    except Exception:
        pass
    E.config_interfaz_previa = mod_configuracion.cargar_config_interfaz()

    E.tamano_icono_actual = E.config_interfaz_previa.get("tamano_icono", C.TAMANO_ICONO_POR_DEFECTO)
    if E.tamano_icono_actual not in C.TAMANOS_ICONO:
        E.tamano_icono_actual = C.TAMANO_ICONO_POR_DEFECTO

    E.alto_tarjeta_actual = E.config_interfaz_previa.get("alto_tarjeta", C.ALTO_TARJETA_POR_DEFECTO)
    if E.alto_tarjeta_actual not in C.ALTOS_TARJETA:
        E.alto_tarjeta_actual = C.ALTO_TARJETA_POR_DEFECTO

    E.tema_interfaz = E.config_interfaz_previa.get("tema_interfaz", "Profesional")
    if E.tema_interfaz not in E.TEMAS_INTERFAZ:
        E.tema_interfaz = "Profesional"

    E.orientacion_paneles = E.config_interfaz_previa.get("orientacion_paneles", "vertical")
    if E.orientacion_paneles not in ("vertical", "horizontal"):
        E.orientacion_paneles = "vertical"

    E.orden_paneles = E.config_interfaz_previa.get("orden_paneles", ["fuentes", "soundboard"])
    if not isinstance(E.orden_paneles, list) or set(E.orden_paneles) != {"fuentes", "soundboard"}:
        E.orden_paneles = ["fuentes", "soundboard"]

    E._principales_guardadas = E.config_interfaz_previa.get("fuentes_principales", [])
    if isinstance(E._principales_guardadas, list):
        E.fuentes_principales = set(E._principales_guardadas)

    E._colores_guardados = E.config_interfaz_previa.get("colores_fuentes", {})
    if isinstance(E._colores_guardados, dict):
        E.colores_fuentes = dict(E._colores_guardados)

    E._orden_guardado = E.config_interfaz_previa.get("orden_fuentes", [])
    if isinstance(E._orden_guardado, list):
        E.orden_fuentes = [n for n in E._orden_guardado if isinstance(n, str)]

    E.num_pads_soundboard = E.config_interfaz_previa.get("num_pads_soundboard", C.NUM_BOTONES_SOUNDBOARD_INICIAL)
    if not isinstance(E.num_pads_soundboard, int) or E.num_pads_soundboard < 1:
        E.num_pads_soundboard = C.NUM_BOTONES_SOUNDBOARD_INICIAL
    if E.config_soundboard:
        E.indices_guardados = [int(k) for k in E.config_soundboard.keys() if k.isdigit()]
        if E.indices_guardados:
            E.num_pads_soundboard = max(E.num_pads_soundboard, max(E.indices_guardados) + 1)

    E.ventana = tk.Tk()
    E.ventana.title("Consola OBS — Panel de Audio Profesional")

    # Ahora que el proceso es consciente del DPI (ver el bloque del
    # principio del archivo), Tk nos entrega la pantalla a resolución
    # nativa: si no le avisamos, dibujaría todo del tamaño que tendría a 96
    # ppp y la interfaz se vería diminuta en un monitor escalado. Este
    # 'tk scaling' le dice cuántos píxeles reales vale un punto tipográfico,
    # así los textos salen del tamaño correcto Y nítidos (rasterizados a la
    # resolución de verdad), en vez de chicos o agrandados por el sistema.
    try:
        E._ppp_pantalla = E.ventana.winfo_fpixels("1i")
        if E._ppp_pantalla > 0:
            E.ventana.tk.call("tk", "scaling", max(1.0, min(2.5, E._ppp_pantalla / 72.0)))
    except Exception:
        pass

    E._familias_disponibles = set(tkfont.families())
    # Para el look "consola de audio profesional" se priorizan las fuentes
    # modernas del sistema (Segoe UI, etc.): son las que usan los programas
    # de audio de verdad y las que mejor se ven en tamaños chicos. Las
    # tipografías propias (.ttf/.otf puestas en assets/fuentes) siguen
    # registrándose y funcionando igual que antes, sólo que ahora quedan
    # como alternativas de respaldo después de las del sistema. La
    # funcionalidad (conexión, audio, configuración) no cambia en nada.
    E._PREFERENCIAS_FUENTE_UI = [
        "Segoe UI", "Helvetica Neue", "SF Pro Display", "Ubuntu",
        "Noto Sans", "Roboto", "Arial", "Helvetica",
    ] + E._NOMBRES_FUENTES_PERSONALIZADAS
    E._PREFERENCIAS_FUENTE_TITULO = [
        "Segoe UI Semibold", "Segoe UI", "Helvetica Neue Medium",
        "Helvetica Neue", "Ubuntu Medium", "Noto Sans Medium", "Arial",
    ] + E._NOMBRES_FUENTES_PERSONALIZADAS
    E.FUENTE_UI = next((f for f in E._PREFERENCIAS_FUENTE_UI if f in E._familias_disponibles), "TkDefaultFont")
    E.FUENTE_TITULO = next((f for f in E._PREFERENCIAS_FUENTE_TITULO if f in E._familias_disponibles), E.FUENTE_UI)
    E.FUENTE_ICONOS = next((f for f in ("Segoe UI Symbol", "Noto Sans Symbols 2", "Arial Unicode MS", E.FUENTE_UI) if f in E._familias_disponibles), E.FUENTE_UI)
    E.FUENTE_EMOJI = next((f for f in ("Segoe UI Emoji", "Noto Color Emoji", "Noto Emoji", E.FUENTE_UI) if f in E._familias_disponibles), E.FUENTE_UI)
    # Si el usuario ya había elegido una tipografía en el menú de
    # ajustes, se aplica por encima de la detección automática. Sin
    # elección guardada se usa "Tipografia de obs" (Open Sans, la de
    # OBS) si está disponible.
    _fuente_guardada = E.config_interfaz_previa.get("fuente_ui", "")
    if not _fuente_guardada and mod_ui_ventana._resolver_familia_tipografia("Tipografia de obs"):
        _fuente_guardada = "Tipografia de obs"
    mod_ui_ventana.aplicar_fuente_elegida(_fuente_guardada, guardar=False)
    # Salida de audio local (parlantes de la PC) en paralelo a OBS.
    E.escuchar_en_pc = E.config_interfaz_previa.get("escuchar_en_pc", True)
    if not isinstance(E.escuchar_en_pc, bool):
        E.escuchar_en_pc = str(E.escuchar_en_pc).lower() in ("1", "true", "sí", "si")
    # Nivelación de efectos (todos los pads al mismo volumen).
    E.nivelar_efectos = E.config_interfaz_previa.get("nivelar_efectos", True)
    if not isinstance(E.nivelar_efectos, bool):
        E.nivelar_efectos = str(E.nivelar_efectos).lower() in ("1", "true", "sí", "si")

    try:
        E._ico = os.path.join(R.CARPETA_ICONOS, "app_icon.ico")
        E._png = os.path.join(R.CARPETA_ICONOS, "app_icon.png")
        if os.path.exists(E._ico):
            E.ventana.iconbitmap(E._ico)
        elif os.path.exists(E._png) and HAY_PILLOW:
            _foto_icono_ventana = ImageTk.PhotoImage(Image.open(E._png))
            E.ventana.iconphoto(True, _foto_icono_ventana)
    except Exception:
        pass

    E._estilo_scrollbar = ttk.Style()
    try:
        E._estilo_scrollbar.theme_use("clam")                                                         
    except Exception:
        pass
    for E._orientacion in ("Vertical", "Horizontal"):
        E._estilo_scrollbar.configure(
            f"Discreta.{E._orientacion}.TScrollbar",
            background="#394151", troughcolor="#10161f", bordercolor="#10161f",
            arrowcolor="#394151", relief="flat", arrowsize=10,
        )
        E._estilo_scrollbar.map(
            f"Discreta.{E._orientacion}.TScrollbar",
            background=[("active", "#3f4a5e")]
        )

    E._estilo_scrollbar.configure(
        "Discreta.TCombobox",
        fieldbackground="#283040", background="#283040", foreground="white",
        arrowcolor="#566070", bordercolor="#394151", lightcolor="#283040",
        darkcolor="#283040", relief="flat", padding=4,
    )
    E._estilo_scrollbar.map(
        "Discreta.TCombobox",
        fieldbackground=[("readonly", "#283040")],
        foreground=[("readonly", "white")],
        bordercolor=[("focus", "#566070")],
    )
    E.ventana.option_add("*TCombobox*Listbox.background", "#202633")
    E.ventana.option_add("*TCombobox*Listbox.foreground", "white")
    E.ventana.option_add("*TCombobox*Listbox.selectBackground", "#566070")
    E.ventana.option_add("*TCombobox*Listbox.font", (E.FUENTE_UI, 9))

    E.ventana.geometry(E.config_interfaz_previa.get("geometria_ventana", "1300x760"))
    E.ventana.minsize(900, 520)
    E.ventana.configure(bg="#10141b")
    E.ventana.resizable(True, True)                                           

    E.ventana.update_idletasks()

    # Cambia, una sola vez, el pincel con el que Windows borra el fondo de
    # la ventana (ver _fijar_color_fondo_nativo más arriba en el archivo)
    # para que coincida con este mismo color: así, hasta el propio borrado
    # que hace Windows por su cuenta al agrandar la ventana ya sale del
    # color correcto, sin flash claro de por medio. No hace nada en Mac/
    # Linux (ver la versión de la función para esos sistemas).
    P._fijar_color_fondo_nativo("#10141b")

    # ------------------------------------------------------------------
    # VELO DE REDIMENSIONADO
    # ------------------------------------------------------------------
    # Antes, para tapar el reacomodo de los paneles al cambiar el tamaño
    # de la ventana, se hacía invisible la VENTANA ENTERA con
    # ventana.attributes("-alpha", 0.0)/1.0. El problema es que esto
    # depende de que el gestor de ventanas del sistema operativo soporte
    # bien la transparencia en tiempo real MIENTRAS la ventana se está
    # redimensionando activamente (dos cosas pasando a la vez: cambio de
    # tamaño + cambio de opacidad), y en varios sistemas eso es
    # justamente lo que producía el corte/glitch visual: el compositor no
    # llega a dibujar un cuadro completo y consistente.
    #
    # El siguiente reemplazo fue un Frame opaco liso (un simple rectángulo
    # del color de fondo) tapando toda la ventana durante el arrastre. Eso
    # evitaba ver los paneles a medio armar, pero el propio rectángulo liso
    # apareciendo y desapareciendo en cada racha de arrastre SE VEÍA, a su
    # vez, como un parpadeo: la interfaz "desaparecía" (tapada) y volvía a
    # "aparecer" de golpe al soltar.
    #
    # La versión actual, en cambio, no tapa con un color liso: le saca una
    # "foto" (con Pillow) a cómo se ve la ventana apenas termina cada
    # reconstrucción, y esa foto es lo que se muestra en el velo la
    # PRÓXIMA vez que arranca un arrastre, escalada en vivo al tamaño que
    # va teniendo la ventana en cada evento. Para el ojo, es la propia
    # interfaz "estirándose" con la ventana (igual que la vista previa de
    # redimensionado nativa de Windows/macOS), aunque en realidad esté
    # congelada y sea sólo una imagen; los widgets de verdad no se tocan
    # hasta que el usuario suelta y la ventana se queda quieta, momento en
    # que se reconstruye todo de una sola vez y se destapa la foto. Si
    # Pillow o su captura de pantalla (ImageGrab) no están disponibles
    # —por ejemplo, en algunas instalaciones de Linux—, se cae de nuevo al
    # rectángulo liso de antes: sigue sin verse nada a medio construir,
    # sólo que sin el efecto de foto en vivo.
    E.velo_redimension = tk.Label(E.ventana, bg="#10141b", bd=0, highlightthickness=0)

    E._captura_ventana = {"imagen_pil": None}   # última foto buena de la interfaz completa
    E._foto_velo = {"tk": None}                   # referencia viva de la imagen actualmente mostrada en el velo


    E.ventana.bind("<Configure>", mod_ui_ventana._al_redimensionar_ventana)


    E.ventana.protocol("WM_DELETE_WINDOW", mod_ui_ventana.al_cerrar)



    C.ALTO_CABECERA = 80
    C.COLOR_CABECERA_ARRIBA = E.color_cabecera_arriba()
    C.COLOR_CABECERA_ABAJO = E.color_cabecera_abajo()

    E.cabecera_fondo = tk.Canvas(E.ventana, height=C.ALTO_CABECERA, bg=C.COLOR_CABECERA_ARRIBA, highlightthickness=0)
    E.cabecera_fondo.pack(fill="x")

    E.cabecera = tk.Frame(E.cabecera_fondo, bg=C.COLOR_CABECERA_ARRIBA)

    E._imagen_logo_cabecera = {"foto": None}

    E._trabajo_redibujado_cabecera = {"id": None}


    E._ventana_cabecera_id = E.cabecera_fondo.create_window(0, 0, window=E.cabecera, anchor="nw")
    E.cabecera_fondo.bind("<Configure>", mod_ui_cabecera._redibujar_cabecera)


    E.marco_icono_cabecera = tk.Canvas(E.cabecera, width=48, height=48, bg=C.COLOR_CABECERA_ARRIBA, highlightthickness=0)
    E.marco_icono_cabecera.pack(side="left", padx=(20, 12), pady=16)

    E._ruta_logo_cabecera = os.path.join(R.CARPETA_ICONOS, "logo_cabecera.png")
    mod_ui_cabecera.repintar_logo_cabecera()

    E.marco_titulos_cabecera = tk.Frame(E.cabecera, bg=C.COLOR_CABECERA_ARRIBA)
    E.marco_titulos_cabecera.pack(side="left", pady=10)

    E.titulo = tk.Label(
        E.marco_titulos_cabecera, text="CONSOLA OBS", bg=C.COLOR_CABECERA_ARRIBA, fg="white",
        font=(E.FUENTE_TITULO, 19, "bold"), anchor="w"
    )
    E.titulo.pack(anchor="w")

    E.subtitulo = tk.Label(
        E.marco_titulos_cabecera, text="Panel de control de audio para OBS Studio",
        bg=C.COLOR_CABECERA_ARRIBA, fg="#828da6", font=(E.FUENTE_UI, 9), anchor="w"
    )
    E.subtitulo.pack(anchor="w")

    E.marco_engranaje = tk.Canvas(E.cabecera, width=52, height=52, bg=C.COLOR_CABECERA_ARRIBA, highlightthickness=0, cursor="hand2")
    E.marco_engranaje.pack(side="right", padx=(0, 18), pady=14)
    E._imagen_engranaje = {"foto": None}


    E._cache_engranajes = {}


    E._estado_engranaje = {"hover": False, "abierto": False}


    E.marco_engranaje.bind("<Configure>", mod_ui_cabecera._redibujar_icono_engranaje)
    E.marco_engranaje.bind("<Button-1>", lambda e: mod_ui_cabecera._alternar_menu_ajustes(e))


    E.marco_engranaje.bind("<Enter>", mod_ui_cabecera._hover_engranaje_dentro)
    E.marco_engranaje.bind("<Leave>", mod_ui_cabecera._hover_engranaje_fuera)
    E.boton_engranaje = E.marco_engranaje

    E.estado_chip = tk.Frame(E.cabecera, bg="#141a26", highlightbackground="#3d4657", highlightthickness=1)
    E.estado_chip.pack(side="right", padx=20, pady=20)

    E.estado = tk.Label(
        E.estado_chip, text="● DESCONECTADO", bg="#141a26", fg="#ff5d6c",
        font=(E.FUENTE_UI, 10, "bold"), padx=14, pady=6
    )
    E.estado.pack()



    # ------------------------------------------------------------------
    # MENÚ DESPLEGABLE DE AJUSTES
    # ------------------------------------------------------------------
    # Antes todo esto era una BARRA fija cruzando la ventana: host, puerto,
    # contraseña, botones y selectores siempre a la vista, robando alto útil
    # a los faders y a los pads. Ahora es un panel que cuelga del botón de
    # engranaje, organizado en secciones (Conexión / Apariencia) en vertical
    # -como el menú de ajustes de cualquier programa moderno-, y que se
    # cierra solo al hacer clic en cualquier otro lado, al apretar Escape o
    # al mover la ventana.
    C.ANCHO_MENU_AJUSTES = 340
    C.COLOR_MENU_FONDO = "#121722"
    C.COLOR_MENU_BORDE = "#2b3548"
    C.COLOR_MENU_CAMPO = "#1b2230"
    C.COLOR_MENU_TITULO = "#6f7d99"
    C.COLOR_MENU_TEXTO = "#c3cee5"

    E.ventana_ajustes = tk.Toplevel(E.ventana, bg=C.COLOR_MENU_BORDE)
    E.ventana_ajustes.overrideredirect(True)
    E.ventana_ajustes.withdraw()
    try:
        E.ventana_ajustes.attributes("-topmost", True)
    except Exception:
        pass

    # El borde del menú es el propio Toplevel asomando 1px alrededor del
    # marco interior: es la forma simple de tener un contorno prolijo en una
    # ventana sin decoración.
    E.barra = tk.Frame(E.ventana_ajustes, bg=C.COLOR_MENU_FONDO)
    E.barra.pack(fill="both", expand=True, padx=1, pady=1)

    E._encabezado_menu = tk.Frame(E.barra, bg=C.COLOR_MENU_FONDO)
    E._encabezado_menu.pack(fill="x", padx=16, pady=(14, 8))

    tk.Label(
        E._encabezado_menu, text="AJUSTES", bg=C.COLOR_MENU_FONDO, fg="white",
        font=(E.FUENTE_TITULO, 12, "bold")
    ).pack(side="left")

    E._cerrar_menu = tk.Label(
        E._encabezado_menu, text="✕", bg=C.COLOR_MENU_FONDO, fg="#6f7d99",
        font=(E.FUENTE_UI, 11, "bold"), cursor="hand2"
    )
    E._cerrar_menu.pack(side="right")
    E._cerrar_menu.bind("<Button-1>", lambda e: mod_ui_cabecera._cerrar_menu_ajustes())
    E._cerrar_menu.bind("<Enter>", lambda e: E._cerrar_menu.config(fg="#ff5d6c"))
    E._cerrar_menu.bind("<Leave>", lambda e: E._cerrar_menu.config(fg="#6f7d99"))


    mod_ui_cabecera._seccion_menu("CONEXIÓN")

    E.entrada_host = mod_ui_cabecera._entrada_menu(mod_ui_cabecera._fila_menu("Host"))
    E.entrada_host.insert(0, E.config_previa.get("host", "localhost"))

    E.entrada_puerto = mod_ui_cabecera._entrada_menu(mod_ui_cabecera._fila_menu("Puerto"))
    E.entrada_puerto.insert(0, E.config_previa.get("puerto", "4455"))

    E.entrada_password = mod_ui_cabecera._entrada_menu(mod_ui_cabecera._fila_menu("Contraseña"), show="•")
    E.entrada_password.insert(0, E.config_previa.get("password", ""))

    # Carpeta assets del lado del OBS (Fase 2 música): solo importa si
    # el OBS está en OTRA pc. No se puede explorar el disco remoto,
    # así que se escribe/pega a mano UNA vez y queda guardada (ej:
    # D:\ConsolaOBS\assets). En la misma PC se ignora.
    E.entrada_base_obs = mod_ui_cabecera._entrada_menu(mod_ui_cabecera._fila_menu("Carpeta OBS"))
    E.entrada_base_obs.insert(0, E.config_interfaz_previa.get("carpeta_base_obs", ""))
    E._etiqueta_base_obs = tk.Label(
        E.barra,
        text="Ruta de assets\\ en la PC del OBS (solo si el OBS está en otra PC)",
        bg=C.COLOR_MENU_FONDO, fg="#8fa0bd", font=(E.FUENTE_UI, 8),
        wraplength=300, justify="left",
    )
    E._etiqueta_base_obs.pack(fill="x", padx=16, pady=(0, 2))

    # IP LAN automática: para que otra PC se conecte A ESTA, tiene que
    # poner ESTA ip como Host. Se detecta sola, sin tener que hacer
    # ipconfig a mano. No cambia la conexión actual: solo informa.
    try:
        _ip_auto = mod_red.obtener_ip_local()
    except Exception:
        _ip_auto = ""
    E._etiqueta_ip_local = tk.Label(
        E.barra,
        text=(f"IP de esta PC: {_ip_auto}  (la otra PC pone esto en Host)" if _ip_auto
              else "IP de esta PC: no detectada (revisá tu WiFi/red)"),
        bg=C.COLOR_MENU_FONDO, fg="#8fa0bd", font=(E.FUENTE_UI, 8),
        wraplength=300, justify="left",
    )
    E._etiqueta_ip_local.pack(fill="x", padx=16, pady=(6, 0))

    E._fila_red = tk.Frame(E.barra, bg=C.COLOR_MENU_FONDO)
    E._fila_red.pack(fill="x", padx=16, pady=(6, 0))
    E.boton_ip_local = tk.Button(
        E._fila_red, text="📋 COPIAR MI IP", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=mod_obs_cliente.copiar_ip_local
    )
    E.boton_ip_local.pack(side="left", fill="x", expand=True, padx=(0, 4))
    E.boton_firewall = tk.Button(
        E._fila_red, text="🛡 FIREWALL", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=5, font=(E.FUENTE_UI, 8, "bold"), cursor="hand2",
        command=mod_obs_cliente.abrir_firewall_ahora
    )
    E.boton_firewall.pack(side="left", fill="x", expand=True, padx=(4, 0))

    E._fila_acciones = tk.Frame(E.barra, bg=C.COLOR_MENU_FONDO)
    E._fila_acciones.pack(fill="x", padx=16, pady=(12, 4))

    E.boton_conectar = tk.Button(
        E._fila_acciones, text="CONECTAR", bg=E.color_acento(), fg="#0c111b",
        activebackground=E.color_acento_claro(), activeforeground="#0c111b",
        relief="flat", bd=0, pady=7, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=mod_obs_cliente.conectar_obs
    )
    E.boton_conectar.pack(side="left", fill="x", expand=True)

    E.boton_actualizar = tk.Button(
        E.barra, text="ACTUALIZAR FUENTES", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=7, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=mod_ui_tarjeta.actualizar
    )
    E.boton_actualizar.pack(fill="x", padx=16, pady=(6, 2))

    # Fase 3 del plan: crear una fuente de audio nueva sin ir a OBS.
    E.boton_agregar_fuente = tk.Button(
        E.barra, text="+  AGREGAR FUENTE", bg="#242d3d", fg=C.COLOR_MENU_TEXTO,
        activebackground="#2f3a4d", activeforeground="white",
        relief="flat", bd=0, pady=7, font=(E.FUENTE_UI, 9, "bold"), cursor="hand2",
        command=mod_audio_fuentes.abrir_selector_nueva_fuente
    )
    E.boton_agregar_fuente.pack(fill="x", padx=16, pady=(4, 2))

    mod_ui_cabecera._seccion_menu("APARIENCIA")

    E.variable_tamano_icono = tk.StringVar(value=E.tamano_icono_actual)
    E.selector_tamano_icono = ttk.Combobox(
        mod_ui_cabecera._fila_menu("Íconos"),
        textvariable=E.variable_tamano_icono,
        values=list(C.TAMANOS_ICONO.keys()),
        state="readonly",
        style="Discreta.TCombobox"
    )
    E.selector_tamano_icono.pack(side="left", fill="x", expand=True)
    E.selector_tamano_icono.bind(
        "<<ComboboxSelected>>",
        lambda e: mod_ui_ventana.cambiar_tamano_icono(E.variable_tamano_icono.get())
    )

    E.variable_alto_tarjeta = tk.StringVar(value=E.alto_tarjeta_actual)
    E.selector_alto_tarjeta = ttk.Combobox(
        mod_ui_cabecera._fila_menu("Alto"),
        textvariable=E.variable_alto_tarjeta,
        values=list(C.ALTOS_TARJETA.keys()),
        state="readonly",
        style="Discreta.TCombobox"
    )
    E.selector_alto_tarjeta.pack(side="left", fill="x", expand=True)
    E.selector_alto_tarjeta.bind(
        "<<ComboboxSelected>>",
        lambda e: mod_ui_ventana.cambiar_alto_tarjeta(E.variable_alto_tarjeta.get())
    )

    E.variable_diseno = tk.StringVar(value=mod_ui_ventana._nombre_diseno_actual())
    E.selector_diseno = ttk.Combobox(
        mod_ui_cabecera._fila_menu("Diseño"),
        textvariable=E.variable_diseno,
        values=list(E.DISENOS.keys()),
        state="readonly",
        style="Discreta.TCombobox"
    )
    E.selector_diseno.pack(side="left", fill="x", expand=True)
    E.selector_diseno.bind(
        "<<ComboboxSelected>>",
        lambda e: mod_ui_ventana.cambiar_diseno(E.variable_diseno.get())
    )

    E.variable_fuente = tk.StringVar(
        value=E.fuente_elegida or mod_ui_ventana.FUENTE_PREDETERMINADA)
    E.selector_fuente = ttk.Combobox(
        mod_ui_cabecera._fila_menu("Tipografía"),
        textvariable=E.variable_fuente,
        values=mod_ui_ventana._fuentes_tipografia_disponibles(),
        state="readonly",
        style="Discreta.TCombobox"
    )
    E.selector_fuente.pack(side="left", fill="x", expand=True)
    E.selector_fuente.bind(
        "<<ComboboxSelected>>",
        lambda e: mod_ui_ventana.cambiar_fuente(E.variable_fuente.get())
    )

    E.variable_tema = tk.StringVar(value=E.tema_interfaz)
    E.selector_tema = ttk.Combobox(
        mod_ui_cabecera._fila_menu("Interfaz"),
        textvariable=E.variable_tema,
        values=list(E.TEMAS_INTERFAZ),
        state="readonly",
        style="Discreta.TCombobox"
    )
    E.selector_tema.pack(side="left", fill="x", expand=True)
    E.selector_tema.bind(
        "<<ComboboxSelected>>",
        lambda e: mod_ui_ventana.cambiar_tema_interfaz(E.variable_tema.get())
    )

    mod_ui_cabecera._seccion_menu("AUDIO")

    E.variable_escuchar = tk.StringVar(value="Sí" if E.escuchar_en_pc else "No")
    E.selector_escuchar = ttk.Combobox(
        mod_ui_cabecera._fila_menu("Escuchar acá"),
        textvariable=E.variable_escuchar,
        values=["Sí", "No"],
        state="readonly",
        style="Discreta.TCombobox"
    )
    E.selector_escuchar.pack(side="left", fill="x", expand=True)
    E.selector_escuchar.bind(
        "<<ComboboxSelected>>",
        lambda e: mod_audio_reproduccion.cambiar_escuchar_en_pc(E.variable_escuchar.get())
    )

    E.variable_nivelar = tk.StringVar(value="Sí" if E.nivelar_efectos else "No")
    E.selector_nivelar = ttk.Combobox(
        mod_ui_cabecera._fila_menu("Nivelar efectos"),
        textvariable=E.variable_nivelar,
        values=["Sí", "No"],
        state="readonly",
        style="Discreta.TCombobox"
    )
    E.selector_nivelar.pack(side="left", fill="x", expand=True)
    E.selector_nivelar.bind(
        "<<ComboboxSelected>>",
        lambda e: mod_audio_reproduccion.cambiar_nivelar_efectos(E.variable_nivelar.get())
    )

    tk.Frame(E.barra, bg=C.COLOR_MENU_FONDO, height=14).pack(fill="x")


    E.ventana.bind("<Button-1>", mod_ui_cabecera._clic_fuera_del_menu, add="+")
    E.ventana.bind("<Escape>", mod_ui_cabecera._cerrar_menu_ajustes, add="+")
    E.ventana_ajustes.bind("<Escape>", mod_ui_cabecera._cerrar_menu_ajustes)


    E.ventana.bind("<Configure>", mod_ui_cabecera._seguir_ventana_con_menu, add="+")
    E.ventana.bind("<B1-Motion>", mod_ui_ventana._mover_divisor, add="+")
    E.ventana.bind("<ButtonRelease-1>", mod_ui_ventana._soltar_divisor, add="+")
    E.ventana.bind("<ButtonRelease-1>", mod_ui_ventana._soltar_boton_termina_resize, add="+")


    mod_ui_ventana.construir_cuerpo()
    # Los audios nuevos de la carpeta Sondidos_pad se convierten en pads
    # solos al arrancar (los que ya tienen pad no se tocan).
    mod_ui_soundboard.detectar_sonidos_carpeta(avisar=False)
    mod_ui_medidores.actualizar_vu_meters_ui()
    mod_obs_eventos._programar_refresco_ganancia()
    mod_audio_reproduccion._programar_refresco_reproduccion()
    E.ventana.after(500, mod_ui_soundboard._refrescar_barra_progreso)
    if not P._ES_WINDOWS:
        # Foto inicial de la interfaz recién armada (sólo hace falta en el
        # respaldo de Mac/Linux; en Windows el congelado nativo no usa
        # ninguna foto), para que si el usuario redimensiona la ventana
        # como primer gesto el velo ya tenga una imagen real para mostrar,
        # en vez de arrancar en blanco la primera vez.
        E.ventana.after(200, mod_ui_ventana._capturar_snapshot_ventana)

    if not HAY_PILLOW:
        E.ventana.after(500, lambda: messagebox.showwarning(
            "Falta instalar Pillow",
            "No se encontró (ni se pudo instalar automáticamente) el paquete "
            "'Pillow', necesario para que las imágenes de los pads funcionen "
            "bien.\n\nSin Pillow, los archivos JPG no se pueden mostrar y "
            "ninguna imagen se va a achicar al tamaño del pad.\n\n"
            "Instalalo manualmente abriendo una terminal y ejecutando:\n"
            "pip install Pillow\n\nDespués volvé a abrir el programa."
        ))
    E.ventana.mainloop()
