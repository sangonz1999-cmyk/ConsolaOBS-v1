import threading

from consola_obs import constantes as C


# ------------------------------------------------------------------
# CARGA DE TIPOGRAFÍA PROPIA (.ttf / .otf) DESDE assets/fuentes
# ------------------------------------------------------------------
# Tk no sabe cargar un archivo de fuente por su cuenta: sólo puede usar
# fuentes que el sistema operativo ya tiene registradas. Así que para
# poder pedirle a Tk una tipografía que vino en un .ttf/.otf propio,
# primero hay que registrársela al sistema operativo -sólo para este
# proceso, sin "instalarla" de forma permanente en la máquina del
# usuario- y recién ahí Tk la puede ver y usar como una familia más.
# Cada sistema operativo lo hace distinto (ver las tres funciones de
# registro más abajo); si algo falla en el camino -el archivo está
# corrupto, el sistema no da permiso, etc.- simplemente no se agrega
# ninguna fuente propia y el programa sigue funcionando con la mejor
# fuente del sistema, como hacía antes.
_NOMBRES_FUENTES_PERSONALIZADAS = []  # familias registradas con éxito, en orden

DISENOS = {
    "Fuentes arriba":    ("vertical",   ["fuentes", "soundboard"]),
    "Fuentes abajo":     ("vertical",   ["soundboard", "fuentes"]),
    "Fuentes izquierda": ("horizontal", ["fuentes", "soundboard"]),
    "Fuentes derecha":   ("horizontal", ["soundboard", "fuentes"]),
}
TAMANO_MINIATURA = (150, 70)
UMBRAL_SILENCIO = -60.0
CAIDA_POR_CUADRO = C.CAIDA_DB_POR_SEG * (C.INTERVALO_VU_MS / 1000.0)

TIPOS_MONITOREO = [
    "OBS_MONITORING_TYPE_NONE",
    "OBS_MONITORING_TYPE_MONITOR_ONLY",
    "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT",
]

PALETA_ETIQUETAS = [
    None,
    "#ff3b30",   # rojo (saturado)
    "#ff9500",   # naranja (saturado)
    "#ffd600",   # amarillo (saturado)
    "#00e676",   # verde (saturado)
    "#00e5ff",   # turquesa/cian (saturado)
    "#2979ff",   # azul (saturado)
    "#651fff",   # índigo (saturado)
    "#d500f9",   # violeta (saturado)
    "#ff1744",   # rosa/magenta (saturado)
]



conectado = False
cliente_obs = None                                                                    
cliente_eventos = None                                              

_lock_pedidos_obs = threading.Lock()

# Host al que se está conectado ahora (tal cual se escribió en
# Ajustes → Host, None si desconectado). La capa de rutas lo usa
# para decidir si manda rutas directas (misma PC) o traducidas a la
# base del OBS (otra PC), sin depender de widgets.
host_conectado = None

_lock_sincronizar_escenas = threading.Lock()

fuentes = {}                                                          
niveles_actuales = {}                                                                             
# Igual que 'niveles_entrada' de acá abajo (el nivel "de entrada" que
# sigue llegando en vivo con la fuente muteada), pero SIN recortarlo a
# 1.0. Se usa sólo para la reconstrucción del nivel de una fuente
# muteada en actualizar_vu_meters_ui: recortar a 1.0 ANTES de
# multiplicar por la ganancia del fader le pone un techo artificial al
# resultado (nunca puede superar la posición del fader), lo que hace
# que el medidor deje de reaccionar al audio real en cualquier fuente
# cuyo filtro de Ganancia empuje la señal por encima de 0dB -algo
# habitual en audio de escritorio-. Ver el comentario completo en
# actualizar_vu_meters_ui.
niveles_crudos = {}
niveles_entrada = {}                                                                                       
niveles_antes_mute = {}
ultima_actualizacion_nivel = {}                                                              
# Momento (time.monotonic) de la última vez que cada fuente saturó (0 dB
# o más). Se guarda por separado del nivel normal porque el nivel normal
# ya llega recortado a 1.0 (ver on_input_volume_meters) y esa
# información se perdería; el LED en rojo total se sostiene un ratito
# después de ese instante (ver DURACION_SATURACION_SEG) para que se
# note aunque el pico haya sido muy corto, igual que el indicador de
# clipping de OBS.
ultima_vez_saturado = {}
# Ganancia extra (en dB) que están aplicando ahora mismo los filtros de
# audio de cada fuente (ver CAMPOS_GANANCIA_FILTRO), sumada entre todos
# los filtros de ese tipo que estén HABILITADOS. Se usa para que el
# medidor de nivel reaccione a esos filtros -sobre todo al de
# "Ganancia"- y para poder marcar saturación en rojo cuando la
# ganancia agregada es alta, aunque la señal de entrada sea floja.
ganancia_filtros_db = {}

