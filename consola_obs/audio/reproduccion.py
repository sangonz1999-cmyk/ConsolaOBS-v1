import threading
import time

from tkinter import messagebox

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import configuracion as mod_configuracion
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.audio import nivelacion as mod_nivelacion
from consola_obs.audio import rutas_obs as mod_rutas_obs
from consola_obs.ui import soundboard as mod_ui_soundboard

_reproduccion_local = {"dispositivo": None, "token": None}
_aviso_miniaudio = {"mostrado": False}
DURACION_FUNDIDO_LOCAL_SEG = 2.0

# Coordinación fundido <-> reproducción nueva (bugs de volumen pisado
# y de segundo sonido mudo): el fundido avisa cuando está activo y
# cuando termina. Una reproducción nueva espera a que termine (corto)
# y recién ahí fija el volumen base y dispara: nunca corren pisados.
# vol_base_db es el nivel del fader del usuario, al que SIEMPRE se
# vuelve tras un fundido (nunca un intermedio a medio fundir).
_fade_obs = {"activo": False, "listo": None, "vol_base_db": None}
_fade_obs["listo"] = threading.Event()
_fade_obs["listo"].set()
# Racha de lecturas terminales seguidas para apagar la luz (ver
# _consultar_estado_reproduccion): una sola lectura puede ser un eco
# viejo del RESTART todavía no aplicado.
_fin_confirmado = {"token": None, "rachas": 0}


def nota_volumen_usuario(db):
    """El usuario movió el fader de efectos (acá o en OBS): ese es el
    nivel base al que se vuelve tras cada fundido. Durante un fundido
    no vale (ahí manda el fundido)."""
    try:
        if not _fade_obs.get("activo"):
            _fade_obs["vol_base_db"] = float(db)
    except Exception:
        pass


def _aplicar_ganancia(trozo, ganancia):
    """Multiplica las muestras por la ganancia (0.0 a 1.0), con saturación
    según el formato. Se usa para el fundido de salida del audio local."""
    if ganancia >= 1.0:
        return trozo
    formato = getattr(trozo, "typecode", None)
    try:
        if formato == "h":
            for j in range(len(trozo)):
                valor = int(trozo[j] * ganancia)
                trozo[j] = 32767 if valor > 32767 else (-32768 if valor < -32768 else valor)
        elif formato in ("f", "d"):
            for j in range(len(trozo)):
                valor = trozo[j] * ganancia
                trozo[j] = 1.0 if valor > 1.0 else (-1.0 if valor < -1.0 else valor)
    except Exception:
        pass
    return trozo


def _ganancia_fundido(progreso, db_inicial=0.0):
    """Ganancia del fundido local para un progreso 0.0→1.0, con la MISMA
    curva que el fundido de OBS (lineal en dB desde db_inicial hasta
    silencio): así los dos se callan juntos en vez de ir desfasados."""
    try:
        db = db_inicial + (E.UMBRAL_SILENCIO - db_inicial) * min(1.0, max(0.0, progreso))
        return 10.0 ** (db / 20.0)
    except Exception:
        return max(0.0, 1.0 - progreso)


def _detener_local(token=None, fundido=False, db_inicial=0.0):
    """Corta el sonido que esté saliendo por la PC. Si se pasa un token,
    sólo lo toca cuando sigue siendo la sesión vigente (para que el
    fundido de una sesión vieja no corte el sonido nuevo).

    Con fundido=True no corta en seco: marca el inicio de una rampa
    igual que la de OBS y el stream se apaga solo al llegar a silencio.
    Devuelve True si se inició un fundido."""
    if token is not None and _reproduccion_local.get("token") != token:
        return False
    if fundido and _reproduccion_local.get("dispositivo") is not None:
        _reproduccion_local["fundido_inicio"] = time.time()
        _reproduccion_local["fundido_db"] = db_inicial
        return True
    _reproduccion_local.pop("fundido_inicio", None)
    _reproduccion_local.pop("fundido_db", None)
    cancelado = _reproduccion_local.pop("cancelar", None)
    if cancelado is not None:
        try:
            cancelado.set()
        except Exception:
            pass
    dispositivo = _reproduccion_local.pop("dispositivo", None)
    _reproduccion_local["token"] = None
    if dispositivo is None:
        return False
    try:
        dispositivo.stop()
    except Exception:
        pass
    try:
        dispositivo.close()
    except Exception:
        pass
    return False


