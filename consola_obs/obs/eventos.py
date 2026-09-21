import threading
import time

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs.obs import cliente as mod_obs_cliente
from consola_obs.ui import dibujo as mod_ui_dibujo
from consola_obs.ui import tarjeta_fuente as mod_ui_tarjeta


def _valor(obj, *nombres_posibles):
    """Lee un campo probando varios nombres, porque según la versión de la
    librería los datos llegan como diccionarios o como objetos con
    atributos (algunas respuestas y eventos vienen en snake_case, otras en
    camelCase). Se usa tanto para los eventos de audio como para la lista
    de fuentes, así ninguna fuente se pierde por una diferencia de formato."""
    for nombre in nombres_posibles:
        if isinstance(obj, dict):
            if nombre in obj:
                return obj[nombre]
        elif hasattr(obj, nombre):
            return getattr(obj, nombre)
    return None


def on_input_volume_meters(datos):
    try:
        entradas = _valor(datos, "inputs") or []
        ahora = time.monotonic()
        for item in entradas:
            nombre = _valor(item, "input_name", "inputName")
            canales = _valor(item, "input_levels_mul", "inputLevelsMul") or []
            pico = 0.0
            pico_entrada = 0.0
            pico_entrada_crudo = 0.0
            hubo_saturacion = False
            for canal in canales:
                valores_validos = []
                if isinstance(canal, (list, tuple)):
                    for v in canal:
                        try:
                            valores_validos.append(float(v))
                        except (TypeError, ValueError):
                            continue
                else:
                    try:
                        valores_validos.append(float(canal))
                    except (TypeError, ValueError):
                        continue
                if not valores_validos:
                    continue
                if len(valores_validos) >= 2:
                    valor_canal = valores_validos[1]
                else:
                    valor_canal = valores_validos[0]
                valor_entrada = valores_validos[2] if len(valores_validos) >= 3 else valor_canal
                # NO se convierte nada acá. OBS manda 'input_levels_mul'
                # siempre como multiplicador LINEAL (1.0 = 0dB), nunca
                # como porcentaje 0-100 -antes había código que, si el
                # valor caía entre 1.0 y 100.0, asumía que era un
                # porcentaje y lo dividía por 100. Esa suposición está
                # mal: el multiplicador lineal real SÍ puede superar
                # 1.0 cuando el audio está saturando de verdad (por
                # ejemplo con el filtro de Ganancia bien arriba, un
                # pasaje fuerte puede dar 3.0, 5.0, etc. -varios dB por
                # encima de 0dB-), y esos valores caen justo en el
                # rango "1.0 a 100.0". Dividirlos por 100 los aplastaba
                # a un número chico, así que cuanto MÁS saturaba el
                # audio real, más probable era que el medidor mostrara
                # MENOS nivel en vez de más. El recorte a 1.0 para el
                # dibujo del medidor se hace más abajo con min(1.0, ...),
                # que es la forma correcta de manejar un valor por
                # encima de 0dB sin perder la información de que hubo
                # saturación real.
                # Ojo: la saturación se chequea ACÁ, sobre el valor
                # todavía sin recortar a 1.0. El multiplicador lineal
                # que manda OBS vale 1.0 en 0 dB y puede superarlo si la
                # señal realmente está saturando (clipping); si
                # esperáramos a "pico" (ya recortado un poco más abajo
                # con min(1.0, ...)) esa información se perdería sin
                # forma de distinguir "llegó justo a 0 dB" de "se fue
                # varios dB por encima".
                #
                # Importante: se chequea SÓLO 'valor_canal' (el nivel
                # después de aplicar fader y mute, lo que de verdad
                # está sonando ahora mismo), NUNCA 'valor_entrada' (la
                # señal cruda de ANTES del fader). Antes se chequeaban
                # los dos, y eso hacía que una fuente cuya señal de
                # origen entra fuerte apareciera marcada como
                # "saturando" aunque el fader estuviera bien abajo y
                # fuera literalmente imposible que saturase con ese
                # volumen -'valor_entrada' ya se usa por separado más
                # abajo (ver nivel_mul_crudo en actualizar_vu_meters_ui)
                # para la detección DINÁMICA que sí tiene en cuenta el
                # fader actual; no hace falta duplicarla acá encima con
                # el dato crudo.
                if valor_canal >= C.UMBRAL_SATURACION_MUL:
                    hubo_saturacion = True
                pico = max(pico, max(0.0, min(1.0, valor_canal)))
                pico_entrada = max(pico_entrada, max(0.0, min(1.0, valor_entrada)))
                # Mismo valor que 'pico_entrada' arriba, pero SIN el
                # techo de 1.0: se necesita entero para la
                # reconstrucción de 'elif muted' en
                # actualizar_vu_meters_ui (ver 'niveles_crudos' y el
                # comentario ahí) -si a esta altura ya lo recortamos a
                # 1.0, una fuente con un filtro de Ganancia que empuja
                # la señal bien por encima de 0dB (algo común en audio
                # de escritorio, más "caliente" que un micrófono) queda
                # SIEMPRE en el techo, y multiplicada después por la
                # ganancia del fader da un número que nunca puede
                # superar exactamente la posición del fader -aunque el
                # audio real suba y baje, para la cuenta es como si
                # siempre estuviera al tope-, y el medidor deja de
                # reaccionar al audio real.
                pico_entrada_crudo = max(pico_entrada_crudo, max(0.0, valor_entrada))
            if nombre:
                E.niveles_actuales[nombre] = pico
                E.niveles_entrada[nombre] = pico_entrada
                E.niveles_crudos[nombre] = pico_entrada_crudo
                widgets = E.fuentes.get(nombre)
                if pico > 0.0001:
                    E.niveles_antes_mute[nombre] = pico
                E.ultima_actualizacion_nivel[nombre] = ahora
                if hubo_saturacion:
                    E.ultima_vez_saturado[nombre] = ahora
    except Exception as e:
        print(f"Error procesando niveles de audio: {e}")

