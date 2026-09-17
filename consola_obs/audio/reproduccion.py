import threading
import time

from tkinter import messagebox

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import configuracion as mod_configuracion
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.ui import soundboard as mod_ui_soundboard

_reproduccion_local = {"dispositivo": None, "token": None}
_aviso_miniaudio = {"mostrado": False}
DURACION_FUNDIDO_LOCAL_SEG = 2.0


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


def _reproducir_local(ruta, token):
    """Reproduce el archivo por la salida de audio de la PC (parlantes /
    auriculares) con miniaudio, en paralelo a OBS. Corre en su propio
    hilo.

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
        return
    _detener_local()
    try:
        flujo = miniaudio.stream_file(ruta)
    except Exception as e:
        print(f"No se pudo abrir el audio local {ruta}: {e}")
        return
    try:
        dispositivo = miniaudio.PlaybackDevice()
    except Exception as e:
        print(f"No se pudo abrir la salida de audio de la PC: {e}")
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
        return
    _reproduccion_local["dispositivo"] = dispositivo
    _reproduccion_local["token"] = token
    _reproduccion_local["cancelar"] = cancelado
    _reproduccion_local.pop("fundido_inicio", None)
    _reproduccion_local.pop("fundido_db", None)
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


def cambiar_escuchar_en_pc(valor):
    """Se llama desde el combobox 'Escuchar acá' del menú de ajustes."""
    E.escuchar_en_pc = (valor == "Sí")
    mod_configuracion.guardar_config_interfaz({"escuchar_en_pc": E.escuchar_en_pc})
    if not E.escuchar_en_pc:
        _detener_local()


def _cargar_y_disparar(indice, accion, token):
    datos = E.config_soundboard.get(str(indice))
    if not datos or not datos.get("archivo"):
        return

    # El audio local sale siempre que esté habilitado, haya o no
    # conexión a OBS: es independiente del trigger de OBS de abajo.
    suena_local = bool(getattr(E, "escuchar_en_pc", True))
    if suena_local:
        threading.Thread(
            target=_reproducir_local,
            args=(datos["archivo"], token),
            daemon=True
        ).start()

    if not E.conectado:
        if not suena_local:
            messagebox.showwarning("Sin conexión", "Conectate a OBS para poder reproducir los efectos.")
        E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))
        return

    try:
        E.cliente_obs.set_input_settings(
            C.NOMBRE_FUENTE_EFECTOS,
            {
                "local_file": datos["archivo"],
                "is_local_file": True,
                "restart_on_activate": False,
                "close_when_inactive": False,
            },
            True
        )
        E.cliente_obs.trigger_media_input_action(C.NOMBRE_FUENTE_EFECTOS, accion)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo reproducir el efecto.\n\n{e}")
        E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))


def _iniciar_reproduccion(indice):
    """Arranca (o reinicia) la reproducción de un pad. Esto SIEMPRE crea
    una sesión nueva, así que si había un fundido en curso de una
    reproducción anterior, ese fundido se va a dar cuenta -por el
    token- de que ya no es el vigente y se va a cancelar solo sin
    tocar este sonido nuevo."""
    E._sesion_reproduccion["token"] += 1
    token = E._sesion_reproduccion["token"]
    E._sesion_reproduccion["inicio"] = time.time()
    mod_ui_soundboard._fijar_pad_activo(indice)
    threading.Thread(
        target=_cargar_y_disparar,
        args=(indice, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART", token),
        daemon=True
    ).start()


def _fundido_y_detener(indice, token, duracion=2.0, pasos=20):
    """Baja el volumen de la fuente de efectos desde su nivel actual
    hasta silencio en 'duracion' segundos y, al llegar abajo, detiene
    el medio. Al final (llegue a terminar o se cancele en el camino)
    siempre deja el volumen tal cual estaba antes de fundir, para que
    la próxima reproducción de cualquier pad vuelva a sonar al nivel
    normal del fader. El pad se apaga recién en ese momento -mientras
    dura el fundido, el sonido técnicamente sigue activo en OBS, así
    que la luz se mantiene prendida hasta el STOP final."""
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
        E.cliente_obs.set_input_volume(C.NOMBRE_FUENTE_EFECTOS, vol_db=vol_inicial)
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
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        )
    except Exception:
        pass
    _vaciar_fuente_efectos()


def reproducir_sonido(indice):
    if E._sesion_reproduccion.get("indice") == indice:
        # Se volvió a apretar el mismo pad mientras sonaba: en vez de
        # reiniciarlo, se apaga con un fundido de volumen de 2 segundos.
        token = E._sesion_reproduccion["token"]
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
    except Exception as e:
        print(f"No se pudo consultar el estado del efecto: {e}")
        return
    if estado in C.ESTADOS_MEDIA_DETENIDO:
        if E._sesion_reproduccion.get("token") == token:
            # Fin natural con la sesión todavía vigente: se vacía la
            # fuente para que ese archivo no suene solo al abrir OBS.
            _vaciar_fuente_efectos()
        E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))


def _programar_refresco_reproduccion():
    if E.conectado and E._sesion_reproduccion.get("indice") is not None:
        threading.Thread(target=_consultar_estado_reproduccion, daemon=True).start()
    E.ventana.after(C.INTERVALO_REFRESCO_REPRODUCCION_MS, _programar_refresco_reproduccion)
