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


def _detener_local(token=None):
    """Corta el sonido que esté saliendo por la PC. Si se pasa un token,
    sólo lo corta cuando sigue siendo la sesión vigente (para que el
    fundido de una sesión vieja no corte el sonido nuevo)."""
    if token is not None and _reproduccion_local.get("token") != token:
        return
    cancelado = _reproduccion_local.pop("cancelar", None)
    if cancelado is not None:
        try:
            cancelado.set()
        except Exception:
            pass
    dispositivo = _reproduccion_local.pop("dispositivo", None)
    _reproduccion_local["token"] = None
    if dispositivo is None:
        return
    try:
        dispositivo.stop()
    except Exception:
        pass
    try:
        dispositivo.close()
    except Exception:
        pass


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


def _fundido_y_detener(indice, token, duracion=1.0, pasos=20):
    """Baja el volumen de la fuente de efectos desde su nivel actual
    hasta silencio en 'duracion' segundos y, al llegar abajo, detiene
    el medio. Al final (llegue a terminar o se cancele en el camino)
    siempre deja el volumen tal cual estaba antes de fundir, para que
    la próxima reproducción de cualquier pad vuelva a sonar al nivel
    normal del fader. El pad se apaga recién en ese momento -mientras
    dura el fundido, el sonido técnicamente sigue activo en OBS, así
    que la luz se mantiene prendida hasta el STOP final."""
    if not E.conectado:
        _detener_local()
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


def reproducir_sonido(indice):
    if E._sesion_reproduccion.get("indice") == indice:
        # Se volvió a apretar el mismo pad mientras sonaba: en vez de
        # reiniciarlo, se apaga con un fundido de volumen de 1 segundo.
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
    try:
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        )
    except Exception as e:
        print(f"Error deteniendo el efecto: {e}")


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
        E.ventana.after(0, lambda: mod_ui_soundboard._apagar_pad_si_token_vigente(indice, token))


def _programar_refresco_reproduccion():
    if E.conectado and E._sesion_reproduccion.get("indice") is not None:
        threading.Thread(target=_consultar_estado_reproduccion, daemon=True).start()
    E.ventana.after(C.INTERVALO_REFRESCO_REPRODUCCION_MS, _programar_refresco_reproduccion)