config_soundboard = {}
miniaturas_cargadas = {}
# Caché de las imágenes YA DECODIFICADAS (abiertas con Pillow, con el
# exif_transpose y la conversión de modo ya aplicados), separado del
# caché de miniaturas de arriba. La apertura + decodificación de un
# archivo de imagen (sobre todo fotos grandes, de celular o 4K) es la
# parte cara de mostrar un pad; una vez decodificada una vez, achicarla
# a distintos tamaños de pad es prácticamente gratis. Sin este caché,
# cada reconstrucción de la interfaz (por ejemplo, al redimensionar la
# ventana) volvía a leer y decodificar TODAS las imágenes de TODOS los
# pads desde cero, porque el tamaño de pad cambia con la ventana y el
# caché de miniaturas usa el tamaño exacto como parte de la clave — eso
# era lo que tildaba el programa.
_imagenes_decodificadas_cache = {}

tamano_icono_actual = C.TAMANO_ICONO_POR_DEFECTO
alto_tarjeta_actual = C.ALTO_TARJETA_POR_DEFECTO

# Interfaz visual: "Profesional" (la de siempre) o "Moderna" (estilo
# OBS). Sólo cambia lo visual; la funcionalidad es la misma.
TEMAS_INTERFAZ = ("Profesional", "Moderna")
tema_interfaz = "Profesional"


def es_moderna():
    return tema_interfaz == "Moderna"


def color_fondo_panel():
    """Fondo de paneles según el tema (más oscuro en Moderna)."""
    return C.MOD_FONDO if es_moderna() else "#10141b"


def color_barra_titulo():
    """Barra de títulos de panel según el tema."""
    return C.MOD_CABECERA if es_moderna() else "#151a24"


def color_cabecera_arriba():
    """Fondo superior de la barra principal (gris azulado en Moderna)."""
    return "#2f3a4e" if es_moderna() else "#1c2637"


def color_cabecera_abajo():
    """Fondo inferior de la barra principal (gris azulado en Moderna)."""
    return "#222b3a" if es_moderna() else "#0c111b"


def color_acento():
    """Acento principal: verde de siempre, azul en Moderna."""
    return C.MOD_ACENTO if es_moderna() else "#2fd693"


def color_acento_oscuro():
    return C.MOD_ACENTO_OSCURO if es_moderna() else "#17b8b0"


def color_acento_claro():
    return C.MOD_ACENTO_CLARO if es_moderna() else "#4fe3ae"

orientacion_paneles = "vertical"                                             
orden_paneles = ["fuentes", "soundboard"]                          

cuerpo = None                                                                    
columnas_soundboard = 4                                                  

num_pads_soundboard = C.NUM_BOTONES_SOUNDBOARD_INICIAL                          

orden_fuentes = []                                                                    
columnas_fuentes = 1                                                                               

fuentes_principales = set()
colores_fuentes = {}
_kinds_sin_audio = set()
_kinds_con_audio = set()
fuentes_ocultas = set()
orden_fuentes_criterios = []
mostrar_ocultas = True
# Escenas donde Efectos/Música PUEDEN estar (lista blanca): en las
# demás no se crea nada nunca, ni siquiera al aire. Vacía = no se crea
# en ninguna (cierra por defecto: lo olvidado queda a salvo solo).
escenas_permitidas = set()
# Estado previo al ocultar (Fase 3): por fuente oculta, {"muted": bool,
# "monitor": str} tal como estaba antes de ocultarla. Vive en memoria y
# se persiste en config_interfaz.json ("fuentes_ocultas_previo") para
# que desocultar después de un reinicio también restaure.
_estado_previo_oculta = {}
escena_actual_nombres = set()
escena_actual_obtenida = False
orden_escena_actual = []
# Colección de escenas activa en OBS (dato vivo, se lee al conectar y
# ante cada cambio: al cambiar de colección cambian TODAS las escenas y
# TODAS las fuentes, así que dispara un refresco completo).
coleccion_actual = ""

_dialogo_filtros_abierto = {"nombre": None, "refrescar": None, "ventana": None}

# Igual que _dialogo_filtros_abierto, pero para la ventana de
# "Propiedades" de una fuente (Fase 2 del plan de mejoras): sólo puede
# haber una abierta a la vez, y se cierra sola si se desconecta OBS o
# si se abren unas Propiedades nuevas mientras ésta seguía abierta.
_dialogo_propiedades_abierto = {"nombre": None, "ventana": None}

_panel_en_arrastre = {"origen": None}

# Caché de placas ya renderizadas. La clave incluye tamaño, color y
# estado, así que mover el mouse por encima de los pads (o reconstruir
# la grilla) no vuelve a pagar el costo del render con Pillow.
_cache_placas = {}
MARCAS_DB = [0, -10, -20, -30, -40, -50, -60]


_ultimo_ancho_celda_fuentes = {"valor": None}
_ultima_grilla_fuentes = {"clave": None}
_ultimas_columnas_pads = {"valor": None}
# Modo super-optimizador: mientras se está redimensionando (borde de la
# ventana, divisor o grillas) se pausa lo secundario (pintado de LEDs y
# degradados) para darle todo el hilo al layout. Se apaga SÓLO al soltar
# el botón del mouse (o si la vigilancia detecta que ya no está
# presionado): quedarse quieto con el botón agarrado nunca lo apaga.
_modo_super = {"activo": False, "timer": None, "origen": None}