def on_scene_created(_datos):
    """Cuando se crea una escena nueva en OBS, la igualamos al resto:
    le agregamos la fuente de efectos del soundboard, la de música de
    fondo y las fuentes marcadas como 'principales' (ver
    _alternar_principal), sin que el usuario tenga que acordarse de
    apretar 'Actualizar fuentes'. El resto de las fuentes de audio YA
    NO se fuerzan a todas las escenas: sólo se muestran (grises si no
    están en la escena al aire)."""
    threading.Thread(target=mod_obs_cliente.preparar_fuente_efectos, daemon=True).start()
    threading.Thread(target=mod_obs_cliente.preparar_fuente_musica, daemon=True).start()
    threading.Thread(target=mod_obs_cliente.asegurar_fuentes_principales_en_todas_las_escenas, daemon=True).start()


def on_current_program_scene_changed(_datos):
    """La escena al aire cambió (desde OBS o desde otra instancia de
    este mismo programa): recalculamos qué fuentes están 'en escena'
    para actualizar el gris de las que no están."""
    threading.Thread(target=mod_obs_cliente._refrescar_membresia_escena, daemon=True).start()


def on_scene_item_enable_state_changed(_datos):
    """Alguien prendió/apagó el 'ojito' de una fuente en la escena
    actual: puede cambiar si esa fuente cuenta como 'en escena'."""
    threading.Thread(target=mod_obs_cliente._refrescar_membresia_escena, daemon=True).start()


def on_scene_item_created(_datos):
    threading.Thread(target=mod_obs_cliente._refrescar_membresia_escena, daemon=True).start()


def on_scene_item_removed(_datos):
    threading.Thread(target=mod_obs_cliente._refrescar_membresia_escena, daemon=True).start()


# ------------------------------------------------------------------
# Fuentes creadas o borradas DESDE DENTRO de OBS (punto 3.3 del plan)
# ------------------------------------------------------------------
# Antes la consola sólo escuchaba eventos de ítems de escena, así que
# una fuente nueva aparecía sola únicamente si se agregaba a la escena
# al aire; una fuente de audio global (Mic/Aux, Audio de escritorio,
# los que se eligen en Configuración > Audio de OBS) no es ítem de
# ninguna escena y por eso no se enteraba hasta apretar "Actualizar
# fuentes" a mano. Con InputCreated/InputRemoved el refresco es solo.
#
# El refresco se agrupa con un pequeño retardo porque OBS puede mandar
# varios de estos eventos casi juntos (por ejemplo al cargar una
# colección de escenas entera): sin esto se dispararía una actualización
# completa por cada fuente, y son pedidos pesados.
_refresco_por_fuentes = {"id": None}
RETARDO_REFRESCO_FUENTES_MS = 400


def _programar_refresco_lista_fuentes():
    if not E.conectado:
        return
    if _refresco_por_fuentes["id"] is not None:
        try:
            E.ventana.after_cancel(_refresco_por_fuentes["id"])
        except Exception:
            pass
    _refresco_por_fuentes["id"] = E.ventana.after(
        RETARDO_REFRESCO_FUENTES_MS, _refrescar_lista_fuentes_ahora
    )


