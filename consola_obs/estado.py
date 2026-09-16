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
    "#e53935",   # rojo
    "#fb8c00",   # naranja
    "#fdd835",   # amarillo
    "#43a047",   # verde
    "#00acc1",   # turquesa/cian
    "#1e88e5",   # azul
    "#5e35b1",   # índigo
    "#8e24aa",   # violeta
    "#e91e63",   # rosa/magenta
]



conectado = False
cliente_obs = None                                                                    
cliente_eventos = None                                              

_lock_pedidos_obs = threading.Lock()

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

# Interfaz visual: "Profesional" (la de siempre) o "Moderna" (estilo
# OBS). Sólo cambia lo visual; la funcionalidad es la misma.
TEMAS_INTERFAZ = ("Profesional", "Moderna")
tema_interfaz = "Profesional"


def es_moderna():
    return tema_interfaz == "Moderna"


# Ajustes de la barra Moderna (Ajustes → Apariencia).
DEGRADADOS_BARRA = ("Nulo", "Sutil", "Suave")
COLORES_BARRA = ("Verde", "Azul", "Naranja", "Violeta")
mod_degradado = "Sutil"
mod_color_barra = "Verde"


def color_fondo_panel():
    """Fondo de paneles según el tema (más oscuro en Moderna)."""
    return C.MOD_FONDO if es_moderna() else "#10141b"


def color_barra_titulo():
    """Barra de títulos de panel según el tema."""
    return C.MOD_CABECERA if es_moderna() else "#151a24"


def color_cabecera_arriba():
    """Fondo superior de la barra principal (gris oscuro en Moderna)."""
    return "#2b2b2b" if es_moderna() else "#1c2637"


def color_cabecera_abajo():
    """Fondo inferior de la barra principal (gris oscuro en Moderna)."""
    return "#1c1c1c" if es_moderna() else "#0c111b"


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
escena_actual_nombres = set()                                                          
escena_actual_obtenida = False                                                            

_dialogo_filtros_abierto = {"nombre": None, "refrescar": None, "ventana": None}

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


_celdas_pads = {}
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
_sesion_reproduccion = {"indice": None, "token": 0, "inicio": 0.0}


_trabajo_redimension_soundboard = {"id": None}


# INTERVALO_VU_MS, CAIDA_DB_POR_SEG, CAIDA_POR_CUADRO,
# UMBRAL_DATOS_VIEJOS_SEG y DEBUG_VU_FUENTE ahora están todos juntos en
# la "SECCIÓN DE CALIBRACIÓN DEL MEDIDOR DE VOLUMEN", cerca del
# principio del archivo, junto con el resto de los parámetros del
# medidor.
_ultimo_debug_vu = {"t": 0.0}
