from tkinter import messagebox
import obsws_python as obs

try:
    # obsws-python loguea con traceback CADA request fallido, aunque
    # lo manejemos bien (como los 600 esperables de filtros/principales
    # inexistentes): se silencia al cargar la capa OBS. Nuestros
    # diagnósticos propios (prints, messagebox, conexion.log) siguen.
    import logging
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
except Exception:
    pass

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import configuracion as mod_configuracion
from consola_obs import red as mod_red
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.ui import tarjeta_fuente as mod_ui_tarjeta


class _ClienteOBSSincronizado:
    """Envoltorio fino sobre el ReqClient real: cada llamada a un método
    (get_input_list, set_input_volume, etc.) pasa por _lock_pedidos_obs
    antes de tocar el socket, así nunca hay dos pedidos en simultáneo
    sin importar desde qué hilo se llamen."""

    def __init__(self, cliente_real):
        self._cliente_real = cliente_real

    def __getattr__(self, nombre_attr):
        atributo = getattr(self._cliente_real, nombre_attr)
        if not callable(atributo):
            return atributo

        def _llamada_con_lock(*args, **kwargs):
            with E._lock_pedidos_obs:
                return atributo(*args, **kwargs)

        return _llamada_con_lock


def _leer_fuentes_globales_obs():
    """Los canales de audio 'globales' de OBS (Desktop Audio 1/2, Mic/Aux
    1 a 4, los que se eligen desde Configuración > Audio, no desde una
    escena puntual) no son parte de NINGUNA escena: suenan siempre,
    tanto si la escena al aire los tiene como si no, porque OBS los
    mezcla por canal y no como ítem de escena. Como get_scene_item_list()
    nunca los va a devolver, sin este chequeo aparte el programa no podía
    detectarlos como "activos" y los pintaba en gris permanentemente
    (como si estuvieran fuera de la escena), aunque en realidad sonaran
    siempre. Achican esto tratándolos igual que una fuente 'principal':
    siempre cuentan como en escena."""
    try:
        especiales = E.cliente_obs.get_special_inputs()
    except Exception as e:
        print(f"No se pudieron leer las fuentes de audio globales de OBS: {e}")
        return set()

    nombres = set()
    for campo in ("desktop1", "desktop2", "mic1", "mic2", "mic3", "mic4"):
        nombre = mod_obs_eventos._valor(especiales, campo)
        if nombre:
            nombres.add(nombre)
    return nombres


def _refrescar_membresia_escena():
    """Vuelve a leer qué fuentes están presentes Y activas en la escena
    que está al aire ahora mismo, para poder mostrar en gris las que no
    lo están. Se llama al conectar, al actualizar fuentes, y cada vez
    que la escena activa cambia (evento de OBS)."""
    if not E.conectado:
        return
    try:
        respuesta_escena = E.cliente_obs.get_current_program_scene()
        escena_actual = mod_obs_eventos._valor(
            respuesta_escena,
            "current_program_scene_name", "currentProgramSceneName",
            "scene_name", "sceneName"
        )
        nombres_en_escena = set()
        if escena_actual:
            items = E.cliente_obs.get_scene_item_list(escena_actual).scene_items
            for it in items:
                nombre_item = mod_obs_eventos._valor(it, "source_name", "sourceName")
                habilitado = mod_obs_eventos._valor(it, "scene_item_enabled", "sceneItemEnabled")
                if nombre_item and habilitado:
                    nombres_en_escena.add(nombre_item)
        nombres_en_escena |= _leer_fuentes_globales_obs()
        E.ventana.after(0, lambda: _aplicar_membresia_escena(nombres_en_escena))
    except Exception as e:
        print(f"No se pudo actualizar la escena activa: {e}")


def _aplicar_membresia_escena(nombres_en_escena):
    E.escena_actual_nombres = nombres_en_escena
    E.escena_actual_obtenida = True
    for nombre in list(E.fuentes.keys()):
        mod_ui_tarjeta._actualizar_estado_gris(nombre)