def _refrescar_lista_fuentes_ahora():
    _refresco_por_fuentes["id"] = None
    if not E.conectado:
        return
    # Si ya hay un "Actualizar fuentes" en curso (el botón queda
    # deshabilitado mientras corre el hilo), se espera un poco y se
    # reintenta, en vez de lanzar dos actualizaciones pisándose.
    try:
        if str(E.boton_actualizar["state"]) == "disabled":
            _refresco_por_fuentes["id"] = E.ventana.after(
                RETARDO_REFRESCO_FUENTES_MS, _refrescar_lista_fuentes_ahora
            )
            return
    except Exception:
        pass
    try:
        mod_ui_tarjeta.actualizar()
    except Exception as e:
        print(f"No se pudo refrescar la lista de fuentes: {e}")


def on_input_created(_datos):
    """Alguien creó una fuente desde OBS (o desde este mismo programa):
    la consola la levanta sola, sin tener que apretar 'Actualizar
    fuentes'."""
    E.ventana.after(0, _programar_refresco_lista_fuentes)


def on_input_removed(_datos):
    """Se borró una fuente desde OBS: se saca la tarjeta de la consola."""
    E.ventana.after(0, _programar_refresco_lista_fuentes)


def on_input_mute_state_changed(datos):
    """Alguien mutea/desmutea una fuente directamente desde OBS (u otro
    controlador): reflejarlo acá en tiempo real, sin esperar al próximo
    'Actualizar fuentes'."""
    nombre = _valor(datos, "input_name", "inputName")
    muted = _valor(datos, "input_muted", "inputMuted")
    if nombre is None or muted is None:
        return
    E.ventana.after(0, lambda: _sincronizar_mute_remoto(nombre, muted))


def _sincronizar_mute_remoto(nombre, muted):
    widgets = E.fuentes.get(nombre)
    if not widgets:
        return
    widgets["muted"] = muted
    mod_ui_dibujo._actualizar_boton_circular(
        widgets["mute"],
        texto_nuevo=("🔇" if muted else "🔊"),
        color_nuevo=mod_ui_dibujo._color_mute(muted)
    )
    mod_ui_tarjeta._actualizar_estado_gris(nombre)


def on_input_volume_changed(datos):
    """Ídem para el volumen: si alguien mueve el fader desde OBS."""
    nombre = _valor(datos, "input_name", "inputName")
    vol_db = _valor(datos, "input_volume_db", "inputVolumeDb")
    if nombre is None or vol_db is None:
        return
    E.ventana.after(0, lambda: _sincronizar_volumen_remoto(nombre, vol_db))


def _sincronizar_volumen_remoto(nombre, vol_db):
    widgets = E.fuentes.get(nombre)
    if not widgets or widgets.get("arrastrando"):
        return
    widgets["fader"].set(vol_db)
    if nombre == C.NOMBRE_FUENTE_EFECTOS:
        # Fader movido desde OBS: también es nivel base para fundidos
        # (import lazy: audio importa este módulo).
        try:
            from consola_obs.audio import reproduccion as mod_audio_reproduccion
            mod_audio_reproduccion.nota_volumen_usuario(vol_db)
        except Exception:
            pass
    if vol_db <= E.UMBRAL_SILENCIO:
        widgets["db"].config(text="SILENCIO", fg="#828da6")
    else:
        widgets["db"].config(text=f"{vol_db:.1f} dB", fg=C.MOD_TEXTO if E.es_moderna() else "#2fd693")


def on_input_audio_monitor_type_changed(datos):
    """Ídem para el tipo de monitoreo (auriculares)."""
    nombre = _valor(datos, "input_name", "inputName")
    tipo = _valor(datos, "monitor_type", "monitorType")
    if nombre is None or not tipo:
        return
    E.ventana.after(0, lambda: _sincronizar_monitor_remoto(nombre, tipo))


def _sincronizar_monitor_remoto(nombre, tipo):
    widgets = E.fuentes.get(nombre)
    if not widgets:
        return
    widgets["tipo_monitor"] = tipo
    mod_ui_dibujo._actualizar_boton_circular(widgets["monitor"], color_nuevo=(
        mod_ui_dibujo._cuadrado_monitor(tipo) if E.es_moderna()
        else C.COLORES_MONITOREO.get(tipo, "#394151")))


def on_input_name_changed(datos):
    """Alguien renombró una fuente directamente desde OBS (o desde
    otra instancia de este mismo programa): reflejarlo acá sin que el
    usuario tenga que apretar 'Actualizar fuentes'. Si el renombre se
    originó ACÁ (ver _confirmar_renombrar_fuente), este mismo evento
    también llega -OBS le hace eco a todos los clientes conectados,
    incluido el que lo pidió- pero para entonces _renombrar_fuente_localmente
    ya no encuentra el nombre viejo (ya se migró) y no hace nada de
    más."""
    nombre_viejo = _valor(datos, "old_input_name", "oldInputName")
    nombre_nuevo = _valor(datos, "input_name", "inputName")
    if not nombre_viejo or not nombre_nuevo:
        return
    E.ventana.after(0, lambda: mod_ui_tarjeta._renombrar_fuente_localmente(nombre_viejo, nombre_nuevo))