_trabajo_redimension_fuentes = {"id": None}
# Último tamaño visto del canvas de fuentes: si un <Configure> no
# cambia el tamaño (scrollbars, contenido), se reacomoda barato en
# vivo; si cambia (resize real), se congela y se difiere al asentado.
_ultimo_tamano_canvas_fuentes = {"valor": None}

_arrastre_fuente = {
    "nombre": None, "arrastrando": False,
    "x_inicio": 0, "y_inicio": 0, "destino_resaltado": None,
}



# Filtros que le sirven a un sonidista para controlar audio: sólo estos
# se ofrecen al "Agregar filtro" (nada de croma, máscaras, LUTs, etc.,
# que son de video y no pintan en una consola de sonido). Cada entrada
# es (nombre a mostrar, ícono, lista de "kind" técnicos posibles que
# puede usar OBS para ese mismo filtro según la versión -algunos
# filtros cambiaron de implementación interna en versiones nuevas de
# OBS, manteniendo el mismo nombre visible-, en orden de preferencia).
# El nombre y el orden calcan el menú "+" de filtros de audio de OBS.
FILTROS_DE_SONIDO_PERMITIDOS = [
    ("Compresor",                    "🗜", ["compressor_filter"]),
    ("Compresor ascendente",         "📊", ["upward_compressor_filter"]),
    # El identificador real que usa OBS para este filtro es
    # "basic_eq_filter" (no "eq_filter": ese nombre lo usa sólo la
    # variable interna del código fuente de OBS, pero el "kind" que
    # informa OBS-WebSocket -y el que hay que usar para crearlo y para
    # reconocer sus ajustes- es "basic_eq_filter"). Se deja "eq_filter"
    # como alternativa por si alguna versión vieja de OBS lo reportara
    # con ese otro nombre.
    ("Ecualizador de 3 bandas",      "🎛", ["basic_eq_filter", "eq_filter"]),
    ("Eliminación de ruido",         "🔇", ["noise_suppress_filter_v2", "noise_suppress_filter"]),
    ("Expansor",                     "📈", ["expander_filter"]),
    ("Extensión VST 2.x",            "🔌", ["vst_filter"]),
    ("Ganancia",                     "🎚", ["gain_filter"]),
    ("Invertir polaridad",           "🔃", ["invert_polarity_filter"]),
    ("Limitador",                    "🚧", ["limiter_filter"]),
    ("Puerta anti-ruidos",           "🚪", ["noise_gate_filter"]),
    ("Retardo de Video (asíncrono)", "⏱", ["async_delay_filter"]),
]


# ------------------------------------------------------------------
# CATÁLOGO DE TIPOS DE ENTRADA para "Agregar fuente" (Fase 3 del plan)
# ------------------------------------------------------------------
# Mismo formato y misma idea que FILTROS_DE_SONIDO_PERMITIDOS: nombre
# entendible, ícono, y la lista de "kinds" posibles que puede informar
# OBS para ese mismo tipo de fuente. Se prueba en orden y se usa el
# primero que esta instancia de OBS realmente tenga registrado (lo que
# devuelve GetInputKindList), así el mismo catálogo sirve en Windows
# (WASAPI), macOS (CoreAudio) y Linux (PulseAudio) sin tocar nada.
#
# Sólo están los tipos que le sirven a un sonidista. Los nombres y el
# orden son los mismos que muestra el menú "Agregar fuente" de OBS en
# español (alfabético), para que quien ya conoce OBS encuentre lo mismo
# acá. Los demás tipos que informe OBS (captura de ventana, navegador,
# texto, imagen, etc.) igual se pueden crear desde el selector completo,
# tildando "Mostrar todos los tipos que informa OBS".
ENTRADAS_DE_AUDIO_PERMITIDAS = [
    ("Captura de audio de aplicación (BETA)", "windowaudio.svg",
     ["wasapi_process_output_capture"]),
    ("Captura de entrada audio", "microphone.svg",
     ["wasapi_input_capture", "coreaudio_input_capture", "pulse_input_capture",
      "pipewire_audio_input_capture", "jack_input_capture"]),
    ("Captura de salida de audio", "windowaudio.svg",
     ["wasapi_output_capture", "coreaudio_output_capture", "pulse_output_capture",
      "pipewire_audio_output_capture", "jack_output_capture"]),
    ("Multimedia", "media.svg",
     ["ffmpeg_source"]),
]

# Nombre por defecto que se sugiere al crear una fuente de cada tipo:
# es el mismo texto amigable del catálogo, así que no hace falta una
# tabla aparte. Para un kind que NO esté en el catálogo (modo "mostrar
# todos"), se sugiere el propio kind.
ICONO_ENTRADA_DESCONOCIDA = "default.svg"

