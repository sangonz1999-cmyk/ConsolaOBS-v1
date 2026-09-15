import tkinter as tk

from tkinter import messagebox, ttk

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs.obs import eventos as mod_obs_eventos


def _filtros_de_sonido_disponibles(tipos_que_ofrece_obs):
    """Cruza el catálogo fijo de arriba con lo que esta instancia de OBS
    realmente tiene registrado (cliente_obs.get_source_filter_kind_list),
    para no ofrecer un filtro que esa versión de OBS no trae. Devuelve
    una lista de (nombre, ícono, kind_real_a_usar)."""
    disponibles = set(tipos_que_ofrece_obs)
    opciones = []
    for nombre, icono, kinds_posibles in E.FILTROS_DE_SONIDO_PERMITIDOS:
        kind_real = next((k for k in kinds_posibles if k in disponibles), None)
        if kind_real:
            opciones.append((nombre, icono, kind_real))
    return opciones


def _abrir_selector_nuevo_filtro(nombre_fuente, al_crear=None):
    """Ventana simple para elegir QUÉ filtro agregar, sólo con los
    filtros de audio que le sirven a un sonidista (ver
    FILTROS_DE_SONIDO_PERMITIDOS), con nombre entendible e ícono por
    tipo, tal como el menú "+" de la lista de filtros dentro de OBS. Al
    confirmar, crea el filtro en OBS con la configuración por defecto
    que trae ese tipo y, si se pasó 'al_crear', lo llama con el nombre
    final del filtro (para, por ejemplo, abrirle el editor de ajustes en
    el acto)."""
    if not E.conectado:
        return

    try:
        respuesta_tipos = E.cliente_obs.get_source_filter_kind_list()
        tipos = mod_obs_eventos._valor(respuesta_tipos, "source_filter_kinds", "sourceFilterKinds") or []
    except Exception as e:
        messagebox.showerror(
            "Error",
            f"No se pudo obtener la lista de tipos de filtro disponibles.\n\n{e}"
        )
        return

    opciones = _filtros_de_sonido_disponibles(tipos)

    if not opciones:
        messagebox.showinfo(
            "Sin filtros disponibles",
            "Esta versión de OBS no informó ninguno de los filtros de audio esperados."
        )
        return

    nombre_por_kind = {kind: nombre for nombre, _icono, kind in opciones}
    icono_por_kind = {kind: icono for nombre, icono, kind in opciones}

    selector = tk.Toplevel(E.ventana)
    selector.title("Agregar filtro")
    selector.configure(bg="#10141b")
    selector.geometry("360x460")
    selector.transient(E.ventana)
    selector.grab_set()

    tk.Label(
        selector, text=f"Nuevo filtro para: {nombre_fuente}", bg="#10141b", fg="white",
        font=(E.FUENTE_UI, 11, "bold"), wraplength=330, justify="left"
    ).pack(anchor="w", padx=12, pady=(12, 2))

    tk.Label(
        selector, text="Elegí el tipo de filtro:", bg="#10141b", fg="#8e9ab3",
        font=(E.FUENTE_UI, 9)
    ).pack(anchor="w", padx=12, pady=(4, 4))

    marco_scroll = tk.Frame(selector, bg="#10141b")
    marco_scroll.pack(fill="both", expand=True, padx=12)

    canvas_tipos = tk.Canvas(marco_scroll, bg="#10141b", highlightthickness=0)
    scrollbar_tipos = ttk.Scrollbar(marco_scroll, orient="vertical", command=canvas_tipos.yview)
    marco_lista_tipos = tk.Frame(canvas_tipos, bg="#10141b")
    marco_lista_tipos.bind(
        "<Configure>", lambda e: canvas_tipos.configure(scrollregion=canvas_tipos.bbox("all"))
    )
    id_ventana_tipos = canvas_tipos.create_window((0, 0), window=marco_lista_tipos, anchor="nw")
    canvas_tipos.bind(
        "<Configure>", lambda e: canvas_tipos.itemconfig(id_ventana_tipos, width=e.width)
    )
    canvas_tipos.configure(yscrollcommand=scrollbar_tipos.set)
    canvas_tipos.pack(side="left", fill="both", expand=True)
    scrollbar_tipos.pack(side="right", fill="y")

    primer_kind = opciones[0][2]
    var_tipo_elegido = tk.StringVar(value=primer_kind)

    for nombre_amigable, icono, kind in opciones:
        tk.Radiobutton(
            marco_lista_tipos, text=f"{icono}  {nombre_amigable}", value=kind,
            variable=var_tipo_elegido, bg="#10141b", fg="white",
            activebackground="#1c2331", activeforeground="white",
            selectcolor="#1a202b", font=(E.FUENTE_UI, 10), anchor="w",
            justify="left", indicatoron=True, padx=6, pady=5
        ).pack(fill="x")

    marco_nombre = tk.Frame(selector, bg="#10141b")
    marco_nombre.pack(fill="x", padx=12, pady=(8, 4))
    tk.Label(
        marco_nombre, text="Nombre del filtro:", bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)
    ).pack(anchor="w")
    var_nombre_filtro = tk.StringVar(value=nombre_por_kind[primer_kind])
    entrada_nombre_filtro = tk.Entry(
        marco_nombre, textvariable=var_nombre_filtro, bg="#1a202b", fg="white",
        insertbackground="white", relief="flat", font=(E.FUENTE_UI, 9)
    )
    entrada_nombre_filtro.pack(fill="x", ipady=3)

    _ultimo_sugerido = {"texto": var_nombre_filtro.get()}

    def _al_cambiar_tipo(*_ignorar):
        # Si el usuario no tocó el nombre a mano (sigue siendo el nombre
        # sugerido para el tipo anterior), lo actualiza solo al nuevo
        # tipo elegido; si ya lo editó, lo respeta tal cual.
        sugerido_nuevo = nombre_por_kind[var_tipo_elegido.get()]
        if var_nombre_filtro.get().strip() == _ultimo_sugerido["texto"]:
            var_nombre_filtro.set(sugerido_nuevo)
        _ultimo_sugerido["texto"] = sugerido_nuevo

    var_tipo_elegido.trace_add("write", _al_cambiar_tipo)

    etiqueta_error = tk.Label(
        selector, text="", bg="#10141b", fg="#ff8a95", font=(E.FUENTE_UI, 8),
        wraplength=330, justify="left"
    )
    etiqueta_error.pack(fill="x", padx=12)

    def _confirmar():
        nombre_filtro = var_nombre_filtro.get().strip()
        if not nombre_filtro:
            etiqueta_error.config(text="Poné un nombre para el filtro.")
            return
        try:
            filtros_actuales = E.cliente_obs.get_source_filter_list(nombre_fuente).filters or []
        except Exception:
            filtros_actuales = []
        nombres_existentes = {
            mod_obs_eventos._valor(f, "filter_name", "filterName") for f in filtros_actuales
        }
        nombre_final = nombre_filtro
        contador = 2
        while nombre_final in nombres_existentes:
            nombre_final = f"{nombre_filtro} {contador}"
            contador += 1

        try:
            E.cliente_obs.create_source_filter(nombre_fuente, nombre_final, var_tipo_elegido.get())
        except Exception as e:
            etiqueta_error.config(text=f"No se pudo crear el filtro.\n{e}")
            return

        selector.destroy()
        if al_crear:
            E.ventana.after(150, lambda: al_crear(nombre_final))

    marco_botones = tk.Frame(selector, bg="#10141b")
    marco_botones.pack(fill="x", padx=12, pady=10)

    tk.Button(
        marco_botones, text="Cancelar", command=selector.destroy,
        bg="#323b4c", fg="white", relief="flat", font=(E.FUENTE_UI, 9)
    ).pack(side="right", padx=(6, 0))

    tk.Button(
        marco_botones, text="Agregar", command=_confirmar,
        bg="#2fd693", fg="#131825", relief="flat", font=(E.FUENTE_UI, 9, "bold")
    ).pack(side="right", ipadx=8)

    entrada_nombre_filtro.focus_set()
    entrada_nombre_filtro.select_range(0, "end")
    entrada_nombre_filtro.bind("<Return>", lambda e: _confirmar())