def _apagar_pad_si_desconectado(token):
    """Apaga el pad cuando NO hay OBS que maneje la luz (sin conexión la
    maneja este hilo local): si la sesión ya cambió, no toca nada."""
    if E.conectado:
        return
    try:
        indice = E._sesion_reproduccion.get("indice")
        E.ventana.after(
            0,
            lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))
    except Exception:
        pass


def _reproducir_local(ruta, token, ganancia_lineal=1.0):
    """Reproduce el archivo por la salida de audio de la PC (parlantes /
    auriculares) con miniaudio, en paralelo a OBS. Corre en su propio
    hilo. ganancia_lineal es la nivelación del pad (1.0 = sin tocar).

    OJO: device.start() NO bloquea (arranca y vuelve enseguida), así
    que hay que quedarse esperando a que el stream se agote o a que lo
    cancelen; si se cerrara el dispositivo al salir, no sonaría nada."""
    try:
        import miniaudio
    except Exception as e:
        if not _aviso_miniaudio["mostrado"]:
            _aviso_miniaudio["mostrado"] = True
            print(f"miniaudio no disponible ({e}): el sonido sólo saldrá por OBS.")
            try:
                # Aviso visible (en el .exe no hay consola donde ver el print).
                messagebox.showwarning(
                    "Sin audio local",
                    f"No se pudo cargar el motor de audio local ({e}).\n\nEl sonido sólo saldrá por OBS."
                )
            except Exception:
                pass
        _apagar_pad_si_desconectado(token)
        return
    _detener_local()
    try:
        flujo = miniaudio.stream_file(ruta)
    except Exception as e:
        print(f"No se pudo abrir el audio local {ruta}: {e}")
        _apagar_pad_si_desconectado(token)
        return
    try:
        dispositivo = miniaudio.PlaybackDevice()
    except Exception as e:
        print(f"No se pudo abrir la salida de audio de la PC: {e}")
        _apagar_pad_si_desconectado(token)
        return
    terminado = threading.Event()
    cancelado = threading.Event()

    def _flujo_envuelto():
        # El primer yield vacío es el apretón de manos: miniaudio exige
        # el generador ya arrancado (device.start le hace send() con la
        # cantidad de frames que quiere) y arrancar con next() evita el
        # TypeError sin consumir audio real del decodificador. Además,
        # cada pedido del device se reenvía al decodificador tal cual,
        # para darle siempre la cantidad exacta que pidió.
        pedido = yield b""
        try:
            try:
                trozo = next(flujo)
            except StopIteration:
                return
            if ganancia_lineal != 1.0:
                trozo = _aplicar_ganancia(trozo, ganancia_lineal)
            while True:
                if cancelado.is_set():
                    break
                inicio_fundido = _reproduccion_local.get("fundido_inicio")
                if inicio_fundido is not None:
                    progreso = (time.time() - inicio_fundido) / DURACION_FUNDIDO_LOCAL_SEG
                    if progreso >= 1.0:
                        break
                    trozo = _aplicar_ganancia(
                        trozo, _ganancia_fundido(
                            progreso, _reproduccion_local.get("fundido_db", 0.0)))
                try:
                    pedido = yield trozo
                except GeneratorExit:
                    break
                try:
                    trozo = flujo.send(pedido) if pedido else next(flujo)
                    if ganancia_lineal != 1.0:
                        trozo = _aplicar_ganancia(trozo, ganancia_lineal)
                except StopIteration:
                    break
        finally:
            try:
                flujo.close()
            except Exception:
                pass
            terminado.set()

    generador = _flujo_envuelto()
    try:
        next(generador)
    except StopIteration:
        try:
            dispositivo.close()
        except Exception:
            pass
        _apagar_pad_si_desconectado(token)
        return
    _reproduccion_local["dispositivo"] = dispositivo
    _reproduccion_local["token"] = token
    _reproduccion_local["cancelar"] = cancelado
    _reproduccion_local.pop("fundido_inicio", None)
    _reproduccion_local.pop("fundido_db", None)
    if E._sesion_reproduccion.get("token") != token:
        # La sesión se canceló mientras se abría el archivo (clic rapidísimo
        # + fundido inmediato): no se arranca para no dejar un sonido huérfano.
        _reproduccion_local.pop("dispositivo", None)
        _reproduccion_local["token"] = None
        _reproduccion_local.pop("cancelar", None)
        try:
            dispositivo.close()
        except Exception:
            pass
        return
    try:
        dispositivo.start(generador)
        while not terminado.wait(timeout=0.1):
            if cancelado.is_set():
                break
    except Exception as e:
        print(f"Error reproduciendo en la PC: {e}")
    finally:
        if _reproduccion_local.get("dispositivo") is dispositivo:
            _reproduccion_local.pop("dispositivo", None)
            _reproduccion_local["token"] = None
            _reproduccion_local.pop("cancelar", None)
            _reproduccion_local.pop("fundido_inicio", None)
            _reproduccion_local.pop("fundido_db", None)
        try:
            dispositivo.close()
        except Exception:
            pass
        # Fin del audio local (natural, fundido o cancelado): sin OBS
        # nadie más va a apagar la luz del pad.
        _apagar_pad_si_desconectado(token)