# SVG original de OBS por input kind (pack obs_pack/imagenes): se usan
# en el submenú "Agregar fuente" y en el selector completo. Lo que no
# está acá cae en default.svg.
SVG_POR_INPUT_KIND = {
    "wasapi_input_capture": "microphone.svg",
    "coreaudio_input_capture": "microphone.svg",
    "pulse_input_capture": "microphone.svg",
    "pipewire_audio_input_capture": "microphone.svg",
    "jack_input_capture": "microphone.svg",
    "wasapi_output_capture": "windowaudio.svg",
    "coreaudio_output_capture": "windowaudio.svg",
    "pulse_output_capture": "windowaudio.svg",
    "pipewire_audio_output_capture": "windowaudio.svg",
    "jack_output_capture": "windowaudio.svg",
    "wasapi_process_output_capture": "windowaudio.svg",
    "ffmpeg_source": "media.svg",
    "window_capture": "window.svg",
    "game_capture": "gamepad.svg",
    "dshow_input": "camera.svg",
    "v4l2_input": "camera.svg",
    "browser_source": "globe.svg",
    "text_ft2_source": "text.svg",
    "text_gdiplus": "text.svg",
    "text_gdiplus_v2": "text.svg",
    "image_source": "image.svg",
    "slideshow": "slideshow.svg",
    "color_source": "brush.svg",
    "color_source_v2": "brush.svg",
    "color_source_v3": "brush.svg",
    "scene": "scene.svg",
    "group": "group.svg",
}