def conectar_obs():

    if E.conectado:
        desconectar_obs()
        return

    host = E.entrada_host.get().strip() or "localhost"
    texto_puerto = E.entrada_puerto.get().strip() or "4455"
    password = E.entrada_password.get()
    paso = "INICIO"

    try:
        puerto = int(texto_puerto)
    except ValueError:
        mod_red.log_conexion("INICIO", f"puerto invalido {texto_puerto!r}")
        messagebox.showerror("Puerto inválido", "El puerto debe ser un número.")
        return

    try:
        _ip_propia = mod_red.obtener_ip_local() or "(no detectada)"
    except Exception:
        _ip_propia = "(no detectada)"
    mod_red.log_conexion("INICIO", f"host={host} puerto={puerto} pass_len={len(password or '')} mi_ip={_ip_propia}")

    # 1) Resolver el host (DNS / IP). Si esto falla, ni se intenta el socket.
    paso = "RESOLVER_HOST"
    try:
        import socket as _socket
        _info = _socket.getaddrinfo(host, puerto, type=_socket.SOCK_STREAM)
        _ips = sorted({x[4][0] for x in _info})
        mod_red.log_conexion("RESOLVER_HOST", f"OK {host} -> {_ips}")
    except Exception as e:
        mod_red.log_conexion("RESOLVER_HOST", f"FALLO no se pudo resolver {host!r}: {e!r}")
        E.conectado = False
        messagebox.showerror(
            "Error de conexión",
            f"No se pudo resolver el Host {host!r}.\nRevisá que sea una IP (ej. 192.168.1.76) o 'localhost'.\n\nDetalle: {e}\n(Más detalle en la terminal y en config/conexion.log)",
        )
        return

    # Firewall automático (mejor esfuerzo, sin frenar la conexión):
    # en la PC del OBS el puerto tiene que estar permitido inbound.
    # Si ya existe la regla no hace nada; si falta y no hay admin,
    # solo queda registrado para avisar en el error.
    paso = "FIREWALL"
    try:
        ok_fw, admin_fw, msg_fw = mod_red.asegurar_regla_firewall(puerto)
        mod_red.log_conexion("FIREWALL", f"ok={ok_fw} necesita_admin={admin_fw} {msg_fw}")
    except Exception as e:
        mod_red.log_conexion("FIREWALL", f"no se pudo chequear: {e!r}")

    try:
        paso = "REQCLIENT_CONNECT"
        mod_red.log_conexion(paso, f"conectando ReqClient a {host}:{puerto} timeout=5 ...")
        nuevo_cliente = obs.ReqClient(host=host, port=puerto, password=password, timeout=5)
        mod_red.log_conexion(paso, "OK socket TCP + handshake websocket")

        paso = "GET_VERSION"
        mod_red.log_conexion(paso, "pidiendo get_version ...")
        _ver = nuevo_cliente.get_version()
        try:
            _vobs = getattr(_ver, "obs_version", "?")
            _vws = getattr(_ver, "obs_websocket_version", "?")
            mod_red.log_conexion(paso, f"OK obs={_vobs} websocket={_vws} (auth correcta)")
        except Exception:
            mod_red.log_conexion(paso, "OK (sin detalle de version)")
        # Plataforma del OBS (windows/linux/macos): sirve para validar
        # la Carpeta OBS (una ruta D:\... en un OBS Linux nunca anda).
        try:
            E.plataforma_obs = str(getattr(_ver, "platform", "") or "").strip().lower()
        except Exception:
            E.plataforma_obs = ""
        if getattr(E, "plataforma_obs", ""):
            mod_red.log_conexion(paso, f"plataforma OBS: {E.plataforma_obs}")
        # Lista de tipos de fuente que trae ese OBS: sirve para elegir
        # kinds creables sin adivinar (y para diagnosticar 605).
        try:
            _rk = nuevo_cliente.get_input_kind_list(True)
            _ks = None
            try:
                _ks = list(getattr(_rk, "input_kinds", None) or [])
            except Exception:
                _ks = None
            if not _ks:
                try:
                    _ks = list(_rk.get("inputKinds", []) or [])
                except Exception:
                    _ks = None
            if _ks:
                mod_red.log_conexion(paso, f"kinds OBS ({len(_ks)}): {sorted(str(k) for k in _ks)}")
        except Exception as e:
            mod_red.log_conexion(paso, f"kinds OBS: no se pudieron listar ({e!r})")

        paso = "EVENTCLIENT_CONNECT"
        mod_red.log_conexion(paso, f"conectando EventClient a {host}:{puerto} ...")
        nuevo_cliente_eventos = obs.EventClient(
            host=host, port=puerto, password=password,
            subs=(
                obs.Subs.LOW_VOLUME | obs.Subs.INPUTVOLUMEMETERS |
                obs.Subs.INPUTS | obs.Subs.SCENES | obs.Subs.SCENEITEMS |
                obs.Subs.FILTERS | obs.Subs.MEDIAINPUTS
            )
        )
        mod_red.log_conexion(paso, "OK")
        paso = "REGISTRO_CALLBACKS"
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_input_volume_meters)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_media_input_playback_started)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_media_input_playback_ended)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_scene_created)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_current_program_scene_changed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_scene_item_enable_state_changed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_scene_item_created)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_scene_item_removed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_input_created)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_input_removed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_input_mute_state_changed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_input_volume_changed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_input_audio_monitor_type_changed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_input_name_changed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_source_filter_created)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_source_filter_removed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_source_filter_enable_state_changed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_source_filter_list_reindexed)
        nuevo_cliente_eventos.callback.register(mod_obs_eventos.on_source_filter_name_changed)

    except Exception as e:
        import traceback as _tb
        try:
            _detalle_tb = "".join(_tb.format_exception(type(e), e, e.__traceback__)).strip()[-2000:]
        except Exception:
            _detalle_tb = ""
        mod_red.log_conexion(paso, f"FALLO en {paso}: {type(e).__name__}: {e}")
        if _detalle_tb:
            mod_red.log_conexion(paso, f"traceback: {_detalle_tb}")
        E.conectado = False
        try:
            texto = mod_red.mensaje_error_conexion(e, host, puerto)
        except Exception:
            texto = f"No se pudo conectar a OBS.\n\n{e}"
        texto += f"\n\n(Falló en paso {paso}. Detalle en la terminal y en config/conexion.log)"
        messagebox.showerror("Error de conexión", texto)
        return

    E.cliente_obs = _ClienteOBSSincronizado(nuevo_cliente)
    E.cliente_eventos = nuevo_cliente_eventos
    E.conectado = True
    E.host_conectado = host
    E._base_aprendida_intentada = False
    E._base_obs_dudosa = False
    E._base_adoptada = False
    try:
        refrescar = getattr(E, "refrescar_hint_base_obs", None)
        if refrescar:
            refrescar()
    except Exception:
        pass
    mod_red.log_conexion("EXITO", f"conectado a {host}:{puerto}, config guardada")

    mod_configuracion.guardar_config_conexion(host, puerto, password)
    _guardar_base_obs_del_campo()
    actualizar_estado_conexion()
    mod_ui_tarjeta.actualizar()


