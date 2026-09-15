TAMANOS_ICONO = {
    "Chico": {
        "diametro_boton": 22, "fuente_boton": 10,
        "pad_ancho": 72, "pad_alto": 72,
        "diametro_pad_chico": 12, "fuente_pad_icono": 7,
        "fuente_pad_texto": 6, "fuente_nombre": 10,
        "fuente_ancho": 70, "fuente_alto": 300,
        "fuente_alto_canal": 120, "fuente_ancho_vu": 10,
    },
    "Mediano": {
        "diametro_boton": 28, "fuente_boton": 12,
        "pad_ancho": 105, "pad_alto": 105,
        "diametro_pad_chico": 16, "fuente_pad_icono": 8,
        "fuente_pad_texto": 6, "fuente_nombre": 12,
        "fuente_ancho": 100, "fuente_alto": 340,
        "fuente_alto_canal": 175, "fuente_ancho_vu": 15,
    },
    "Grande": {
        "diametro_boton": 36, "fuente_boton": 14,
        "pad_ancho": 138, "pad_alto": 138,
        "diametro_pad_chico": 21, "fuente_pad_icono": 9,
        "fuente_pad_texto": 7, "fuente_nombre": 14,
        "fuente_ancho": 132, "fuente_alto": 434,
        "fuente_alto_canal": 230, "fuente_ancho_vu": 20,
    },
}
TAMANO_ICONO_POR_DEFECTO = "Mediano"

ANCHO_VENTANA_REFERENCIA = 1300
ALTO_VENTANA_REFERENCIA = 760
ESCALA_MINIMA = 0.40
ESCALA_MAXIMA = 1.50
ESCALA_BASE = 0.78

NOMBRE_FUENTE_EFECTOS = "Soundboard_Efectos"
ETIQUETA_FUENTE_EFECTOS = "Efectos De Sonido"
NUM_BOTONES_SOUNDBOARD_INICIAL = 12

# ============================================================
# SECCIÓN DE CALIBRACIÓN DEL MEDIDOR DE VOLUMEN
# ============================================================
# Estos son TODOS los parámetros que controlan cómo se ve y se
# comporta el medidor de nivel (el de las lucecitas de colores), en un
# solo lugar para poder tocarlos sin andar buscando por todo el
# archivo. Nota importante: como el medidor ahora usa DIRECTAMENTE el
# nivel que OBS reporta para cada fuente (ver niveles_actuales /
# actualizar_vu_meters_ui, más abajo en el archivo) en vez de
# reconstruirlo a mano, NO hay (ni hace falta) un número de "offset en
# dB" para que coincida con OBS: coincide porque es el mismo dato. Lo
# que sí se puede ajustar acá es CUÁNDO se considera que algo está
# saturando, CUÁNTO se sostiene el aviso, y qué tan sensible es el
# medidor a huecos cortos en los datos.

# A partir de qué nivel (en múltiplo lineal, donde 1.0 = 0 dB) se
# considera que la fuente está saturando. OBS manda el nivel de audio
# como multiplicador lineal y puede llegar a superar 1.0 cuando la
# señal excede los 0 dB (clipping real); 0.999 en vez de 1.0 exacto es
# sólo para no perder el aviso por el redondeo normal de punto
# flotante. No conviene tocarlo salvo que quieras que el aviso de
# saturación sea más/menos estricto que el de OBS.
UMBRAL_SATURACION_MUL = 0.999

# Cuánto tiempo (en segundos) se queda el medidor todo en rojo después
# de detectar una saturación, aunque el pico haya durado un instante.
# Sin este "sostenido" un clip de un solo cuadro sería casi invisible;
# con demasiado tiempo, en cambio, el aviso deja de sentirse ligado al
# momento exacto en que pasó, y con audio muy denso (picos seguidos,
# más frecuentes que este tiempo) puede dar la sensación de que el
# medidor queda "pegado" en rojo sin bajar nunca. Igual de criterio
# que el indicador de clipping de OBS. Si sentís que se sostiene
# demasiado, bajalo; si sentís que los clips cortos casi no se notan,
# subilo.
DURACION_SATURACION_SEG = 1.0

# Cuánto tiempo (en segundos) tiene que pasar SIN que una fuente mande
# ningún nivel de audio para que asumamos que de verdad dejó de sonar
# (se sacó la fuente, se cerró la app capturada, etc.) y mostremos
# silencio. Fuentes como "Captura de ventana" pierden y reenganchan su
# hook de captura seguido -sobre todo al minimizar/restaurar la
# ventana capturada- y en ese momento dejan de mandar niveles durante
# una fracción de segundo; con un umbral chico, esos huecos cortos y
# normales hacen que el medidor caiga a silencio de golpe y después
# salte para arriba en cuanto vuelve el dato, lo que se ve como un
# medidor errático sin que el audio real haya cambiado. Si notás que
# el medidor tarda de más en apagarse cuando de verdad se cortó el
# audio, bajalo un poco; si lo seguís viendo parpadear con fuentes que
# pierden el hook seguido, subilo.
UMBRAL_DATOS_VIEJOS_SEG = 1.5