# ESQUEMA de los filtros de sonido "importantes" (los mismos que
# ofrece FILTROS_DE_SONIDO_PERMITIDOS): acá se calcan, campo por
# campo, los mismos nombres de ajuste ("threshold", "ratio",
# "attack_time", etc.), los mismos rangos y los mismos valores por
# defecto que usa el código fuente real de OBS para el Limitador
# (limiter-filter.c), el Compresor (compressor-filter.c), la Ganancia
# (gain-filter.c) y el Ecualizador de 3 bandas (eq-filter.c).
#
# Por qué hace falta esto y no alcanza con "leer los ajustes y armar
# una barra para cada uno" (que es lo que hace el editor genérico más
# abajo): OBS sólo guarda en el filtro los valores que se tocaron
# alguna vez a mano. Un filtro recién agregado (o uno al que nunca le
# tocaste, por ejemplo, el "Ataque") todavía no tiene ese valor
# guardado -aunque el motor de audio SÍ esté usando el valor por
# defecto internamente-, así que OBS-WebSocket devuelve para ese
# filtro un diccionario vacío o incompleto. Si sólo se dibujara una
# barra por cada clave que vino en la respuesta, el Limitador o el
# Compresor recién creados aparecerían "sin ajustes editables" (o con
# la mitad de los controles faltantes), que es justo el síntoma de
# "no funciona". Wiraendo cada filtro con su esquema fijo, el editor
# siempre muestra el juego completo de controles, con el valor real de
# OBS si ya está guardado, o si no, el mismo valor por defecto que
# OBS le está aplicando igual.
ESQUEMA_FILTROS_CONOCIDOS = {
    "gain_filter": [
        dict(clave="db", etiqueta="Ganancia", tipo="float",
             minimo=-30.0, maximo=30.0, paso=0.1, sufijo=" dB", defecto=0.0),
    ],
    "limiter_filter": [
        dict(clave="threshold", etiqueta="Umbral", tipo="float",
             minimo=-60.0, maximo=0.0, paso=0.1, sufijo=" dB", defecto=-6.0),
        dict(clave="release_time", etiqueta="Liberar", tipo="int",
             minimo=1, maximo=1000, paso=1, sufijo=" ms", defecto=60),
    ],
    "compressor_filter": [
        dict(clave="ratio", etiqueta="Relación", tipo="float",
             minimo=1.0, maximo=32.0, paso=0.5, sufijo=":1", defecto=10.0),
        dict(clave="threshold", etiqueta="Umbral", tipo="float",
             minimo=-60.0, maximo=0.0, paso=0.1, sufijo=" dB", defecto=-18.0),
        dict(clave="attack_time", etiqueta="Ataque", tipo="int",
             minimo=1, maximo=500, paso=1, sufijo=" ms", defecto=6),
        dict(clave="release_time", etiqueta="Liberar", tipo="int",
             minimo=1, maximo=1000, paso=1, sufijo=" ms", defecto=60),
        dict(clave="output_gain", etiqueta="Ganancia de salida", tipo="float",
             minimo=-32.0, maximo=32.0, paso=0.1, sufijo=" dB", defecto=0.0),
        dict(clave="sidechain_source", etiqueta="Fuente de atenuación/reducción",
             tipo="lista", defecto="none"),
    ],
    # "basic_eq_filter" es el kind real que usa OBS para el "Ecualizador
    # de 3 bandas"; se deja "eq_filter" también con el mismo esquema
    # por si alguna versión vieja lo reportara con ese otro nombre (ver
    # el comentario en FILTROS_DE_SONIDO_PERMITIDOS).
    "basic_eq_filter": [
        dict(clave="high", etiqueta="Alto", tipo="float",
             minimo=-20.0, maximo=20.0, paso=0.1, sufijo=" dB", defecto=0.0),
        dict(clave="mid", etiqueta="Medio", tipo="float",
             minimo=-20.0, maximo=20.0, paso=0.1, sufijo=" dB", defecto=0.0),
        dict(clave="low", etiqueta="Bajos", tipo="float",
             minimo=-20.0, maximo=20.0, paso=0.1, sufijo=" dB", defecto=0.0),
    ],
    # Puerta anti-ruidos (noise_gate_filter): claves, rangos y valores
    # por defecto calcados de noise-gate-filter.c (VOL_MIN/VOL_MAX
    # -96..0 dB para los dos umbrales; los tres tiempos van de 0 a
    # 10000 ms en el propio OBS).
    "noise_gate_filter": [
        dict(clave="close_threshold", etiqueta="Umbral de clausura", tipo="float",
             minimo=-96.0, maximo=0.0, paso=1.0, sufijo=" dB", defecto=-32.0),
        dict(clave="open_threshold", etiqueta="Umbral de apertura", tipo="float",
             minimo=-96.0, maximo=0.0, paso=1.0, sufijo=" dB", defecto=-26.0),
        dict(clave="attack_time", etiqueta="Tiempo de Ataque", tipo="int",
             minimo=0, maximo=10000, paso=1, sufijo=" ms", defecto=25),
        dict(clave="hold_time", etiqueta="Tiempo de espera", tipo="int",
             minimo=0, maximo=10000, paso=1, sufijo=" ms", defecto=200),
        dict(clave="release_time", etiqueta="Tiempo de liberación", tipo="int",
             minimo=0, maximo=10000, paso=1, sufijo=" ms", defecto=150),
    ],
    # Compresor ascendente (upward_compressor_filter): mismo archivo
    # fuente que el Expansor (expander-filter.c), pero con su propio
    # rango de Relación (0.0 a 1.0, es la fracción de "levante" hacia
    # arriba) y su propio campo extra "Amplitud de curva" (knee_width)
    # que el Expansor no tiene.
    "upward_compressor_filter": [
        dict(clave="ratio", etiqueta="Relación", tipo="float",
             minimo=0.0, maximo=1.0, paso=0.05, sufijo=":1", defecto=0.5),
        dict(clave="threshold", etiqueta="Umbral", tipo="float",
             minimo=-60.0, maximo=0.0, paso=0.1, sufijo=" dB", defecto=-20.0),
        dict(clave="attack_time", etiqueta="Ataque", tipo="int",
             minimo=1, maximo=100, paso=1, sufijo=" ms", defecto=10),
        dict(clave="release_time", etiqueta="Liberar", tipo="int",
             minimo=1, maximo=1000, paso=1, sufijo=" ms", defecto=50),
        dict(clave="output_gain", etiqueta="Ganancia de salida", tipo="float",
             minimo=-32.0, maximo=32.0, paso=0.1, sufijo=" dB", defecto=0.0),
        dict(clave="knee_width", etiqueta="Amplitud de curva", tipo="int",
             minimo=0, maximo=20, paso=1, sufijo=" dB", defecto=10),
    ],
    # Expansor (expander_filter): a diferencia de lo que se había
    # supuesto en el plan original, este filtro NO tiene fuente de
    # sidechain en OBS (eso es exclusivo del Compresor); en cambio
    # trae un selector de Preajuste (Expansor/Puerta -que reinicia el
    # resto de los valores a los que trae cada preajuste, igual que en
    # OBS-) y un Detector (RMS/Pico).
    "expander_filter": [
        dict(clave="presets", etiqueta="Preajuste", tipo="lista", defecto="expander",
             opciones=[("Expansor", "expander"), ("Puerta (gate)", "gate")]),
        dict(clave="ratio", etiqueta="Relación", tipo="float",
             minimo=1.0, maximo=20.0, paso=0.1, sufijo=":1", defecto=2.0),
        dict(clave="threshold", etiqueta="Umbral", tipo="float",
             minimo=-60.0, maximo=0.0, paso=0.1, sufijo=" dB", defecto=-40.0),
        dict(clave="attack_time", etiqueta="Ataque", tipo="int",
             minimo=1, maximo=100, paso=1, sufijo=" ms", defecto=10),
        dict(clave="release_time", etiqueta="Liberar", tipo="int",
             minimo=1, maximo=1000, paso=1, sufijo=" ms", defecto=50),
        dict(clave="output_gain", etiqueta="Ganancia de salida", tipo="float",
             minimo=-32.0, maximo=32.0, paso=0.1, sufijo=" dB", defecto=0.0),
        dict(clave="detector", etiqueta="Detector", tipo="lista", defecto="RMS",
             opciones=[("RMS", "RMS"), ("Pico (Peak)", "peak")]),
    ],
    # Eliminación de ruido (noise_suppress_filter_v2): el control de
    # "Nivel de supresión" sólo se usa con el método Speex -con
    # RNNoise, OBS directamente lo oculta, porque RNNoise no tiene ese
    # ajuste-, así que acá también se esconde salvo que el método
    # elegido sea "speex" (ver 'visible_si').
    "noise_suppress_filter_v2": [
        dict(clave="method", etiqueta="Método", tipo="lista", defecto="rnnoise",
             opciones=[("Speex", "speex"), ("RNNoise", "rnnoise")]),
        dict(clave="suppress_level", etiqueta="Nivel de supresión", tipo="int",
             minimo=-60, maximo=0, paso=1, sufijo=" dB", defecto=-30,
             visible_si=("method", "speex")),
    ],
    # Retardo de Video/asíncrono (async_delay_filter): un único campo,
    # el tiempo de retardo en ms (0 a 20000, igual que en OBS).
    "async_delay_filter": [
        dict(clave="delay_ms", etiqueta="Tiempo de retardo", tipo="int",
             minimo=0, maximo=20000, paso=1, sufijo=" ms", defecto=0),
    ],
    # Extensión VST 2.x: sólo se replica el selector de plugin
    # (ruta al archivo del VST), tal como se acordó en el plan -los
    # controles internos del plugin en sí no los expone OBS-WebSocket-.
    "vst_filter": [
        dict(clave="plugin_path", etiqueta="Plugin VST", tipo="archivo", defecto=""),
    ],
}
ESQUEMA_FILTROS_CONOCIDOS["eq_filter"] = ESQUEMA_FILTROS_CONOCIDOS["basic_eq_filter"]