def _guardar_base_obs_del_campo():
    """Guarda la Carpeta OBS del campo, pero NUNCA pisa una base buena
    con un campo vacío (eso borraba lo aprendido solo con reconectar).
    Devuelve lo guardado o None."""
    try:
        texto = (E.entrada_base_obs.get() or "").strip()
    except Exception:
        return None
    if not texto:
        return None
    try:
        mod_configuracion.guardar_config_interfaz({"carpeta_base_obs": texto})
    except Exception:
        return None
    return texto


def _desconectar_solo_red():
    """Suelta los sockets y limpia referencias, SIN tocar widgets (para
    el cierre de la app, que ya destruyó la ventana). Nunca lanza."""
    try:
        from consola_obs.audio import musica as mod_audio_musica
        mod_audio_musica.detener_y_vaciar_musica()
    except Exception:
        pass
    try:
        E.conectado = False
    except Exception:
        pass
    try:
        E.host_conectado = None
    except Exception:
        pass
    try:
        E.plataforma_obs = ""
    except Exception:
        pass
    for cliente in (E.cliente_obs, E.cliente_eventos):
        try:
            if cliente is not None:
                cliente.disconnect()
        except Exception:
            pass
    try:
        E.cliente_obs = None
    except Exception:
        pass
    try:
        E.cliente_eventos = None
    except Exception:
        pass