# Por debajo de qué nivel (múltiplo lineal) se considera que
# 'niveles_actuales' (el mismo dato que usa la fuente SIN mutear) está
# realmente en silencio para una fuente muteada, y por lo tanto hay que
# reconstruir el nivel a mano con 'niveles_crudos' (ver 'elif muted' en
# actualizar_vu_meters_ui). Motivo: con la mayoría de las fuentes,
# mutear SÍ corta 'niveles_actuales' a 0 de verdad, así que ahí la
# reconstrucción manual es necesaria; pero hay casos puntuales donde
# OBS sigue reportando ahí el nivel real y en vivo aun estando muteada,
# y ahí conviene usar ese dato directamente en vez de reconstruirlo:
# es el valor exacto que ya calculó OBS, sin ninguna aproximación de
# acá. 0.0005 (~-66 dB) es lo
# bastante chico para no confundir ruido de piso/redondeo con audio
# real, pero deja pasar cualquier nivel que se pueda considerar "vivo".
UMBRAL_NIVEL_MUTEADO_DIRECTO = 0.0005

# Cada cuánto (en milisegundos) se refresca el medidor en pantalla.
# Cuanto más bajo, más fluido se ve, pero más trabajo le exige a la
# interfaz; 33ms es aproximadamente 30 cuadros por segundo.
INTERVALO_VU_MS = 33

# Velocidad a la que "cae" la aguja/LED del medidor cuando el nivel
# baja (subir siempre es instantáneo, como en un medidor de pico
# real; sólo la bajada se anima). A 70 dB/seg recorre el rango
# completo (0 a -60 dB) en menos de 1 segundo, parecido a un medidor
# de consola real; bajalo para que la caída se vea más lenta/suave,
# subilo para que sea más brusca/inmediata.
CAIDA_DB_POR_SEG = 70

# Ajuste manual (en dB) para el nivel RECONSTRUIDO que se muestra
# mientras una fuente está MUTEADA (ver 'elif muted' en
# actualizar_vu_meters_ui, más abajo). Ese nivel se arma multiplicando
# el dato "de entrada" que manda OBS por la ganancia del fader y la de
# los filtros, y ese cálculo puede quedar corrido unos cuantos dB del
# nivel real por cosas que este programa no puede leer de OBS (por
# ejemplo, la ganancia de hardware del dispositivo de audio, o
# filtros/etapas que no están en CAMPOS_GANANCIA_FILTRO). En vez de
# seguir adivinando, este número lo compensa a mano:
#   - Si la barra muteada queda MÁS ALTA que la activa -sube de más-,
#     bajá este número (poné un valor más negativo).
#   - Si la barra muteada queda MÁS BAJA que la activa -sube de
#     menos-, subí este número (poné un valor más positivo).
# Probalo muteando y desmuteando la MISMA fuente con el MISMO audio
# sonando, comparando dónde queda la barra en cada caso, y ajustá de a
# poco (2 o 3 dB por vez) hasta que las dos coincidan.
CALIBRACION_VU_MUTEADO_DB = 0.0

# Diagnóstico (opcional): imprime en la consola, para UNA fuente
# puntual, el nivel real que reporta OBS y si hubo algún hueco de
# datos. Poné acá el nombre EXACTO de la fuente tal como aparece en el
# panel (por ejemplo "Captura de ventana") para activarlo; dejalo en
# None para no imprimir nada (así queda por defecto). Sirve para
# comparar con certeza, mirando los números en la consola en vez de a
# ojo entre capturas de pantalla, si en algún momento el medidor
# vuelve a parecer raro.
DEBUG_VU_FUENTE = None
INTERVALO_DEBUG_VU_SEG = 0.25
# lo que trae "de fábrica" (y que por lo tanto el medidor tiene que
# tener en cuenta): para cada "kind" de filtro que puede sumar
# ganancia, el nombre del campo (en dB) que hay que leerle. El filtro
# de "Ganancia" es el caso obvio, pero la "Ganancia de salida" del
# Compresor hace exactamente lo mismo (sube la señal después de
# comprimirla), así que se suma igual.
CAMPOS_GANANCIA_FILTRO = {
    "gain_filter": "db",
    "compressor_filter": "output_gain",
}

# Cada cuánto (en milisegundos) se vuelve a consultar a OBS, en
# segundo plano, cuánta ganancia extra están aplicando los filtros de
# cada fuente (ver _calcular_ganancia_extra_fuente). No hace falta que
# sea tan seguido como el medidor de nivel: la ganancia de un filtro no
# cambia sola, sólo cuando alguien la toca -y esos casos puntuales ya
# se refrescan al toque, sin esperar este ciclo (ver
# _refrescar_ganancia_fuente)-, así que este ciclo es sólo una red de
# contención por si algo se movió desde otro lado (otra instancia del
# programa, o la propia ventana de filtros de OBS).
INTERVALO_REFRESCO_GANANCIA_MS = 1000

ETIQUETAS_MONITOREO = {
    "OBS_MONITORING_TYPE_NONE": "🎧 OFF",
    "OBS_MONITORING_TYPE_MONITOR_ONLY": "🎧 SOLO YO",
    "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT": "🎧 YO + STREAM",
}