# Rangos "de catálogo" para los campos numéricos de filtros que NO
# están en ESQUEMA_FILTROS_CONOCIDOS (croma, VST de terceros, etc.):
# para esos se sigue usando el editor genérico de siempre, adivinando
# un rango razonable por el nombre del campo. Se busca por
# coincidencia de texto dentro del nombre del campo (por ejemplo "db"
# coincide con "gain_db", "threshold_db", etc.), así que no hace falta
# cubrir cada nombre exacto de cada filtro.
RANGOS_CAMPOS_FILTRO = [
    ("ratio", (1, 32)),
    ("output_gain", (-32, 32)),
    ("makeup_gain", (0, 30)),
    ("gain", (-30, 30)),
    ("db", (-60, 30)),
    ("threshold", (-96, 0)),
    ("attack_time", (1, 500)),
    ("release_time", (1, 1000)),
    ("hold_time", (1, 1000)),
    ("sync_offset", (-950, 20000)),
    ("opacity", (0, 100)),
    ("contrast", (-100, 100)),
    ("brightness", (-100, 100)),
    ("gamma", (-100, 100)),
    ("saturation", (-100, 100)),
    ("similarity", (0, 1000)),
    ("smoothness", (0, 1000)),
    ("spill", (0, 1000)),
]


# ------------------------------------------------------------------
# ESQUEMA de "Propiedades" por tipo de fuente (Fase 2 del plan de
# mejoras): igual idea que ESQUEMA_FILTROS_CONOCIDOS de más arriba,
# pero para los AJUSTES DE LA FUENTE en sí (los que en OBS aparecen al
# hacer clic derecho > Propiedades), no los de un filtro.
#
# A diferencia de los filtros -donde OBS-WebSocket sólo devuelve un
# diccionario plano de valores, sin ningún dato de tipo/rango/opciones-,
# acá pasa exactamente lo mismo: GetInputSettings también devuelve sólo
# valores planos. Por eso el mismo criterio de "calcar a mano, campo por
# campo, lo que trae el código fuente de OBS" que ya se usó para los
# filtros se repite acá para los tipos de entrada de AUDIO que le
# importan a un sonidista: micrófono/línea (WASAPI de entrada), audio de
# escritorio (WASAPI de salida), audio de una aplicación puntual
# (WASAPI de captura de proceso, Windows 10 1809+) y Fuente de medios
# (para reproducir un archivo o una URL). Cualquier otro tipo de fuente
# (Captura de ventana, Navegador, Fuente de color, un dshow/decklink de
# video, etc.) no tiene entrada acá y cae en el editor genérico -mismo
# criterio que un filtro sin esquema: una fila por cada ajuste que haya
# devuelto OBS, adivinando un control razonable según el tipo de dato-.
#
# Los campos tipo "lista_dinamica" son la diferencia importante con el
# esquema de filtros: el dispositivo de audio o la ventana a capturar
# son distintos en cada PC, así que sus opciones NO se pueden fijar acá
# a mano -se piden en vivo a OBS con GetInputPropertiesListPropertyItems
# apenas se abre la ventana, tal como pide el punto 2.2 del plan-.
#
# IMPORTANTE (ver punto 2.4 del plan): estos son los campos y rangos que
# trae el código fuente de OBS (win-wasapi, media-source), pero todavía
# no se compararon contra capturas de pantalla reales de "Propiedades"
# tomadas en el setup real -como sí se hizo, filtro por filtro, en la
# Fase 1-. Antes de dar esto por "calcado exacto", conviene revisar cada
# tipo de entrada que se use de verdad contra su ventana real de OBS,
# igual que se hizo con los filtros.
_ESQUEMA_DISPOSITIVO_WASAPI = [
    dict(clave="device_id", etiqueta="Dispositivo", tipo="lista_dinamica", defecto="default"),
    dict(clave="use_device_timing", etiqueta="Usar temporización de dispositivo",
         tipo="bool", defecto=False),
]