def desconectar_obs():

    try:
        # La música no puede seguir sonando sin UI que la controle
        # (a diferencia de los efectos, que se dejan como están al
        # desconectar): STOP + vaciado antes de soltar el socket.
        from consola_obs.audio import musica as mod_audio_musica
        mod_audio_musica.detener_y_vaciar_musica()
    except Exception:
        pass

    E.conectado = False
    E.host_conectado = None
    E.plataforma_obs = ""

    for cliente in (E.cliente_obs, E.cliente_eventos):
        try:
            if cliente is not None:
                cliente.disconnect()
        except Exception:
            pass

    E.cliente_obs = None
    E.cliente_eventos = None

    for nombre in list(E.fuentes.keys()):
        E.fuentes[nombre]["tarjeta_sombra"].destroy()
        del E.fuentes[nombre]
    E.niveles_actuales.clear()
    E.niveles_crudos.clear()
    E.niveles_entrada.clear()
    E.niveles_antes_mute.clear()
    E.ultima_vez_saturado.clear()
    E.orden_fuentes.clear()
    E.escena_actual_nombres = set()
    E.escena_actual_obtenida = False

    actualizar_estado_conexion()


def copiar_ip_local():
    """Copia 'mi IP LAN' al portapapeles: es la que hay que poner como
    Host en LA OTRA PC."""
    try:
        ip = mod_red.obtener_ip_local()
    except Exception:
        ip = ""
    if not ip:
        messagebox.showwarning(
            "Sin IP local",
            "No pude detectar una IP de red local.\n"
            "Conectate a la misma WiFi/red y probá de nuevo,\n"
            "o ejecutá 'ipconfig' para ver tu IPv4.",
        )
        return
    try:
        E.ventana.clipboard_clear()
        E.ventana.clipboard_append(ip)
    except Exception:
        pass
    messagebox.showinfo(
        "IP copiada",
        f"Tu IP en esta red es {ip} (copiada).\n\n"
        "En LA OTRA PC poné esa IP en Ajustes → Host.\n"
        "Acá dejá localhost si el OBS está en esta misma PC.",
    )


def abrir_firewall_ahora():
    """Botón '🛡 Firewall': crea la regla inbound para el puerto actual."""
    try:
        texto_puerto = E.entrada_puerto.get().strip() or "4455"
        puerto = int(texto_puerto)
    except ValueError:
        messagebox.showerror("Puerto inválido", "El puerto debe ser un número.")
        return
    ok, necesita_admin, mensaje = mod_red.asegurar_regla_firewall(puerto)
    if ok:
        messagebox.showinfo("Firewall", mensaje)
    elif necesita_admin:
        messagebox.showwarning(
            "Hace falta administrador",
            f"{mensaje}\n\n"
            "Cerrá el programa y abrilo con 'Ejecutar como administrador',\n"
            f"apretá CONECTAR o el botón Firewall una vez, y listo.\n"
            f"(Puerto {puerto} TCP entrante).",
        )
    else:
        messagebox.showerror("Firewall", mensaje)


def actualizar_estado_conexion():
    if E.conectado:
        E.estado.config(text="● CONECTADO", fg=E.color_acento())
        E.estado_chip.config(highlightbackground=E.color_acento())
        E.boton_conectar.config(text="DESCONECTAR", bg="#ff5567", activebackground="#cb3542")
    else:
        E.estado.config(text="● DESCONECTADO", fg="#ff5d6c")
        E.estado_chip.config(highlightbackground="#3f4a5e")
        E.boton_conectar.config(text="CONECTAR", bg=E.color_acento(), activebackground=E.color_acento_claro())


def _sesion_efecto_activa():
    """Hay un efecto sonando o apagándose (la sesión es dueña del
    transporte): el refresco no debe tocarlo."""
    try:
        return E._sesion_reproduccion.get("indice") is not None
    except Exception:
        return False


