import math
import time

from consola_obs import estado as E
from consola_obs import constantes as C
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
    except Exception:
        return
    ahora = time.monotonic()
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
        if not datos_vigentes:
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

        widgets["vu_visual_db"] = db_visual

        # Si la fuente está atenuada (fuera de escena / con el medidor
        # en gris) la saturación se sigue marcando igual -ver
        # _actualizar_medidor_led-, sólo que en gris en vez de rojo,
        # para no perder el aviso de saturación por estar en modo gris.
        saturado = (ahora - E.ultima_vez_saturado.get(nombre, -math.inf)) <= C.DURACION_SATURACION_SEG

        _log_debug_vu(nombre, nivel_mul_crudo, datos_vigentes, saturado, ahora)

        if E._modo_super.get("activo"):
            # En modo super sólo se sigue el nivel (matemática barata);
            # el pintado se pausa y se invalida para repintar completo
            # al salir, sin saltos.
            widgets.setdefault("vu_led_estado", {}).pop("ultimo", None)
            continue

        _actualizar_medidor_led(
            widgets["vu_canvas"], widgets["vu_segmentos"], db_visual,
            atenuado=atenuado, saturado=saturado,
            estado=widgets.setdefault("vu_led_estado", {})
        )