def _quizas_refrescar_dialogo_filtros(datos):
    """Si hay un diálogo de filtros abierto para esta misma fuente, lo
    refresca para reflejar el cambio hecho desde OBS (filtro agregado,
    quitado, activado/desactivado, etc.)."""
    nombre = _valor(datos, "source_name", "sourceName")
    if nombre and E._dialogo_filtros_abierto["nombre"] == nombre and E._dialogo_filtros_abierto["refrescar"]:
        E.ventana.after(0, E._dialogo_filtros_abierto["refrescar"])


def _calcular_ganancia_extra_fuente(nombre):
    """Suma, en dB, la ganancia que están aplicando ahora mismo los
    filtros de audio de 'nombre' que pueden subir la señal por encima
    de lo que ya trae (ver CAMPOS_GANANCIA_FILTRO). Sólo cuenta la de
    los filtros que están HABILITADOS: uno desactivado no afecta el
    audio real. Hace varios pedidos a OBS (uno por la lista de
    filtros, uno más por cada filtro relevante para leerle el valor),
    así que SIEMPRE se llama desde un hilo aparte, nunca desde el hilo
    de la interfaz."""
    if not E.conectado:
        return 0.0
    total_db = 0.0
    try:
        filtros = E.cliente_obs.get_source_filter_list(nombre).filters or []
    except Exception:
        return 0.0
    for filtro in filtros:
        kind = _valor(filtro, "filter_kind", "filterKind")
        campo = C.CAMPOS_GANANCIA_FILTRO.get(kind)
        if not campo:
            continue
        if not _valor(filtro, "filter_enabled", "filterEnabled"):
            continue
        nombre_filtro = _valor(filtro, "filter_name", "filterName")
        try:
            info = E.cliente_obs.get_source_filter(nombre, nombre_filtro)
            ajustes = _valor(info, "filter_settings", "filterSettings") or {}
        except Exception:
            continue
        try:
            total_db += float(ajustes.get(campo, 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
    return total_db


def _refrescar_ganancia_fuente(nombre):
    """Recalcula y guarda la ganancia extra de UNA fuente puntual, en
    segundo plano. Se llama después de cualquier acción que pueda
    haberla cambiado (tocar el filtro de Ganancia, prenderlo/apagarlo,
    borrarlo, etc.) para que el medidor reaccione al toque, sin
    esperar al ciclo de refresco periódico."""
    E.ganancia_filtros_db[nombre] = _calcular_ganancia_extra_fuente(nombre)


def _refrescar_ganancia_fuente_en_hilo(nombre):
    threading.Thread(target=_refrescar_ganancia_fuente, args=(nombre,), daemon=True).start()


def _refrescar_ganancia_todas_las_fuentes():
    for nombre in list(E.fuentes.keys()):
        _refrescar_ganancia_fuente(nombre)


def _programar_refresco_ganancia():
    """Red de contención: cada INTERVALO_REFRESCO_GANANCIA_MS
    reconsulta la ganancia de todas las fuentes conocidas, por si algo
    la cambió sin pasar por ninguno de los ganchos puntuales de arriba
    (por ejemplo, tocando el filtro directamente desde OBS)."""
    if E.conectado:
        threading.Thread(target=_refrescar_ganancia_todas_las_fuentes, daemon=True).start()
    E.ventana.after(C.INTERVALO_REFRESCO_GANANCIA_MS, _programar_refresco_ganancia)


def _quizas_refrescar_ganancia_por_evento(datos):
    nombre = _valor(datos, "source_name", "sourceName")
    if nombre:
        _refrescar_ganancia_fuente_en_hilo(nombre)


def on_source_filter_created(datos):
    _quizas_refrescar_dialogo_filtros(datos)
    _quizas_refrescar_ganancia_por_evento(datos)


def on_source_filter_removed(datos):
    _quizas_refrescar_dialogo_filtros(datos)
    _quizas_refrescar_ganancia_por_evento(datos)


def on_source_filter_enable_state_changed(datos):
    _quizas_refrescar_dialogo_filtros(datos)
    _quizas_refrescar_ganancia_por_evento(datos)


def on_source_filter_list_reindexed(datos):
    _quizas_refrescar_dialogo_filtros(datos)
    _quizas_refrescar_ganancia_por_evento(datos)


def on_source_filter_name_changed(datos):
    _quizas_refrescar_dialogo_filtros(datos)