def _musica_ociosa():
    """True si la música está detenida (se puede ordenar sin pisar
    nada). Sonando/pausada/abriendo: manos afuera (vaciarle el archivo
    la pausaría y perdería la posición)."""
    try:
        from consola_obs.audio import musica as mod_audio_musica
        return mod_audio_musica._sesion.get("estado") == "DETENIDA"
    except Exception:
        return True


def _asegurar_fuente_en_todas_las_escenas(nombre_fuente):
    """Se asegura de que 'nombre_fuente' esté presente Y ACTIVA en TODAS
    las escenas de OBS: si falta en alguna, se agrega; si está pero
    deshabilitada ('ojito' apagado), se habilita. Se usa tanto para la
    fuente interna de efectos como para las fuentes marcadas como
    'principales'. Serializada con _lock_sincronizar_escenas (ver más
    arriba) para que no se pueda ejecutar en paralelo con otra operación
    del mismo tipo y terminar creando la fuente dos veces en la misma
    escena."""
    if not E.conectado:
        return
    with E._lock_sincronizar_escenas:
        try:
            escenas = [mod_obs_eventos._valor(e, "scene_name", "sceneName") for e in E.cliente_obs.get_scene_list().scenes]
        except Exception as e:
            print(f"No se pudieron listar las escenas: {e}")
            return

        # La fuente tiene que EXISTIR como input para poder meterla en
        # escenas: si se borró/renombró fuera (caso típico: un principal
        # viejo como 'Audio escritorio'), cada create_scene_item
        # devolvía 600 spameando el log en cada conexión. Se poda de
        # principales con aviso, una sola vez.
        try:
            entradas = [mod_obs_eventos._valor(i, "input_name", "inputName")
                        for i in E.cliente_obs.get_input_list().inputs]
        except Exception as e:
            print(f"No se pudieron listar las entradas: {e}")
            return
        if nombre_fuente not in entradas:
            print(f"'{nombre_fuente}' no existe en OBS: no se puede asegurar en escenas.")
            if nombre_fuente in E.fuentes_principales:
                E.fuentes_principales.discard(nombre_fuente)
                try:
                    mod_configuracion.guardar_config_interfaz(
                        {"fuentes_principales": sorted(E.fuentes_principales)})
                except Exception:
                    pass
                print(f"'{nombre_fuente}' se quitó de fuentes principales.")
            return

        for escena in escenas:
            if not escena:
                continue
            try:
                items = E.cliente_obs.get_scene_item_list(escena).scene_items
                item_existente = None
                for it in items:
                    if mod_obs_eventos._valor(it, "source_name", "sourceName") == nombre_fuente:
                        item_existente = it
                        break

                if item_existente is None:
                    E.cliente_obs.create_scene_item(escena, nombre_fuente, True)
                else:
                    habilitado = mod_obs_eventos._valor(item_existente, "scene_item_enabled", "sceneItemEnabled")
                    if not habilitado:
                        item_id = mod_obs_eventos._valor(item_existente, "scene_item_id", "sceneItemId")
                        if item_id is not None:
                            E.cliente_obs.set_scene_item_enabled(escena, item_id, True)
            except Exception as e:
                print(f"No se pudo asegurar '{nombre_fuente}' en la escena '{escena}': {e}")


def quitar_fuente_de_todas_las_escenas(nombre_fuente):
    """Inverso de _asegurar_fuente_en_todas_las_escenas: saca
    'nombre_fuente' de TODAS las escenas (RemoveSceneItem por cada
    ítem de primer nivel que la referencie) SIN borrar el input de
    OBS: la fuente sigue existiendo y se puede volver a agregar a
    cualquier escena desde OBS. Sólo cubre ítems de primer nivel (no
    los anidados dentro de grupos). Serializada con
    _lock_sincronizar_escenas como su contraparte. Devuelve en
    cuántas escenas estaba."""
    quitadas = 0
    if not E.conectado:
        return quitadas
    with E._lock_sincronizar_escenas:
        try:
            escenas = [mod_obs_eventos._valor(e, "scene_name", "sceneName") for e in E.cliente_obs.get_scene_list().scenes]
        except Exception as e:
            print(f"No se pudieron listar las escenas: {e}")
            return quitadas
        for escena in escenas:
            if not escena:
                continue
            try:
                items = E.cliente_obs.get_scene_item_list(escena).scene_items
            except Exception as e:
                print(f"No se pudieron listar los ítems de '{escena}': {e}")
                continue
            for it in items:
                try:
                    if mod_obs_eventos._valor(it, "source_name", "sourceName") != nombre_fuente:
                        continue
                    item_id = mod_obs_eventos._valor(it, "scene_item_id", "sceneItemId")
                    if item_id is None:
                        continue
                    E.cliente_obs.remove_scene_item(escena, item_id)
                    quitadas += 1
                except Exception as e:
                    print(f"No se pudo quitar '{nombre_fuente}' de '{escena}': {e}")
    return quitadas