COLORES_MONITOREO = {
    "OBS_MONITORING_TYPE_NONE": "#394151",
    "OBS_MONITORING_TYPE_MONITOR_ONLY": "#4dabf7",
    "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT": "#2fd693",
}

COLOR_BORDE_PRINCIPAL = "#ffb454"

COLOR_GRIS_ATENUADO = "#8e98ad"


COLOR_SOMBRA = "#05070c"

# ------------------------------------------------------------------
# PLACAS DE VIDRIO (el nuevo aspecto de los pads del soundboard)
# ------------------------------------------------------------------
# Los pads ya no se dibujan con primitivas de Tk (polígonos + líneas).
# Tk no suaviza nada de lo que dibuja: cada curva y cada borde diagonal
# queda con escalones visibles, y eso es exactamente lo que se veía
# como "pixelado". Acá, en cambio, cada pad se arma con Pillow a varias
# veces la resolución final (supersampling) y recién al final se achica
# con LANCZOS, que promedia esos sub-píxeles: el resultado es un botón
# con marco claro biselado, foso negro, cara oscura en degradado y un
# reflejo de vidrio en la esquina superior izquierda, todo con bordes
# perfectamente lisos a cualquier tamaño.
FACTOR_SUPERSAMPLING_PLACAS = 4
LADO_MAXIMO_RENDER_PLACA = 1600      # tope del lienzo interno, por costo

COLOR_PLACA_MARCO_ARRIBA = "#d4dcea"     # brillo del marco metálico
COLOR_PLACA_MARCO_ABAJO = "#69778f"
COLOR_PLACA_FOSO = "#04060a"             # ranura negra entre marco y cara
COLOR_PLACA_CARA_ARRIBA = "#2e3646"      # cara del pad, arriba
COLOR_PLACA_CARA_ABAJO = "#161b25"       # cara del pad, abajo
LIMITE_CACHE_PLACAS = 120


FACTOR_SUPERSAMPLING_CIRCULOS = 6


NUM_SEGMENTOS_VU = 24


COLOR_LED_SATURADO = "#ff2441"
# Equivalente en gris del color de saturación de arriba: se usa cuando
# la fuente está atenuada (fuera de escena / muteada) y satura, para
# marcarlo igual que en color pero sin romper el "modo gris" -nada de
# rojo mezclado con la tarjeta gris, todo el tramo encendido pasa a
# este gris bien claro, más claro que cualquiera de los grises
# normales del degradado (ver color_on_gris en _dibujar_segmentos_led)
# para que la saturación siga notándose como un aviso distinto.
COLOR_LED_SATURADO_GRIS = "#f2f4fb"



ALTO_CANAL = 230
ANCHO_BARRA_VU = 20


# Margen (en píxeles) de "colchón" antes de sacarle una columna entera a
# la grilla de fuentes. Sin este margen, cualquier achique mínimo del
# panel (por ejemplo, arrastrar apenas un poco el divisor hacia el lado
# de las fuentes) hacía caer de golpe la última columna entera a la fila
# de abajo. Con el margen, un achique chico simplemente angosta un poco
# las tarjetas (ver _ancho_celda_fuentes) en vez de reacomodar todo; sólo
# se saca una columna cuando el espacio que falta es "de verdad" y no
# "apenas un poco".
MARGEN_HISTERESIS_COLUMNAS = 40


UMBRAL_ARRASTRE_PX = 6



AJUSTES_FUENTE_EFECTOS = {
    "local_file": "",
    "is_local_file": True,
    "restart_on_activate": False,
    "close_when_inactive": False,
}


# ------------------------------------------------------------------
# CHEQUEO PERIÓDICO DEL ESTADO REAL DE REPRODUCCIÓN
# ------------------------------------------------------------------
# El brillo del pad no se apaga "a ojo" (por ejemplo, calculando
# cuánto dura el archivo): se le pregunta a OBS, cada
# INTERVALO_REFRESCO_REPRODUCCION_MS, si el medio todavía está
# reproduciéndose de verdad. Así, un efecto con una cola larga de
# silencio (o simplemente muy bajo) se sigue viendo iluminado mientras
# OBS lo siga teniendo activo, en vez de apagarse antes de tiempo.
INTERVALO_REFRESCO_REPRODUCCION_MS = 150
GRACIA_INICIO_REPRODUCCION_SEG = 0.35  # ignora el estado recién arrancado un
# instante: al reiniciar, OBS puede tardar un pestañeo en reportar
# "reproduciendo" y hasta entonces todavía contesta el estado viejo
# ("detenido"), que si le hiciéramos caso apagaría la luz apenas
# prendida.
ESTADOS_MEDIA_DETENIDO = {"OBS_MEDIA_STATE_STOPPED", "OBS_MEDIA_STATE_ENDED", "OBS_MEDIA_STATE_ERROR"}
MARGEN_REAJUSTE_ANCHO_SOUNDBOARD = 0


COLOR_PANEL_SOUNDBOARD = "#10141b"