ESQUEMA_PROPIEDADES_ENTRADA = {
    # Mic/Aux (captura de entrada de audio) y Audio de escritorio
    # (captura de salida de audio): mismos dos campos en OBS, sólo
    # cambia si se listan dispositivos de grabación o de reproducción
    # -esa parte la resuelve OBS solo al pedirle la lista de items a
    # ESTA fuente puntual-.
    "wasapi_input_capture": _ESQUEMA_DISPOSITIVO_WASAPI,
    "wasapi_output_capture": _ESQUEMA_DISPOSITIVO_WASAPI,
    # Equivalentes de macOS y Linux: mismo campo de dispositivo, sin
    # "Usar temporización de dispositivo" (eso es una particularidad
    # de WASAPI/Windows, no existe en CoreAudio ni en PulseAudio).
    "coreaudio_input_capture": [
        dict(clave="device_id", etiqueta="Dispositivo", tipo="lista_dinamica", defecto="default"),
    ],
    "coreaudio_output_capture": [
        dict(clave="device_id", etiqueta="Dispositivo", tipo="lista_dinamica", defecto="default"),
    ],
    "pulse_input_capture": [
        dict(clave="device_id", etiqueta="Dispositivo", tipo="lista_dinamica", defecto="default"),
    ],
    "pulse_output_capture": [
        dict(clave="device_id", etiqueta="Dispositivo", tipo="lista_dinamica", defecto="default"),
    ],
    # Captura de audio de aplicación (WASAPI, Windows 10 1809+): elegís
    # una ventana de la aplicación (no un dispositivo) y OBS captura el
    # audio de ESE proceso. "Coincidir ventana usando" es el mismo
    # criterio de Título/Clase/Ejecutable que usa la Captura de ventana
    # -el valor por defecto puesto acá (Ejecutable) es una suposición
    # razonable, a confirmar contra la ventana real de OBS (ver punto
    # 2.4 del plan): si esta fuente ya tiene un valor guardado, o si
    # GetInputDefaultSettings informa uno, ese pisa a este de todas
    # formas.
    "wasapi_process_output_capture": [
        dict(clave="window", etiqueta="Ventana", tipo="lista_dinamica", defecto=""),
        dict(clave="priority", etiqueta="Coincidir ventana usando", tipo="lista",
             opciones=[("Título", 0), ("Clase", 1), ("Ejecutable", 2)], defecto=2),
    ],
    # Fuente de medios (ffmpeg_source): calcado campo por campo contra
    # la ventana real de OBS en español -mismo orden y mismas etiquetas-:
    # Archivo local, archivo, Bucle, Reiniciar..., Decodificación por
    # hardware, No mostrar nada..., Cerrar archivo..., Velocidad. El
    # Buffer y los campos de red (URL/formato/retraso) sólo existen en
    # OBS en modo red, así que se ocultan con archivo local.
    "ffmpeg_source": [
        dict(clave="is_local_file", etiqueta="Archivo local", tipo="bool", defecto=True),
        dict(clave="local_file", etiqueta="Archivo local", tipo="archivo", defecto="",
             visible_si=("is_local_file", True)),
        dict(clave="input", etiqueta="Entrada (URL)", tipo="texto", defecto="",
             visible_si=("is_local_file", False)),
        dict(clave="input_format", etiqueta="Formato de entrada", tipo="texto", defecto="",
             visible_si=("is_local_file", False)),
        dict(clave="reconnect_delay_sec", etiqueta="Retraso de reconexión", tipo="int",
             minimo=1, maximo=60, paso=1, sufijo=" s", defecto=10,
             visible_si=("is_local_file", False)),
        dict(clave="buffering_mb", etiqueta="Buffer", tipo="int",
             minimo=0, maximo=16, paso=1, sufijo=" MB", defecto=2,
             visible_si=("is_local_file", False)),
        dict(clave="looping", etiqueta="Bucle", tipo="bool", defecto=False),
        dict(clave="restart_on_activate", etiqueta="Reiniciar la reproducción cuando la fuente esté activa",
             tipo="bool", defecto=True),
        dict(clave="hw_decode", etiqueta="Utilizar la decodificación por hardware cuando esté disponible",
             tipo="bool", defecto=False),
        dict(clave="clear_on_media_end", etiqueta="No mostrar nada al terminar la reproducción",
             tipo="bool", defecto=True),
        dict(clave="close_when_inactive", etiqueta="Cerrar archivo cuando esté inactivo",
             tipo="bool", defecto=False),
        dict(clave="speed_percent", etiqueta="Velocidad", tipo="int",
             minimo=1, maximo=200, paso=1, sufijo="%", defecto=100),
    ],
    # Captura de ventana (win-capture/window-capture.c). Calcado contra
    # la ventana real de OBS en el setup del sonidista: mismo orden de
    # campos, mismas etiquetas y mismas opciones de cada desplegable.
    #
    # Los valores numéricos de "method" y "priority" NO son un rango a
    # deslizar -por eso antes salían como barras en el editor genérico-,
    # son enumeraciones del código de OBS:
    #   method   -> 0 Automático | 1 BitBlt | 2 Windows Graphics Capture
    #   priority -> 0 Título | 1 Clase | 2 Ejecutable
    # (las etiquetas largas de "priority" son las mismas que muestra OBS
    # en español: describen a qué se cae si el título ya no coincide).
    #
    # La visibilidad también se copia de OBS: con BitBlt sólo tiene
    # sentido "Compatibilidad multiadaptador", y "Captura de audio",
    # "Área del cliente" y "Forzar SDR" son exclusivos de Windows
    # Graphics Capture. Con "Automático" OBS resuelve a WGC en Windows
    # 10/11, así que se muestran los campos de WGC -que es justo lo que
    # se ve en la captura de referencia-.
    "window_capture": [
        dict(clave="window", etiqueta="Ventana", tipo="lista_dinamica", defecto=""),
        dict(clave="method", etiqueta="Método de captura", tipo="lista", defecto=0,
             opciones=[
                 ("Automático", 0),
                 ("BitBlt (Windows 7 y posterior)", 1),
                 ("Captura de gráficos de Windows (Windows 10 1903 y posterior)", 2),
             ]),
        dict(clave="priority", etiqueta="Prioridad de captura de ventana", tipo="lista", defecto=2,
             opciones=[
                 ("El título de la ventana debe coincidir", 0),
                 ("Coincidir con el título, de lo contrario buscar ventana del mismo tipo", 1),
                 ("Coincidir con el título, de lo contrario buscar ventana del mismo ejecutable", 2),
             ]),
        dict(clave="capture_audio", etiqueta="Captura de audio (BETA)", tipo="bool", defecto=False,
             visible_si=("method", (0, 2))),
        dict(clave="cursor", etiqueta="Captura de Cursor", tipo="bool", defecto=True),
        dict(clave="compatibility", etiqueta="Compatibilidad multiadaptador",
             tipo="bool", defecto=False, visible_si=("method", (1,))),
        dict(clave="client_area", etiqueta="Área del cliente", tipo="bool", defecto=True,
             visible_si=("method", (0, 2))),
        dict(clave="force_sdr", etiqueta="Forzar SDR", tipo="bool", defecto=False,
             visible_si=("method", (0, 2))),
    ],
}