def cambiar_escuchar_en_pc(valor):
    """Se llama desde el combobox 'Escuchar acá' del menú de ajustes."""
    E.escuchar_en_pc = (valor == "Sí")

    mod_configuracion.guardar_config_interfaz({"escuchar_en_pc": E.escuchar_en_pc})

    if not E.escuchar_en_pc:
        _detener_local()


def cambiar_nivelar_efectos(valor):
    """Se llama desde el combobox 'Nivelar efectos' del menú de ajustes."""
    E.nivelar_efectos = (valor == "Sí")
    mod_configuracion.guardar_config_interfaz({"nivelar_efectos": E.nivelar_efectos})


def _asegurar_filtro_nivel(db):
    """Pone el filtro Gain propio en la fuente de efectos con los dB
    del pad que suena (lo crea si falta). No toca el fader del usuario:
    la compensación vive solo en este filtro."""
    try:
        E.cliente_obs.get_source_filter(C.NOMBRE_FUENTE_EFECTOS, C.NOMBRE_FILTRO_NIVEL)
    except Exception:
        try:
            E.cliente_obs.create_source_filter(
                C.NOMBRE_FUENTE_EFECTOS, C.NOMBRE_FILTRO_NIVEL,
                "gain_filter", {"db": 0.0})
        except Exception as e:
            print(f"No se pudo crear el filtro de nivelación: {e}")
            return
    try:
        E.cliente_obs.set_source_filter_settings(
            C.NOMBRE_FUENTE_EFECTOS, C.NOMBRE_FILTRO_NIVEL,
            {"db": float(db)}, True)
    except Exception as e:
        print(f"No se pudo aplicar la nivelación ({db} dB): {e}")
def _cargar_y_disparar(indice, accion, token):
    datos = E.config_soundboard.get(str(indice))
    if not datos or not datos.get("archivo"):
        return

    # Nivelación (ver audio/nivelacion.py): se mide el pico una sola
    # vez por archivo y se guarda en el pad; si cambió el archivo se
    # vuelve a medir. Con la nivelación apagada se usa 0 dB pero igual
    # se mide y cachea para cuando se prenda.
    ruta = datos["archivo"]
    nivel_db = datos.get("nivel_db")
    if (not isinstance(nivel_db, (int, float))
            or datos.get("nivel_archivo") != ruta
            or datos.get("nivel_version") != mod_nivelacion.NIVEL_VERSION):
        try:
            nivel_db = mod_nivelacion.ganancia_db_para(ruta)
        except Exception:
            nivel_db = 0.0
        datos["nivel_db"] = nivel_db
        datos["nivel_archivo"] = ruta
        datos["nivel_version"] = mod_nivelacion.NIVEL_VERSION
        try:
            mod_configuracion.guardar_config_soundboard()
        except Exception:
            pass
    if not bool(getattr(E, "nivelar_efectos", True)):
        nivel_db = 0.0

    # El audio local sale siempre que esté habilitado, haya o no
    # conexión a OBS: es independiente del trigger de OBS de abajo.
    suena_local = bool(getattr(E, "escuchar_en_pc", True))
    if suena_local:
        threading.Thread(
            target=_reproducir_local,
            args=(datos["archivo"], token,
                  mod_nivelacion.lineal_desde_db(nivel_db)),
            daemon=True
        ).start()

    if not E.conectado:
        # Sin OBS la sesión queda activa y la luz la maneja el hilo
        # local (se apaga al terminar o con el fundido del 2do clic).
        if not suena_local:
            messagebox.showwarning("Sin conexión", "Conectate a OBS para poder reproducir los efectos.")
            E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))
        return

    try:
        # Sincronización con un fundido en curso (si lo hay): se lo
        # espera (corto) para no pisarse el volumen a medias, y recién
        # ahí se fija el nivel base del usuario y se dispara. Sin esto,
        # disparar en medio de un fundido dejaba al sonido nuevo
        # sonando bajito o en silencio (segundo sonido mudo).
        try:
            _fade_obs["listo"].wait(timeout=1.5)
        except Exception:
            pass
        try:
            base = _fade_obs.get("vol_base_db")
            if base is not None:
                E.cliente_obs.set_input_volume(
                    C.NOMBRE_FUENTE_EFECTOS, vol_db=float(base))
        except Exception as e:
            print(f"No se pudo fijar el volumen base del efecto: {e}")
        # La ruta se traduce si el OBS está en otra PC (Fase 2 música):
        # en la misma PC llega intacta, en otra se antepone la carpeta
        # base configurada. El audio local de abajo siempre usa la
        # ruta de ESTA pc, sin traducir.
        E.cliente_obs.set_input_settings(
            C.NOMBRE_FUENTE_EFECTOS,
            {
                "local_file": mod_rutas_obs.resolver_para_obs(datos["archivo"]),
                "is_local_file": True,
                "restart_on_activate": False,
                "close_when_inactive": False,
            },
            True
        )
        _asegurar_filtro_nivel(nivel_db)
        E.cliente_obs.trigger_media_input_action(C.NOMBRE_FUENTE_EFECTOS, accion)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo reproducir el efecto.\n\n{e}")
        E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))