def abrir_filtros(nombre):
    if not E.conectado:
        messagebox.showwarning("Sin conexión", "Conectate a OBS para ver los filtros.")
        return

    # Si ya había una ventana de "Filtros" abierta (de esta fuente o de
    # otra), se cierra antes de abrir la nueva -sin esto, cada vez que
    # se apretaba "Filtros" se apilaba una ventana más arriba de la
    # anterior, hasta llenar la pantalla de ventanas superpuestas-. Sólo
    # puede haber una a la vez.
    ventana_previa = E._dialogo_filtros_abierto.get("ventana")
    if ventana_previa is not None:
        try:
            ventana_previa.destroy()
        except Exception:
            pass
        E._dialogo_filtros_abierto["nombre"] = None
        E._dialogo_filtros_abierto["refrescar"] = None
        E._dialogo_filtros_abierto["ventana"] = None

    ventana_filtros = tk.Toplevel(E.ventana)
    ventana_filtros.title(f"Filtros — {nombre}")
    ventana_filtros.configure(bg="#10141b")
    ventana_filtros.geometry("400x440")

    tk.Label(
        ventana_filtros, text=nombre, bg="#10141b", fg="white",
        font=(E.FUENTE_UI, 11, "bold")
    ).pack(anchor="w", padx=10, pady=(10, 0))

    marco_lista = tk.Frame(ventana_filtros, bg="#10141b")
    marco_lista.pack(fill="both", expand=True, padx=10, pady=10)

    def cerrar():
        if E._dialogo_filtros_abierto["nombre"] == nombre:
            E._dialogo_filtros_abierto["nombre"] = None
            E._dialogo_filtros_abierto["refrescar"] = None
            E._dialogo_filtros_abierto["ventana"] = None
        ventana_filtros.destroy()

    ventana_filtros.protocol("WM_DELETE_WINDOW", cerrar)

    def refrescar():
        for w in marco_lista.winfo_children():
            w.destroy()
        try:
            filtros = E.cliente_obs.get_source_filter_list(nombre).filters
        except Exception as e:
            tk.Label(
                marco_lista, text=f"No se pudieron leer los filtros.\n\n{e}",
                bg="#10141b", fg="#ff8a95", wraplength=340, justify="left"
            ).pack(pady=20)
            return

        if not filtros:
            tk.Label(
                marco_lista, text="Esta fuente no tiene filtros.",
                bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)
            ).pack(pady=20)
            return

        for filtro in filtros:
            nombre_filtro = mod_obs_eventos._valor(filtro, "filter_name", "filterName")
            tipo_filtro = mod_obs_eventos._valor(filtro, "filter_kind", "filterKind")
            habilitado = mod_obs_eventos._valor(filtro, "filter_enabled", "filterEnabled")

            fila = tk.Frame(marco_lista, bg="#1a202b", highlightbackground="#0e1219", highlightthickness=1)
            fila.pack(fill="x", pady=3)

            var_habilitado = tk.BooleanVar(value=bool(habilitado))

            def _alternar_filtro(nf=nombre_filtro, var=var_habilitado):
                try:
                    E.cliente_obs.set_source_filter_enabled(nombre, nf, var.get())
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo cambiar el filtro.\n\n{e}")
                    return
                mod_obs_eventos._refrescar_ganancia_fuente_en_hilo(nombre)

            tk.Checkbutton(
                fila, variable=var_habilitado, command=_alternar_filtro,
                bg="#1a202b", activebackground="#222a38", selectcolor="#131825",
                fg="white", activeforeground="white"
            ).pack(side="left", padx=4)

            tk.Label(
                fila, text=f"{nombre_filtro}\n{tipo_filtro}", bg="#1a202b", fg="white",
                font=(E.FUENTE_UI, 9), justify="left", anchor="w"
            ).pack(side="left", padx=4, pady=4, fill="x", expand=True)

            tk.Button(
                fila, text="Ajustes", command=lambda nf=nombre_filtro: _abrir_editor_ajustes_filtro(nombre, nf),
                bg="#3d4d66", fg="white", relief="flat", font=(E.FUENTE_UI, 8)
            ).pack(side="right", padx=4)

            def _eliminar_filtro(nf=nombre_filtro):
                if messagebox.askyesno("Eliminar filtro", f"¿Eliminar el filtro '{nf}'?"):
                    try:
                        E.cliente_obs.remove_source_filter(nombre, nf)
                        refrescar()
                        mod_obs_eventos._refrescar_ganancia_fuente_en_hilo(nombre)
                    except Exception as e:
                        messagebox.showerror("Error", f"No se pudo eliminar el filtro.\n\n{e}")

            tk.Button(
                fila, text="✕", command=_eliminar_filtro,
                bg="#ff5567", fg="white", relief="flat", font=(E.FUENTE_UI, 8)
            ).pack(side="right", padx=(4, 8))

    E._dialogo_filtros_abierto["nombre"] = nombre
    E._dialogo_filtros_abierto["refrescar"] = refrescar
    E._dialogo_filtros_abierto["ventana"] = ventana_filtros

    def _al_crear_filtro_nuevo(nombre_filtro_creado):
        # Al crear un filtro desde ACÁ, OBS de todas formas manda el
        # evento SourceFilterCreated (le hace eco a todos los clientes,
        # incluido éste), que ya refresca la lista sólo con eso — pero
        # se refresca también al toque, sin esperar la ida y vuelta por
        # la red, y de paso se le abre el editor de ajustes en el acto
        # para no obligar a un segundo click.
        refrescar()
        mod_obs_eventos._refrescar_ganancia_fuente_en_hilo(nombre)
        _abrir_editor_ajustes_filtro(nombre, nombre_filtro_creado)

    marco_botones_inferior = tk.Frame(ventana_filtros, bg="#10141b")
    marco_botones_inferior.pack(pady=(0, 8))

    tk.Button(
        marco_botones_inferior, text="➕ Agregar filtro", command=lambda: _abrir_selector_nuevo_filtro(nombre, _al_crear_filtro_nuevo),
        bg="#2fd693", fg="#131825", relief="flat", font=(E.FUENTE_UI, 9, "bold")
    ).pack(side="left", padx=(0, 6))

    tk.Button(
        marco_botones_inferior, text="↻ Actualizar", command=refrescar,
        bg="#323b4c", fg="white", relief="flat", font=(E.FUENTE_UI, 9)
    ).pack(side="left")

    refrescar()