def asegurar_fuentes_principales_en_todas_las_escenas():
    """Antes esto igualaba TODAS las fuentes de audio en TODAS las
    escenas (invasivo: tocaba escenas del usuario sin que lo pidiera).
    Ahora sólo se hace con las fuentes marcadas explícitamente como
    'principales' (ver _alternar_principal); el resto de las fuentes
    sólo se muestran (grises si no están en la escena activa)."""
    for nombre in list(E.fuentes_principales):
        _asegurar_fuente_en_todas_las_escenas(nombre)


def preparar_fuente_efectos():
    """Crea (si hace falta) la fuente compartida del soundboard y se
    asegura de que esté presente en todas las escenas. Serializada con
    _lock_sincronizar_escenas: si esto se dispara dos veces casi al
    mismo tiempo (por ejemplo al crear una escena nueva, que dispara
    esta misma función Y, por separado, la de las fuentes "principales"
    — ver on_scene_created), sin este lock las dos podían preguntar "¿ya
    existe la fuente de efectos en la escena nueva?" al mismo tiempo,
    recibir "no" las dos, y terminar creándola dos veces: de ahí salían
    las dos "Soundboard_Efectos" duplicadas e idénticas en la escena
    recién creada, aunque esa fuente no esté (ni se pueda estar) marcada
    con la estrella. Con el lock, la segunda espera a que la primera
    termine y ya la encuentra creada."""
    if not E.conectado:
        return

    with E._lock_sincronizar_escenas:
        try:
            escenas = [
                mod_obs_eventos._valor(e, "scene_name", "sceneName")
                for e in E.cliente_obs.get_scene_list().scenes
            ]
            escenas = [e for e in escenas if e]

            if not escenas:
                return

            entradas = [
                mod_obs_eventos._valor(i, "input_name", "inputName")
                for i in E.cliente_obs.get_input_list().inputs
            ]

            if C.NOMBRE_FUENTE_EFECTOS not in entradas:
                E.cliente_obs.create_input(
                    escenas[0],
                    C.NOMBRE_FUENTE_EFECTOS,
                    "ffmpeg_source",
                    C.AJUSTES_FUENTE_EFECTOS,
                    True
                )
                try:
                    E.cliente_obs.trigger_media_input_action(
                        C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
                    )
                except Exception:
                    pass
            else:
                # Fuente existente: solo se ordena a vacío si NO hay
                # sesión activa (si no, mataríamos el efecto en curso
                # cada vez que se refresca, ej al agregar una fuente).
                if not _sesion_efecto_activa():
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
                        print(f"No se pudo ajustar 'restart_on_activate': {e}")

            for escena in escenas:
                try:
                    items = E.cliente_obs.get_scene_item_list(
                        escena
                    ).scene_items

                    nombres_en_escena = [
                        mod_obs_eventos._valor(it, "source_name", "sourceName")
                        for it in items
                    ]

                    if C.NOMBRE_FUENTE_EFECTOS not in nombres_en_escena:
                        E.cliente_obs.create_scene_item(
                            escena,
                            C.NOMBRE_FUENTE_EFECTOS,
                            True
                        )
                        try:
                            E.cliente_obs.trigger_media_input_action(
                                C.NOMBRE_FUENTE_EFECTOS,
                                "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
                            )
                        except Exception:
                            pass

                except Exception as e:
                    print(
                        f"No se pudo agregar la fuente de efectos a "
                        f"'{escena}': {e}"
                    )

            if not _sesion_efecto_activa():
                try:
                    E.cliente_obs.trigger_media_input_action(
                        C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
                    )
                except Exception:
                    pass

        except Exception as e:
            print(
                f"No se pudo preparar la fuente de efectos: {e}"
            )