_cache_duracion = {}


def _cargar_duracion(indice, token, ruta):
    """Lee la duración del audio en un hilo (decodifica el archivo, que
    para efectos cortos tarda milisegundos) y la guarda en la sesión si
    sigue vigente: con eso la barra de progreso del pad avanza al ritmo
    real del sonido, haya o no conexión a OBS."""
    if not ruta:
        return
    try:
        if ruta in _cache_duracion:
            duracion = _cache_duracion[ruta]
        else:
            import miniaudio
            decodificado = miniaudio.decode_file(ruta)
            duracion = len(decodificado.samples) / max(1, decodificado.nchannels) / max(1, decodificado.sample_rate)
            if duracion > 0:
                if len(_cache_duracion) > 200:
                    _cache_duracion.clear()
                _cache_duracion[ruta] = duracion
    except Exception:
        return
    if duracion > 0 and E._sesion_reproduccion.get("token") == token:
        E._sesion_reproduccion["duracion"] = duracion


def _iniciar_reproduccion(indice):
    """Arranca (o reinicia) la reproducción de un pad. Esto SIEMPRE crea
    una sesión nueva, así que si había un fundido en curso de una
    reproducción anterior, ese fundido se va a dar cuenta -por el
    token- de que ya no es el vigente y se va a cancelar solo sin
    tocar este sonido nuevo."""
    # Freno automático remoto: sin base útil el OBS de la otra PC
    # recibiría una ruta inexistente (silencio en el stream aunque el
    # pad se ilumine y suene local). base_obs_lista_o_avisar ya mostró
    # el arreglo; acá solo se frena sin tocar la sesión.
    try:
        base_ok = mod_rutas_obs.base_obs_lista_o_avisar()
    except Exception:
        base_ok = True
    if not base_ok:
        return
    E._sesion_reproduccion["token"] += 1
    token = E._sesion_reproduccion["token"]
    E._sesion_reproduccion["inicio"] = time.time()
    E._sesion_reproduccion["deteniendo"] = False
    E._sesion_reproduccion["duracion"] = None
    E._sesion_reproduccion["ultimo_estado_obs"] = None
    try:
        ruta = (E.config_soundboard.get(str(indice)) or {}).get("archivo")
    except Exception:
        ruta = None
    E._sesion_reproduccion["archivo"] = ruta
    mod_ui_soundboard._fijar_pad_activo(indice)
    threading.Thread(
        target=_cargar_duracion,
        args=(indice, token, ruta),
        daemon=True
    ).start()
    threading.Thread(
        target=_cargar_y_disparar,
        args=(indice, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART", token),
        daemon=True
    ).start()


def _fundido_y_detener(indice, token, duracion=2.0, pasos=20):
    """Baja el volumen de la fuente de efectos desde su nivel actual
    hasta silencio en 'duracion' segundos y, al llegar abajo, detiene
    el medio. Al final (llegue a terminar o se cancele en el camino)
    siempre deja el volumen en el nivel BASE del usuario (nunca en un
    intermedio a medio fundir, que era lo que dejaba todo bajo cuando
    se encadenaban fundidos). El pad se apaga recién en ese momento
    -mientras dura el fundido, el sonido técnicamente sigue activo en
    OBS, así que la luz se mantiene prendida hasta el STOP final."""
    _fade_obs["listo"].clear()
    cadena = _fade_obs.get("activo")
    _fade_obs["activo"] = True
    try:
        return _fundido_y_detener_cuerpo(indice, token, duracion, pasos, cadena)
    finally:
        _fade_obs["activo"] = False
        _fade_obs["listo"].set()


def _fundido_y_detener_cuerpo(indice, token, duracion, pasos, cadena):
    if not E.conectado:
        # Sin OBS no hay fundido de aquel lado, pero el local sí se
        # desvanece igual; la luz se apaga cuando termina (~2 s).
        if _detener_local(token, fundido=True):
            E.ventana.after(2100, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))
        else:
            E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))
        return

    try:
        respuesta = E.cliente_obs.get_input_volume(C.NOMBRE_FUENTE_EFECTOS)
        vol_inicial = mod_obs_eventos._valor(respuesta, "input_volume_db", "inputVolumeDb")
        if vol_inicial is None:
            vol_inicial = 0.0
    except Exception as e:
        print(f"No se pudo leer el volumen para el fundido: {e}")
        vol_inicial = 0.0

    if not cadena:
        # Cabeza de cadena: este nivel es el del usuario y es al que
        # se vuelve siempre (los fundidos encadenados no lo pisan).
        try:
            _fade_obs["vol_base_db"] = float(vol_inicial)
        except Exception:
            pass

    # El fundido local arranca en paralelo al de OBS (misma duración y
    # misma curva en dB, para que se callen juntos sin delay).
    _detener_local(token, fundido=True, db_inicial=vol_inicial)

    intervalo = duracion / pasos
    cancelado = False
    for paso in range(1, pasos + 1):
        if E._sesion_reproduccion.get("token") != token:
            # Mientras fundía se disparó otra reproducción (de este
            # mismo pad o de otro): dejamos el sonido nuevo en paz.
            cancelado = True
            break
        fraccion = paso / pasos
        db = vol_inicial + (E.UMBRAL_SILENCIO - vol_inicial) * fraccion
        try:
            if db <= E.UMBRAL_SILENCIO:
                E.cliente_obs.set_input_volume(C.NOMBRE_FUENTE_EFECTOS, vol_mul=0)
            else:
                E.cliente_obs.set_input_volume(C.NOMBRE_FUENTE_EFECTOS, vol_db=db)
        except Exception as e:
            print(f"Error durante el fundido: {e}")
            cancelado = True
            break
        time.sleep(intervalo)

    if not cancelado:
        # Re-chequeo final: el sleep anterior pudo haber dejado pasar
        # una reproducción nueva; sin esto el STOP mataba al sonido
        # nuevo recién arrancado (segundo sonido mudo).
        if E._sesion_reproduccion.get("token") != token:
            cancelado = True
        else:
            try:
                E.cliente_obs.trigger_media_input_action(
                    C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
                )
                # El STOP es async: OBS tarda un pelín en aplicarlo de
                # verdad. Si devolviéramos el volumen ya mismo, hay una
                # ventana breve en la que el sonido -que técnicamente
                # sigue reproduciéndose todavía- se escucha de golpe a
                # volumen normal antes de cortar. Por eso se espera a que
                # OBS confirme que ya se detuvo (o, como red de
                # contención, hasta un segundo) antes de restaurar.
                _esperar_a_que_se_detenga(token)
            except Exception as e:
                print(f"Error deteniendo el efecto tras el fundido: {e}")

    try:
        base = _fade_obs.get("vol_base_db")
        if base is None:
            base = vol_inicial
        E.cliente_obs.set_input_volume(C.NOMBRE_FUENTE_EFECTOS, vol_db=float(base))
    except Exception as e:
        print(f"No se pudo restaurar el volumen tras el fundido: {e}")

    if E._sesion_reproduccion.get("token") == token:
        # La fuente queda en reposo: se vacía para que OBS no
        # reproduzca solo este archivo la próxima vez que se abra.
        _vaciar_fuente_efectos()

    _detener_local(token)
    E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))