_celdas_pads = {}
# Por cada pad, (canvas, caja_cara) para pintar el overlay de progreso
# de reproducción (ver _refrescar_barra_progreso en soundboard.py).
_canvas_pads = {}
# Overlay vigente de la barra de progreso (None si no hay).
_overlay_progreso = None
# Por cada pad, una función sin argumentos que vuelve a pintar su
# placa con el estado actual (mouse encima, presionado, y si está
# sonando de verdad). construir_soundboard() la llena de nuevo cada
# vez que reconstruye la grilla; el resto del programa la usa para
# poder prender/apagar el brillo de un pad puntual desde afuera (por
# ejemplo, cuando el chequeo periódico del estado de OBS detecta que
# un efecto terminó).
_refrescos_pads = {}
_arrastre_pad = {
    "indice": None, "arrastrando": False,
    "x_inicio": 0, "y_inicio": 0, "destino_resaltado": None,
}

# ------------------------------------------------------------------
# ESTADO DE REPRODUCCIÓN DEL SOUNDBOARD
# ------------------------------------------------------------------
# Como todos los pads comparten UNA sola fuente de OBS ("Soundboard_
# Efectos"), en un momento dado sólo puede estar sonando un pad a la
# vez. "indice" guarda cuál es (o None si no hay nada sonando), y
# "token" es un número que se incrementa cada vez que arranca una
# reproducción nueva -incluyendo un reinicio del mismo pad-. Un
# fundido en curso se fija en qué token nació: si ese token dejó de
# ser el vigente (porque se disparó otra reproducción mientras
# fundía), el fundido se cancela solo sin frenar el sonido nuevo.
_sesion_reproduccion = {"indice": None, "token": 0, "inicio": 0.0, "deteniendo": False, "duracion": None}


_trabajo_redimension_soundboard = {"id": None}


# INTERVALO_VU_MS, CAIDA_DB_POR_SEG, CAIDA_POR_CUADRO,
# UMBRAL_DATOS_VIEJOS_SEG y DEBUG_VU_FUENTE ahora están todos juntos en
# la "SECCIÓN DE CALIBRACIÓN DEL MEDIDOR DE VOLUMEN", cerca del
# principio del archivo, junto con el resto de los parámetros del
# medidor.
_ultimo_debug_vu = {"t": 0.0}
