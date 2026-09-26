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
    que la escena activa cambia (evento de OBS). Con generación: si dos
    refrescos se enciman, el viejo no pisa al nuevo. Cada paso tolera
    fallos por separado para no abortar todo."""
    if not E.conectado:
        return
    try:
        E._gen_membresia_escena = int(getattr(E, "_gen_membresia_escena", 0) or 0) + 1
        gen = E._gen_membresia_escena
    except Exception:
        gen = None
    try:
        respuesta_escena = E.cliente_obs.get_current_program_scene()
        escena_actual = mod_obs_eventos._valor(
            respuesta_escena,
            "current_program_scene_name", "currentProgramSceneName",
            "scene_name", "sceneName"
        )
    except Exception as e:
        print(f"No se pudo actualizar la escena activa: {e}")
        return
    try:
        E.escena_actual_nombre = escena_actual or ""
    except Exception:
        pass
    nombres_en_escena = set()
    orden_escena = []
    if escena_actual:
        try:
            respuesta_items = E.cliente_obs.get_scene_item_list(escena_actual)
            items = mod_obs_eventos._valor(respuesta_items, "scene_items", "sceneItems") or []
        except Exception as e:
            print(f"No se pudieron listar los ítems de '{escena_actual}': {e}")
            items = []
        for it in items or []:
            try:
                nombre_item = mod_obs_eventos._valor(it, "source_name", "sourceName")
                habilitado = mod_obs_eventos._valor(it, "scene_item_enabled", "sceneItemEnabled")
            except Exception:
                continue
            if not nombre_item:
                continue
            if nombre_item not in orden_escena:
                orden_escena.append(nombre_item)
            if habilitado:
                nombres_en_escena.add(nombre_item)
    try:
        globales = _leer_fuentes_globales_obs()
    except Exception:
        globales = set()
    try:
        nombres_en_escena |= globales
    except Exception:
        pass
    try:
        for g in sorted(globales or set()):
            if g not in orden_escena:
                orden_escena.append(g)
    except Exception:
        pass
    # Modo estudio: la preview también suena al lado del programa.
    try:
        en_estudio = False
        try:
            resp_estudio = E.cliente_obs.get_studio_mode_enabled()
            en_estudio = bool(mod_obs_eventos._valor(resp_estudio, "studio_mode_enabled", "studioModeEnabled"))
        except Exception:
            en_estudio = False
        if en_estudio:
            try:
                resp_previa = E.cliente_obs.get_current_preview_scene()
                escena_previa = mod_obs_eventos._valor(
                    resp_previa, "current_preview_scene_name", "currentPreviewSceneName",
                    "scene_name", "sceneName")
            except Exception:
                escena_previa = None
            if escena_previa and escena_previa != escena_actual:
                try:
                    resp_items = E.cliente_obs.get_scene_item_list(escena_previa)
                    items_prev = mod_obs_eventos._valor(resp_items, "scene_items", "sceneItems") or []
                except Exception:
                    items_prev = []
                for it in items_prev or []:
                    try:
                        nm = mod_obs_eventos._valor(it, "source_name", "sourceName")
                        hab = mod_obs_eventos._valor(it, "scene_item_enabled", "sceneItemEnabled")
                    except Exception:
                        continue
                    if not nm:
                        continue
                    if nm not in orden_escena:
                        orden_escena.append(nm)
                    if hab:
                        nombres_en_escena.add(nm)
    except Exception:
        pass
    try:
        mod_red.log_conexion("FUENTES", f"escena '{escena_actual}': "
                             f"{len(orden_escena)} ítems, {len(nombres_en_escena)} activos")
    except Exception:
        pass
    try:
        if gen is not None and int(getattr(E, "_gen_membresia_escena", 0) or 0) != gen:
            return
    except Exception:
        pass
    try:
        E.ventana.after(0, lambda: _aplicar_membresia_escena(nombres_en_escena, orden_escena))
    except Exception:
        pass
    # La escena al aire cambió (o se releyó): las internas tienen que
    # estar ahí para que efectos/música suenen. En hilo aparte porque
    # este camino también lo usa la vigilancia desde el hilo de UI.
    try:
        import threading as _th
        _th.Thread(target=asegurar_internas_en_escena_actual, daemon=True).start()
    except Exception:
        pass


def _aplicar_membresia_escena(nombres_en_escena, orden_escena=None):
    E.escena_actual_nombres = nombres_en_escena
    E.escena_actual_obtenida = True
    try:
        E.orden_escena_actual = list(orden_escena or [])
    except Exception:
        pass
    for nombre in list(E.fuentes.keys()):
        try:
            mod_ui_tarjeta._actualizar_estado_gris(nombre)
        except Exception:
            pass
    try:
        mod_ui_tarjeta._refrescar_titulo_escena()
    except Exception:
        pass
    try:
        mod_ui_tarjeta._reubicar_si_orden_dinamico()
    except Exception:
        pass


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


def _nombre_programa_actual():
    """Nombre de la escena que está al aire ahora mismo ('' si no se
    puede leer). El audio sólo sale por esa escena: es la única que el
    programa necesita tocar."""
    try:
        respuesta = E.cliente_obs.get_current_program_scene()
        return mod_obs_eventos._valor(
            respuesta, "current_program_scene_name", "currentProgramSceneName",
            "scene_name", "sceneName") or ""
    except Exception as e:
        print(f"No se pudo leer la escena activa: {e}")
        return ""


def _escena_permitida(nombre_escena):
    """True si la escena está tildada en la lista blanca (sólo ahí
    pueden estar Efectos/Música). Lista vacía = ninguna (cierra por
    defecto). Pura respecto a red (lee sólo memoria). Nunca lanza."""
    try:
        return bool(nombre_escena) and nombre_escena in (
            getattr(E, "escenas_permitidas", None) or set())
    except Exception:
        return False


def programa_actual_permitido():
    """True si la escena que está al aire AHORA está permitida (lectura
    en vivo: sólo para hilos, nunca desde el hilo de UI)."""
    try:
        return _escena_permitida(_nombre_programa_actual())
    except Exception:
        return False


def _asegurar_item_en_escena(nombre_fuente, escena):
    """Asegura el ÍTEM de una fuente (que ya existe como input) en UNA
    escena puntual: si falta se agrega activado; si está deshabilitado
    ('ojito' apagado) se habilita. No crea inputs ni toca ninguna otra
    escena. Sólo en escenas permitidas (en las demás devuelve False sin
    tocar nada). Serializada con _lock_sincronizar_escenas para no
    duplicar el ítem si dos hilos la piden a la vez. Devuelve True si
    quedó bien."""
    if not E.conectado or not escena or not nombre_fuente:
        return False
    if not _escena_permitida(escena):
        return False
    with E._lock_sincronizar_escenas:
        try:
            items = E.cliente_obs.get_scene_item_list(escena).scene_items
        except Exception as e:
            print(f"No se pudieron listar los ítems de '{escena}': {e}")
            return False
        item_existente = None
        for it in items or []:
            try:
                if mod_obs_eventos._valor(it, "source_name", "sourceName") == nombre_fuente:
                    item_existente = it
                    break
            except Exception:
                continue
        try:
            if item_existente is None:
                E.cliente_obs.create_scene_item(escena, nombre_fuente, True)
            elif not mod_obs_eventos._valor(item_existente, "scene_item_enabled", "sceneItemEnabled"):
                item_id = mod_obs_eventos._valor(item_existente, "scene_item_id", "sceneItemId")
                if item_id is not None:
                    E.cliente_obs.set_scene_item_enabled(escena, item_id, True)
        except Exception as e:
            print(f"No se pudo asegurar '{nombre_fuente}' en '{escena}': {e}")
            return False
    return True


def asegurar_interna_en_escena_actual(nombre_fuente, kind, ajustes):
    """Asegura una fuente INTERNA (Efectos/Música) en la escena que está
    al aire AHORA: si el input no existe se crea ahí; si existe pero le
    falta el ítem, se agrega activado. NUNCA toca otras escenas, y sólo
    si la del aire está permitida (si no, no se hace nada y devuelve
    False: lo no tildado no se toca por más que esté al aire). Devuelve
    True si quedó bien."""
    if not E.conectado:
        return False
    escena = _nombre_programa_actual()
    if not escena or not _escena_permitida(escena):
        return False
    with E._lock_sincronizar_escenas:
        try:
            entradas = [mod_obs_eventos._valor(i, "input_name", "inputName")
                        for i in E.cliente_obs.get_input_list().inputs]
        except Exception as e:
            print(f"No se pudieron listar las entradas: {e}")
            return False
        if nombre_fuente not in entradas:
            try:
                E.cliente_obs.create_input(escena, nombre_fuente, kind, ajustes, True)
            except Exception as e:
                print(f"No se pudo crear '{nombre_fuente}': {e}")
                return False
    return _asegurar_item_en_escena(nombre_fuente, escena)


def asegurar_internas_en_escena_actual():
    """Efectos + Música presentes y activas en la escena al aire
    (barato e idempotente). Para llamar al cambiar de escena o antes de
    disparar, sin tocar ninguna otra escena."""
    try:
        escena = _nombre_programa_actual()
    except Exception:
        return
    if not escena:
        return
    try:
        _asegurar_item_en_escena(C.NOMBRE_FUENTE_EFECTOS, escena)
    except Exception:
        pass
    try:
        _asegurar_item_en_escena(C.NOMBRE_FUENTE_MUSICA, escena)
    except Exception:
        pass


def quitar_internas_de_otras_escenas():
    """Limpieza para escenas ya 'contaminadas' por el modo anterior
    (que metía Efectos/Música en todas): quita esos ítems de TODAS las
    escenas SALVO la que está al aire. Los inputs NO se borran (siguen
    existiendo para usarse donde corresponde). Sólo ítems de primer
    nivel. Devuelve (programa, quitadas)."""
    if not E.conectado:
        return "", 0
    programa = _nombre_programa_actual()
    quitadas = 0
    with E._lock_sincronizar_escenas:
        try:
            escenas = [mod_obs_eventos._valor(e, "scene_name", "sceneName")
                       for e in E.cliente_obs.get_scene_list().scenes]
        except Exception as e:
            print(f"No se pudieron listar las escenas: {e}")
            return programa, quitadas
        for escena in escenas:
            if not escena or escena == programa:
                continue
            try:
                items = E.cliente_obs.get_scene_item_list(escena).scene_items
            except Exception as e:
                print(f"No se pudieron listar los ítems de '{escena}': {e}")
                continue
            for it in items or []:
                try:
                    if mod_obs_eventos._valor(it, "source_name", "sourceName") not in (
                            C.NOMBRE_FUENTE_EFECTOS, C.NOMBRE_FUENTE_MUSICA):
                        continue
                    item_id = mod_obs_eventos._valor(it, "scene_item_id", "sceneItemId")
                    if item_id is None:
                        continue
                    E.cliente_obs.remove_scene_item(escena, item_id)
                    quitadas += 1
                except Exception as e:
                    print(f"No se pudo limpiar '{escena}': {e}")
    return programa, quitadas


def quitar_fuente_de_todas_las_escenas(nombre_fuente):
    """Saca 'nombre_fuente' de TODAS las escenas (RemoveSceneItem por
    cada ítem de primer nivel que la referencie) SIN borrar el input de
    OBS: la fuente sigue existiendo y se puede volver a agregar a
    cualquier escena desde OBS. Sólo cubre ítems de primer nivel (no
    los anidados dentro de grupos). Serializada con
    _lock_sincronizar_escenas. Devuelve en cuántas escenas estaba."""
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
    """OBSOLETA a propósito: las 'principales' son sólo resaltado visual
    (borde + criterio de orden). Ya no se fuerza ninguna fuente en
    ninguna escena: las escenas especiales (cámaras, capturas) no se
    tocan nunca. Se deja vacía (en vez de borrarla) por si algo viejo
    todavía la llama."""
    pass


def preparar_fuente_efectos():
    """Deja lista la fuente compartida del soundboard, SÓLO en la escena
    que está al aire: si no existe se crea ahí; si existe se la ordena a
    vacío/detenida (sólo sin efecto en curso, para no matar lo que suena
    cada vez que se refresca). Las demás escenas no se tocan: las de
    cámaras o capturas quedan intactas. Serializada (vía
    asegurar_interna_en_escena_actual) para no duplicarla si dos hilos
    la piden a la vez."""
    if not E.conectado:
        return
    try:
        asegurar_interna_en_escena_actual(
            C.NOMBRE_FUENTE_EFECTOS, "ffmpeg_source", C.AJUSTES_FUENTE_EFECTOS)
    except Exception as e:
        print(f"No se pudo preparar la fuente de efectos: {e}")
        return
    # STOP de orden: solo sin sesión activa (con un efecto en curso
    # lo mataría: era parte del bug de "agregar fuente corta todo").
    if _sesion_efecto_activa():
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
        print(f"No se pudo ajustar 'restart_on_activate': {e}")
    try:
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_EFECTOS, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        )
    except Exception:
        pass


def preparar_fuente_musica():
    """Espejo de preparar_fuente_efectos para la música de fondo: crea
    la fuente 'Musica' (ffmpeg_source, sin loop propio) si falta, SÓLO
    en la escena al aire, arrancando detenida y vacía. El programa es el
    dueño del transporte (qué tema suena y en qué momento); OBS solo
    ejecuta. Las demás escenas no se tocan."""
    if not E.conectado:
        return
    try:
        asegurar_interna_en_escena_actual(
            C.NOMBRE_FUENTE_MUSICA, "ffmpeg_source", C.AJUSTES_FUENTE_MUSICA)
    except Exception as e:
        print(f"No se pudo preparar la fuente de música: {e}")
        return
    # Fuente existente: solo se vacía si la música está detenida
    # (vaciarla sonando la pausa y pierde la posición: era el bug de
    # "agregar fuente corta la música").
    if not _musica_ociosa():
        return
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
    try:
        E.cliente_obs.trigger_media_input_action(
            C.NOMBRE_FUENTE_MUSICA, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP"
        )
    except Exception:
        pass


def preparar_fuentes_en_todas_las_escenas():
    """OBSOLETA a propósito: antes esto forzaba TODAS las fuentes de
    audio a existir en TODAS las escenas, lo cual era invasivo (tocaba
    escenas del usuario sin que lo pidiera explícitamente, y rompía
    escenas especiales de cámaras o capturas). Ahora no se fuerza NADA
    en ninguna escena salvo las internas (Efectos/Música) y sólo en la
    escena al aire — ver asegurar_interna_en_escena_actual().
    Se deja esta función vacía (en vez de borrarla) por si algo viejo
    todavía la llama."""
    pass