def _esperar_a_que_se_detenga(token, tope_seg=1.0):
    """Sondea el estado real del efecto hasta que OBS confirme que ya
    se detuvo (o hasta 'tope_seg' como red de contención, por si el
    STOP nunca llega a reflejarse en el estado por algún motivo)."""
    limite = time.time() + tope_seg
    while time.time() < limite:
        if E._sesion_reproduccion.get("token") != token:
            # Arrancó otra reproducción mientras esperábamos: ya no
            # tiene sentido seguir esperando a que ESTA se detenga.
            return
        try:
            respuesta = E.cliente_obs.get_media_input_status(C.NOMBRE_FUENTE_EFECTOS)
            estado = mod_obs_eventos._valor(respuesta, "media_state", "mediaState")
        except Exception as e:
            print(f"No se pudo confirmar que el efecto se detuvo: {e}")
            return
        if estado in C.ESTADOS_MEDIA_DETENIDO:
            return
        time.sleep(0.05)


def _vaciar_fuente_efectos():
    """Deja la fuente de efectos sin archivo cargado (local_file="").
    Cada pad deja su audio cargado en la fuente compartida
    Soundboard_Efectos, y si no se vacía, al abrir OBS ese archivo se
    reproduce solo al activarse la escena, aunque la consola ni esté
    abierta. Se llama cada vez que la fuente queda en reposo (fin
    natural, STOP manual, fundido o cierre de la app)."""
    if not E.conectado:
        return
    try:
        E.cliente_obs.set_input_settings(
            C.NOMBRE_FUENTE_EFECTOS,
            {
                "local_file": "",
                "restart_on_activate": False,
                "close_when_inactive": False,
            },
            True
        )
    except Exception as e:
        print(f"No se pudo vaciar la fuente de efectos: {e}")