def _valor_obs_o_defecto(ajustes, clave, defecto):
    """El valor que trajo OBS para esa clave si está presente (incluso
    si es 0, False o ""), o si no, el valor por defecto del esquema."""
    if clave in ajustes and ajustes[clave] is not None:
        return ajustes[clave]
    return defecto


def _valores_equivalentes(a, b):
    """Compara dos valores de ajuste tolerando el redondeo de punto
    flotante que puede introducir el viaje de ida y vuelta por JSON,
    para no hacer "temblar" una barra por una diferencia de milésimas
    que en realidad no cambió nada."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-4
    return a == b


def _construir_opciones_sidechain():
    """Fuentes que se pueden elegir como "Fuente de atenuación/
    reducción" (sidechain) de un compresor: las mismas fuentes de
    audio que ya están en la consola, más "Ninguno" primero -tal como
    hace el desplegable equivalente dentro de OBS."""
    opciones = [("Ninguno", "none")]
    for nombre_fuente_disp in sorted(E.fuentes.keys()):
        opciones.append((nombre_fuente_disp, nombre_fuente_disp))
    return opciones


def _rango_para_campo(clave, valor):
    """Adivina un rango razonable (mínimo, máximo) para la barra
    deslizante de un campo de ajuste de filtro, según su nombre."""
    clave_baja = clave.lower()
    for patron, rango in E.RANGOS_CAMPOS_FILTRO:
        if patron in clave_baja:
            return rango
    if isinstance(valor, float) and 0 <= valor <= 1:
        return (0.0, 1.0)
    if isinstance(valor, bool):
        return (0, 1)
    amplitud = max(10, abs(valor) * 2)
    minimo = -amplitud if valor < 0 else 0
    return (minimo, amplitud)


def _abrir_editor_ajustes_filtro(nombre_fuente, nombre_filtro):
    """Editor de los ajustes de un filtro con controles simples: una
    barra deslizante para cada valor numérico (en vez del típico cuadro
    de texto/código con el número de dB), una tilde para cada valor de
    sí/no, un desplegable para las fuentes (por ej. el sidechain del
    compresor), y un campo de texto para el resto.

    Para el Limitador, el Compresor, la Ganancia y el Ecualizador de 3
    bandas (ver ESQUEMA_FILTROS_CONOCIDOS) se dibuja siempre el juego
    COMPLETO de controles que trae OBS, con las mismas claves, rangos y
    valores por defecto que usa OBS -así el filtro recién agregado ya
    aparece con todos sus controles funcionando, no sólo "Ganancia".
    Para cualquier otro filtro se sigue armando un control genérico por
    cada ajuste que haya devuelto OBS, como antes.

    Los cambios en los controles se mandan a OBS al instante, igual que
    el fader de volumen principal. Mientras el editor esté abierto,
    también se sondea a OBS varias veces por segundo para traer de
    vuelta cualquier cambio hecho desde DENTRO de OBS (por ejemplo, si
    alguien mueve el mismo Umbral desde la ventana de filtros de OBS),
    de forma que los cambios viajen en los dos sentidos en tiempo real
    -salvo en el control que el usuario tiene agarrado en ese instante,
    para no pelearle el slider mientras lo está arrastrando."""
    if not E.conectado:
        return
    try:
        info = E.cliente_obs.get_source_filter(nombre_fuente, nombre_filtro)
        ajustes = mod_obs_eventos._valor(info, "filter_settings", "filterSettings") or {}
        tipo_filtro = mod_obs_eventos._valor(info, "filter_kind", "filterKind")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudieron leer los ajustes del filtro.\n\n{e}")
        return

    editor = tk.Toplevel(E.ventana)
    editor.title(f"Ajustes — {nombre_filtro}")
    editor.configure(bg="#10141b")
    editor.geometry("400x480")

    tk.Label(
        editor, text=f"{nombre_fuente} · {nombre_filtro}",
        bg="#10141b", fg="white", font=(E.FUENTE_UI, 11, "bold")
    ).pack(anchor="w", padx=12, pady=(12, 8))

    marco_scroll = tk.Frame(editor, bg="#10141b")
    marco_scroll.pack(fill="both", expand=True, padx=12)

    canvas_ajustes = tk.Canvas(marco_scroll, bg="#10141b", highlightthickness=0)
    scrollbar_ajustes = ttk.Scrollbar(marco_scroll, orient="vertical", command=canvas_ajustes.yview)
    marco_campos = tk.Frame(canvas_ajustes, bg="#10141b")
    marco_campos.bind(
        "<Configure>", lambda e: canvas_ajustes.configure(scrollregion=canvas_ajustes.bbox("all"))
    )
    id_ventana_campos = canvas_ajustes.create_window((0, 0), window=marco_campos, anchor="nw")
    canvas_ajustes.bind(
        "<Configure>", lambda e: canvas_ajustes.itemconfig(id_ventana_campos, width=e.width)
    )
    canvas_ajustes.configure(yscrollcommand=scrollbar_ajustes.set)
    canvas_ajustes.pack(side="left", fill="both", expand=True)
    scrollbar_ajustes.pack(side="right", fill="y")

    # Nombre de campo -> función que devuelve su valor actual leído del
    # control correspondiente; se arma en el mismo orden en que se van
    # creando los controles, más abajo.
    controles = {}
    # Campos que llegaron con un tipo de dato que no tiene un control
    # simple acá (listas, objetos anidados): se guardan tal cual están
    # y se reenvían sin tocar al aplicar, para no perderlos.
    claves_avanzadas = {}
    # Último valor por campo que ESTE editor le mandó a OBS (o leyó de
    # OBS): sirve para que el sondeo periódico sepa si lo que acaba de
    # leer es un cambio genuino hecho desde OBS, o simplemente el eco
    # de lo que el editor mismo acaba de aplicar.
    valores_conocidos = {}
    # Campo -> True mientras el usuario tiene ese slider agarrado con
    # el mouse: el sondeo no le toca el valor mientras dure el arrastre.
    arrastrando = {}
    # Campo -> función(valor) que actualiza el control en pantalla SIN
    # volver a aplicar nada (para cuando el cambio vino de OBS).
    actualizadores = {}

    trabajo_sondeo = {"id": None}

    def aplicar(*_ignorar):
        nuevos_ajustes = dict(claves_avanzadas)
        for clave, obtener in controles.items():
            try:
                nuevos_ajustes[clave] = obtener()
            except Exception:
                pass
        valores_conocidos.update(nuevos_ajustes)
        try:
            E.cliente_obs.set_source_filter_settings(nombre_fuente, nombre_filtro, nuevos_ajustes, True)
        except Exception as e:
            print(f"No se pudieron aplicar los ajustes del filtro '{nombre_filtro}': {e}")
            return
        if tipo_filtro in C.CAMPOS_GANANCIA_FILTRO:
            # Este filtro puede estar cambiando la ganancia extra de la
            # fuente (ver CAMPOS_GANANCIA_FILTRO): recalcularla al
            # toque para que el medidor de nivel reaccione ya mismo,
            # sin esperar al ciclo de refresco periódico.
            mod_obs_eventos._refrescar_ganancia_fuente_en_hilo(nombre_fuente)

    def _crear_barra(clave, etiqueta_texto, minimo, maximo, paso, sufijo, valor_inicial, es_entero):
        fila = tk.Frame(marco_campos, bg="#10141b")
        fila.pack(fill="x", pady=6)

        cabecera_campo = tk.Frame(fila, bg="#10141b")
        cabecera_campo.pack(fill="x")
        tk.Label(
            cabecera_campo, text=etiqueta_texto, bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)
        ).pack(side="left")
        valor_mostrado_inicial = round(float(valor_inicial)) if es_entero else float(valor_inicial)
        etiqueta_valor = tk.Label(
            cabecera_campo, text=f"{valor_mostrado_inicial:g}{sufijo}", bg="#10141b", fg="#2fd693",
            font=(E.FUENTE_UI, 9, "bold")
        )
        etiqueta_valor.pack(side="right")

        var_num = tk.DoubleVar(value=float(valor_inicial))

        def _al_mover(v, etq=etiqueta_valor, entero=es_entero, sfj=sufijo, clv=clave):
            valor_mostrado = round(float(v)) if entero else float(v)
            etq.config(text=f"{valor_mostrado:g}{sfj}")
            arrastrando[clv] = True
            aplicar()

        def _al_soltar(_evento=None, clv=clave):
            arrastrando[clv] = False

        control_slider = tk.Scale(
            fila, from_=minimo, to=maximo, resolution=paso,
            orient="horizontal", showvalue=False, variable=var_num, command=_al_mover,
            bg="#2fd693", fg="white", troughcolor="#293244",
            highlightthickness=0, activebackground="#4fe3ae", sliderrelief="flat",
            sliderlength=18, width=12
        )
        control_slider.pack(fill="x")
        control_slider.bind("<ButtonRelease-1>", _al_soltar)
        control_slider.bind("<ButtonPress-1>", lambda _e, clv=clave: arrastrando.__setitem__(clv, True))

        tipo_original = int if es_entero else float
        controles[clave] = (lambda var=var_num, t=tipo_original: t(var.get()))
        valores_conocidos[clave] = valor_inicial

        def _actualizar_desde_afuera(v, var=var_num, etq=etiqueta_valor, entero=es_entero, sfj=sufijo):
            var.set(float(v))
            valor_mostrado = round(float(v)) if entero else float(v)
            etq.config(text=f"{valor_mostrado:g}{sfj}")
        actualizadores[clave] = _actualizar_desde_afuera

    def _crear_lista(clave, etiqueta_texto, valor_inicial):
        fila = tk.Frame(marco_campos, bg="#10141b")
        fila.pack(fill="x", pady=6)
        tk.Label(
            fila, text=etiqueta_texto, bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)
        ).pack(anchor="w")

        opciones = _construir_opciones_sidechain()
        etiquetas_opciones = [o[0] for o in opciones]
        etiqueta_por_valor = {v: e for e, v in opciones}
        valor_por_etiqueta = {e: v for e, v in opciones}

        var_combo = tk.StringVar(value=etiqueta_por_valor.get(valor_inicial, etiquetas_opciones[0]))
        combo = ttk.Combobox(
            fila, textvariable=var_combo, values=etiquetas_opciones,
            state="readonly", style="Discreta.TCombobox"
        )
        combo.pack(fill="x", pady=(2, 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: aplicar())

        controles[clave] = (lambda var=var_combo, m=valor_por_etiqueta: m.get(var.get(), "none"))
        valores_conocidos[clave] = valor_inicial

        def _actualizar_desde_afuera(v, var=var_combo, m=etiqueta_por_valor, etqs=etiquetas_opciones):
            var.set(m.get(v, etqs[0]))
        actualizadores[clave] = _actualizar_desde_afuera

    esquema = E.ESQUEMA_FILTROS_CONOCIDOS.get(tipo_filtro)

    if esquema:
        for campo in esquema:
            clave = campo["clave"]
            valor_inicial = _valor_obs_o_defecto(ajustes, clave, campo["defecto"])
            if campo["tipo"] == "lista":
                _crear_lista(clave, campo["etiqueta"], valor_inicial)
            else:
                _crear_barra(
                    clave, campo["etiqueta"], campo["minimo"], campo["maximo"],
                    campo["paso"], campo["sufijo"], valor_inicial, campo["tipo"] == "int"
                )

        # Ajustes que trajo OBS pero que no forman parte del esquema
        # fijo (por ejemplo, versiones de OBS que le agreguen algún
        # campo nuevo a futuro a estos mismos filtros): se conservan
        # tal cual y se reenvían sin tocar, para no perderlos al
        # aplicar, aunque no tengan un control propio acá.
        claves_conocidas = {c["clave"] for c in esquema}
        for clave, valor in ajustes.items():
            if clave not in claves_conocidas:
                claves_avanzadas[clave] = valor
    else:
        # Filtro sin esquema fijo (croma, VST de terceros, etc.): se
        # arma un control genérico por cada ajuste que haya devuelto
        # OBS, adivinando un rango razonable por el nombre del campo.
        for clave, valor in ajustes.items():
            if isinstance(valor, bool):
                var_bool = tk.BooleanVar(value=valor)
                tk.Checkbutton(
                    marco_campos, text=clave, variable=var_bool, command=aplicar,
                    bg="#10141b", fg="white", activebackground="#10141b", activeforeground="white",
                    selectcolor="#1a202b", font=(E.FUENTE_UI, 9), anchor="w"
                ).pack(fill="x", pady=4)
                controles[clave] = var_bool.get
                valores_conocidos[clave] = valor

            elif isinstance(valor, (int, float)):
                minimo, maximo = _rango_para_campo(clave, valor)
                es_entero = isinstance(valor, int) and not isinstance(valor, bool)
                _crear_barra(clave, clave, minimo, maximo, (1 if es_entero else 0.1), "", valor, es_entero)

            elif isinstance(valor, str):
                fila = tk.Frame(marco_campos, bg="#10141b")
                fila.pack(fill="x", pady=4)
                tk.Label(fila, text=clave, bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)).pack(anchor="w")
                var_txt = tk.StringVar(value=valor)
                entrada = tk.Entry(
                    fila, textvariable=var_txt, bg="#1a202b", fg="white",
                    insertbackground="white", relief="flat", font=(E.FUENTE_UI, 9)
                )
                entrada.pack(fill="x", ipady=3)
                entrada.bind("<Return>", aplicar)
                entrada.bind("<FocusOut>", aplicar)
                controles[clave] = var_txt.get
                valores_conocidos[clave] = valor

            else:
                claves_avanzadas[clave] = valor

        if not ajustes:
            tk.Label(
                marco_campos, text="Este filtro no tiene ajustes editables.",
                bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)
            ).pack(pady=20)

    if claves_avanzadas:
        tk.Label(
            marco_campos,
            text=f"({len(claves_avanzadas)} ajuste(s) avanzado(s) no se muestran acá,\n"
                 "pero se conservan tal cual al aplicar.)",
            bg="#10141b", fg="#79859f", font=(E.FUENTE_UI, 7), justify="left"
        ).pack(anchor="w", pady=(12, 0))

    # Las barras y los desplegables ya aplican solos al tocarlos; este
    # botón es sobre todo para confirmar los campos de texto (que no se
    # aplican letra por letra) y, al tocarlo, además cierra la ventana
    # -es la confirmación final de "quedó todo como quiero".
    def _aplicar_y_cerrar():
        aplicar()
        _cerrar_editor()

    tk.Button(
        editor, text="Aplicar", command=_aplicar_y_cerrar,
        bg="#2fd693", fg="#131825", relief="flat", font=(E.FUENTE_UI, 9, "bold")
    ).pack(pady=10, ipadx=16, ipady=3)

    # ------------------------------------------------------------------
    # Sincronización EN VIVO desde OBS hacia este editor: OBS-WebSocket
    # avisa con eventos cuando un filtro se crea, se borra, se renombra
    # o se prende/apaga, pero NO cuando cambian sus AJUSTES (no existe
    # ningún evento "SourceFilterSettingsChanged" en el protocolo). La
    # única forma de enterarse de un cambio hecho desde dentro de OBS
    # mientras este editor está abierto es preguntarle a OBS de tanto
    # en tanto. Se hace cada medio segundo, sólo mientras la ventana
    # sigue abierta, y sin pisar el control que el usuario tenga
    # agarrado en ese instante.
    def _sondear_cambios_externos():
        if not E.conectado:
            trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)
            return
        try:
            info_actual = E.cliente_obs.get_source_filter(nombre_fuente, nombre_filtro)
            ajustes_actuales = mod_obs_eventos._valor(info_actual, "filter_settings", "filterSettings") or {}
        except Exception:
            trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)
            return

        for clave, actualizador in actualizadores.items():
            if arrastrando.get(clave):
                continue
            defecto = next((c["defecto"] for c in esquema if c["clave"] == clave), None) if esquema else None
            valor_actual = _valor_obs_o_defecto(ajustes_actuales, clave, defecto)
            if valor_actual is None:
                continue
            if not _valores_equivalentes(valores_conocidos.get(clave), valor_actual):
                valores_conocidos[clave] = valor_actual
                actualizador(valor_actual)

        trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)

    def _cerrar_editor():
        if trabajo_sondeo["id"] is not None:
            try:
                editor.after_cancel(trabajo_sondeo["id"])
            except Exception:
                pass
            trabajo_sondeo["id"] = None
        editor.destroy()

    editor.protocol("WM_DELETE_WINDOW", _cerrar_editor)
    trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)