def preparar_fuente_musica():
    """Espejo de preparar_fuente_efectos para la música de fondo
    (Fase 1 del plan de música): crea la fuente 'Musica'
    (ffmpeg_source, sin loop propio) si falta y la asegura presente en
    todas las escenas, arrancando detenida y vacía. El programa es el
    dueño del transporte (qué tema suena y en qué momento); OBS solo
    ejecuta. Serializada con _lock_sincronizar_escenas por el mismo
    motivo que la de efectos (evitar duplicados si dos hilos la piden
    a la vez, por ejemplo al crear una escena nueva)."""
    if not E.conectado:
        return

    with E._lock_sincronizar_escenas:
        try:
            escenas = [
                mod_obs_eventos._valor(e, "scene_name", "sceneName")
                for e in E.cliente_obs.get_scene_list().scenes
            ]
            escenas = [e for e in escenas if e]

            if not escenas:
                return

            entradas = [
                mod_obs_eventos._valor(i, "input_name", "inputName")
                for i in E.cliente_obs.get_input_list().inputs
            ]

            if C.NOMBRE_FUENTE_MUSICA not in entradas:
                E.cliente_obs.create_input(
                    escenas[0],
                    C.NOMBRE_FUENTE_MUSICA,
                    "ffmpeg_source",
                    C.AJUSTES_FUENTE_MUSICA,
                    True
                )
                try:
                    E.cliente_obs.trigger_media_input_action(
                        C.NOMBRE_FUENTE_MUSICA, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
                    )
                except Exception:
                    pass
            else:
                # Fuente existente: solo se vacía si la música está
                # detenida (vaciarla sonando la pausa y pierde la
                # posición: era el bug de "agregar fuente corta la
                # música").
                if _musica_ociosa():
                    try:
                        E.cliente_obs.set_input_settings(
                            C.NOMBRE_FUENTE_MUSICA,
                            {
                                "local_file": "",
                                "looping": False,
                                "restart_on_activate": False,
                                "close_when_inactive": False,
                            },
                            True
                        )
                    except Exception as e:
                        print(f"No se pudo ajustar la fuente de música: {e}")

            for escena in escenas:
                try:
                    items = E.cliente_obs.get_scene_item_list(
                        escena
                    ).scene_items

                    nombres_en_escena = [
                        mod_obs_eventos._valor(it, "source_name", "sourceName")
                        for it in items
                    ]

                    if C.NOMBRE_FUENTE_MUSICA not in nombres_en_escena:
                        E.cliente_obs.create_scene_item(
                            escena,
                            C.NOMBRE_FUENTE_MUSICA,
                            True
                        )
                        try:
                            E.cliente_obs.trigger_media_input_action(
                                C.NOMBRE_FUENTE_MUSICA,
                                "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
                            )
                        except Exception:
                            pass

                except Exception as e:
                    print(
                        f"No se pudo agregar la fuente de música a "
                        f"'{escena}': {e}"
                    )

            if _musica_ociosa():
                try:
                    E.cliente_obs.trigger_media_input_action(
                        C.NOMBRE_FUENTE_MUSICA, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
                    )
                except Exception:
                    pass

        except Exception as e:
            print(
                f"No se pudo preparar la fuente de música: {e}"
            )


def preparar_fuentes_en_todas_las_escenas():
    """OBSOLETA a propósito: antes esto forzaba TODAS las fuentes de
    audio a existir en TODAS las escenas, lo cual era invasivo (tocaba
    escenas del usuario sin que lo pidiera explícitamente). Ahora sólo
    se muestran (en gris si no están en la escena al aire) y sólo se
    fuerzan a todas las escenas las que el usuario marca como
    'principales' — ver asegurar_fuentes_principales_en_todas_las_escenas().
    Se deja esta función vacía (en vez de borrarla) por si algo viejo
    todavía la llama."""
    pass