def detener_y_vaciar_efectos():
    """STOP + vaciado best-effort para el cierre de la app: así no queda
    ningún archivo cargado que OBS reproduzca solo al abrirse."""
    _detener_local()
    if not E.conectado:
        return
    try:
        _fade_obs["listo"].wait(timeout=0.5)
        base = _fade_obs.get("vol_base_db")
        if base is not None:
            E.cliente_obs.set_input_volume(
                C.NOMBRE_FUENTE_EFECTOS, vol_db=float(base))
    except Exception:
        pass
    try:
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        )
    except Exception:
        pass
    _vaciar_fuente_efectos()


def reproducir_sonido(indice):
    try:
        datos = E.config_soundboard.get(str(indice)) or {}
    except Exception:
        datos = {}
    if not datos.get("archivo"):
        # Pad vacío: no hay nada que reproducir (y sin esto la sesión
        # quedaba activa con la luz prendida para siempre).
        return
    sesion = E._sesion_reproduccion
    if sesion.get("indice") == indice:
        # Segundo clic sobre el pad que suena: fundido de 2 segundos.
        # Pero si lo último que informó OBS es terminal (el sonido ya
        # terminó y la luz todavía no se apagó, ventana más grande en
        # remoto por latencia), NO es un fundido: es "tocar de nuevo"
        # y arranca fresco. Sin esto el clic bajaba el volumen 2 s en
        # vez de sonar (y no sonaba nada).
        # Mientras se está apagando se ignoran más clics, hasta que el
        # sonido termine: si no, el spam de clics re-dispara sesiones y
        # el audio se buguea. Vale conectado a OBS o no.
        if sesion.get("ultimo_estado_obs") in C.ESTADOS_MEDIA_DETENIDO:
            _iniciar_reproduccion(indice)
            return
        if sesion.get("deteniendo"):
            return
        sesion["deteniendo"] = True
        token = sesion["token"]
        threading.Thread(
            target=_fundido_y_detener,
            args=(indice, token),
            daemon=True
        ).start()
        return

    _iniciar_reproduccion(indice)


def detener_sonido(indice):
    _detener_local()
    if E._sesion_reproduccion.get("indice") == indice:
        E._sesion_reproduccion["token"] += 1
        mod_ui_soundboard._fijar_pad_activo(None)
    if not E.conectado:
        return
    token = E._sesion_reproduccion.get("token")
    try:
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        )
    except Exception as e:
        print(f"Error deteniendo el efecto: {e}")
    if E._sesion_reproduccion.get("token") == token:
        # Sin reproducción nueva en el medio: se vacía la fuente para
        # que no quede cargado un archivo que OBS reproduciría solo.
        _vaciar_fuente_efectos()


def reiniciar_sonido(indice):
    # El botón de reinicio siempre vuelve a arrancar el sonido desde
    # cero, nunca lo apaga -a diferencia de tocar el pad de nuevo-.
    _iniciar_reproduccion(indice)


def _consultar_estado_reproduccion():
    indice = E._sesion_reproduccion.get("indice")
    if indice is None:
        return
    token = E._sesion_reproduccion.get("token")
    inicio = E._sesion_reproduccion.get("inicio") or 0
    if time.time() - inicio < C.GRACIA_INICIO_REPRODUCCION_SEG:
        return
    try:
        respuesta = E.cliente_obs.get_media_input_status(C.NOMBRE_FUENTE_EFECTOS)
        estado = mod_obs_eventos._valor(respuesta, "media_state", "mediaState")
        dur_ms = mod_obs_eventos._valor(respuesta, "media_duration", "mediaDuration")
    except Exception as e:
        print(f"No se pudo consultar el estado del efecto: {e}")
        return
    if E._sesion_reproduccion.get("token") == token:
        E._sesion_reproduccion["ultimo_estado_obs"] = estado
    # Respaldo de duración desde OBS (por si el decode local falló):
    # viene en ms. Sólo vale si el archivo que OBS tiene cargado es el
    # de ESTA sesión: si no, sería la duración del efecto anterior
    # todavía en transición. Se queda con la MAYOR (una duración local
    # más corta que la real es lo que cortaba la barra antes de
    # tiempo, con el sonido todavía sonando).
    try:
        if dur_ms and float(dur_ms) > 0:
            if E._sesion_reproduccion.get("token") == token and float(dur_ms) > 0:
                try:
                    info_fx = E.cliente_obs.get_input_settings(C.NOMBRE_FUENTE_EFECTOS)
                    aj_fx = mod_obs_eventos._valor(info_fx, "input_settings", "inputSettings") or {}
                    cargado = mod_obs_eventos._valor(aj_fx, "local_file", "localFile")
                except Exception:
                    cargado = None
                try:
                    esperado = E._sesion_reproduccion.get("archivo")
                    esperado_obs = (mod_rutas_obs.resolver_para_obs(esperado)
                                    if esperado else None)
                    ok = bool(cargado and esperado_obs and mod_ui_soundboard._normalizar_ruta(
                        cargado) == mod_ui_soundboard._normalizar_ruta(esperado_obs))
                except Exception:
                    ok = False
                if ok:
                    previa = E._sesion_reproduccion.get("duracion") or 0
                    E._sesion_reproduccion["duracion"] = max(float(previa), float(dur_ms) / 1000.0)
    except Exception:
        pass
    if estado in C.ESTADOS_MEDIA_DETENIDO:
        # Una sola lectura terminal puede ser un eco viejo (el RESTART
        # recién mandado todavía no aplicado en OBS): recién a la
        # TERCERA seguida se da por terminado de verdad. Sin esto la
        # luz (y la barra) se cortaban solas con el audio sonando.
        if E._sesion_reproduccion.get("token") == token:
            if _fin_confirmado.get("token") == token:
                _fin_confirmado["rachas"] += 1
            else:
                _fin_confirmado["token"] = token
                _fin_confirmado["rachas"] = 1
            if _fin_confirmado["rachas"] < 3:
                return
            _fin_confirmado["rachas"] = 0
            # Fin natural con la sesión todavía vigente: se vacía la
            # fuente para que ese archivo no suene solo al abrir OBS.
            _vaciar_fuente_efectos()
        else:
            _fin_confirmado["token"] = None
            _fin_confirmado["rachas"] = 0
            return
        E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))
    else:
        _fin_confirmado["token"] = None
        _fin_confirmado["rachas"] = 0


def _programar_refresco_reproduccion():
    if E.conectado and E._sesion_reproduccion.get("indice") is not None:
        threading.Thread(target=_consultar_estado_reproduccion, daemon=True).start()
    E.ventana.after(C.INTERVALO_REFRESCO_REPRODUCCION_MS, _programar_refresco_reproduccion)
