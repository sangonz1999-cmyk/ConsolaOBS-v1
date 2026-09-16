import tkinter as tk

from tkinter import filedialog, messagebox, ttk

from consola_obs import estado as E
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.audio import filtros as mod_audio_filtros


def abrir_propiedades(nombre):
    """Ventana de "Propiedades" de una fuente (Fase 2 del plan de
    mejoras): arma los controles dinámicamente según el inputKind real
    de la fuente en OBS (GetInputSettings), usando el mismo juego
    completo de ajustes "de catálogo" que ya se usa para los filtros
    -ver ESQUEMA_PROPIEDADES_ENTRADA en estado.py- para los tipos de
    entrada de audio conocidos (WASAPI de entrada/salida, captura de
    audio de aplicación, Fuente de medios), así un micrófono muestra
    sus propios campos, una fuente de audio de aplicación los suyos, un
    Media Source los suyos, etc., igual que hace OBS. Cualquier otro
    tipo de fuente cae en un editor genérico -mismo criterio que un
    filtro sin esquema fijo-, para que ninguna fuente quede sin ventana
    de Propiedades aunque todavía no esté calcada exacto.

    Los ajustes que dependen de ESTA máquina (qué dispositivo de audio
    hay, qué ventanas están abiertas ahora) no se pueden fijar a mano:
    se piden en vivo con GetInputPropertiesListPropertyItems, tal como
    pide el punto 2.2 del plan. Para completar los campos que el
    esquema conoce pero que la fuente todavía no tiene guardados (por
    ejemplo, una fuente recién creada), se usa GetInputDefaultSettings
    antes de caer al valor por defecto puesto a mano acá.

    Igual que en Filtros: los cambios se mandan a OBS al instante con
    SetInputSettings y, mientras la ventana esté abierta, se sondea a
    OBS cada medio segundo para traer cualquier cambio hecho desde
    DENTRO de OBS. No existe un evento "InputSettingsChanged" en el
    protocolo de OBS-WebSocket (sólo hay eventos puntuales para el
    nombre, el mute, el volumen, etc., igual que con los filtros no
    existe "SourceFilterSettingsChanged"), así que acá también hace
    falta sondeo periódico en vez de un aviso instantáneo."""
    if not E.conectado:
        messagebox.showwarning("Sin conexión", "Conectate a OBS para ver las propiedades.")
        return

    # Sólo puede haber una ventana de "Propiedades" abierta a la vez
    # -mismo criterio que con la ventana de Filtros-.
    ventana_previa = E._dialogo_propiedades_abierto.get("ventana")
    if ventana_previa is not None:
        try:
            ventana_previa.destroy()
        except Exception:
            pass
        E._dialogo_propiedades_abierto["nombre"] = None
        E._dialogo_propiedades_abierto["ventana"] = None

    try:
        info = E.cliente_obs.get_input_settings(nombre)
        ajustes = mod_obs_eventos._valor(info, "input_settings", "inputSettings") or {}
        input_kind = mod_obs_eventos._valor(info, "input_kind", "inputKind")
    except Exception as e:
        messagebox.showerror(
            "Error", f"No se pudieron leer las propiedades de '{nombre}'.\n\n{e}"
        )
        return

    # Ajustes "de fábrica" para este inputKind: sirven para completar
    # cualquier campo del esquema que la fuente todavía no tenga
    # guardado (ver el mismo razonamiento en el comentario grande de
    # ESQUEMA_FILTROS_CONOCIDOS, en estado.py). No todas las versiones
    # de OBS-WebSocket devuelven algo útil acá para cualquier kind, así
    # que si falla simplemente se sigue sin eso.
    ajustes_por_defecto = {}
    try:
        resp_defecto = E.cliente_obs.get_input_default_settings(input_kind)
        ajustes_por_defecto = mod_obs_eventos._valor(
            resp_defecto, "default_input_settings", "defaultInputSettings"
        ) or {}
    except Exception:
        pass

    # Copia intacta de cómo estaba la fuente al abrir la ventana: es lo
    # que se restaura si el usuario toca "Cancelar" (igual que en OBS,
    # donde los cambios se ven en vivo pero Cancelar los deshace).
    ajustes_originales = dict(ajustes)

    editor = tk.Toplevel(E.ventana)
    editor.title(f"Propiedades para '{nombre}'")
    editor.configure(bg="#10141b")
    # Más ancha que antes porque ahora la etiqueta va a la izquierda y
    # el control a la derecha, como en la ventana real de OBS, y hay
    # opciones de texto largo ("Coincidir con el título, de lo
    # contrario buscar ventana del mismo ejecutable").
    editor.geometry("820x560")
    editor.minsize(620, 380)

    tk.Label(
        editor, text=f"{nombre}\n{input_kind or '(tipo desconocido)'}",
        bg="#10141b", fg="white", font=(E.FUENTE_UI, 11, "bold"), justify="left"
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
    mod_audio_filtros._habilitar_scroll_con_rueda(canvas_ajustes)

    controles = {}
    claves_avanzadas = {}
    valores_conocidos = {}
    arrastrando = {}
    actualizadores = {}
    filas_por_clave = {}
    # Orden en que se fueron creando las filas. Hace falta para que un
    # campo que estaba oculto vuelva a aparecer EN SU LUGAR y no al
    # final de la lista (por ejemplo, "Compatibilidad multiadaptador"
    # al pasar el método de captura a BitBlt).
    orden_filas = []
    ANCHO_ETIQUETA = 31
    _actualizar_visibilidad_condicional = lambda: None

    def _registrar_fila(clave, fila):
        filas_por_clave[clave] = fila
        if clave not in orden_filas:
            orden_filas.append(clave)

    def _fila_etiquetada(clave, etiqueta_texto):
        """Fila al estilo de OBS: etiqueta a la izquierda, alineada a
        la derecha contra una columna fija, y el control ocupando todo
        el ancho restante. Devuelve el contenedor donde va el control."""
        fila = tk.Frame(marco_campos, bg="#10141b")
        fila.pack(fill="x", pady=4)
        _registrar_fila(clave, fila)
        tk.Label(
            fila, text=etiqueta_texto, bg="#10141b", fg="#8e9ab3",
            font=(E.FUENTE_UI, 9), width=ANCHO_ETIQUETA, anchor="e"
        ).pack(side="left", padx=(0, 8))
        contenedor = tk.Frame(fila, bg="#10141b")
        contenedor.pack(side="left", fill="x", expand=True)
        return contenedor

    trabajo_sondeo = {"id": None}

    def _valor_efectivo(clave, defecto_esquema):
        """Valor actual de la fuente para 'clave' si OBS lo trae; si
        no, el valor por defecto que OBS le aplica a este inputKind
        (GetInputDefaultSettings); si tampoco, el valor puesto a mano
        en el esquema."""
        if clave in ajustes and ajustes[clave] is not None:
            return ajustes[clave]
        if clave in ajustes_por_defecto and ajustes_por_defecto[clave] is not None:
            return ajustes_por_defecto[clave]
        return defecto_esquema

    def aplicar(*_ignorar):
        nuevos_ajustes = dict(claves_avanzadas)
        for clave, obtener in controles.items():
            try:
                nuevos_ajustes[clave] = obtener()
            except Exception:
                pass
        valores_conocidos.update(nuevos_ajustes)
        try:
            E.cliente_obs.set_input_settings(nombre, nuevos_ajustes, True)
        except Exception as e:
            print(f"No se pudieron aplicar las propiedades de '{nombre}': {e}")
            return
        _actualizar_visibilidad_condicional()

    def _crear_barra(clave, etiqueta_texto, minimo, maximo, paso, sufijo, valor_inicial, es_entero):
        fila = tk.Frame(marco_campos, bg="#10141b")
        fila.pack(fill="x", pady=6)
        _registrar_fila(clave, fila)

        cabecera_campo = tk.Frame(fila, bg="#10141b")
        cabecera_campo.pack(fill="x")
        tk.Label(
            cabecera_campo, text=etiqueta_texto, bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)
        ).pack(side="left")
        valor_mostrado_inicial = round(float(valor_inicial)) if es_entero else float(valor_inicial)
        etiqueta_valor = tk.Label(
            cabecera_campo, text=f"{valor_mostrado_inicial:g}{sufijo}",
            bg="#10141b", fg=E.color_acento_claro() if E.es_moderna() else "#2fd693",
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
            bg=E.color_acento(), fg="white", troughcolor="#293244",
            highlightthickness=0, activebackground=E.color_acento_claro(), sliderrelief="flat",
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

    def _crear_check(clave, etiqueta_texto, valor_inicial):
        fila = tk.Frame(marco_campos, bg="#10141b")
        fila.pack(fill="x", pady=2)
        _registrar_fila(clave, fila)

        # En OBS las casillas no llevan etiqueta a la izquierda: van
        # alineadas con la columna de los controles, debajo de los
        # desplegables. Se reserva el mismo ancho de la columna de
        # etiquetas para que queden en la misma línea vertical.
        tk.Label(
            fila, text="", bg="#10141b", width=ANCHO_ETIQUETA
        ).pack(side="left", padx=(0, 8))

        var_bool = tk.BooleanVar(value=bool(valor_inicial))
        tk.Checkbutton(
            fila, text=etiqueta_texto, variable=var_bool, command=aplicar,
            bg="#10141b", fg="white", activebackground="#10141b", activeforeground="white",
            selectcolor="#1a202b", font=(E.FUENTE_UI, 9), anchor="w"
        ).pack(side="left", fill="x", expand=True)

        controles[clave] = var_bool.get
        valores_conocidos[clave] = bool(valor_inicial)

        def _actualizar_desde_afuera(v, var=var_bool):
            var.set(bool(v))
        actualizadores[clave] = _actualizar_desde_afuera

    def _crear_lista_fija(clave, etiqueta_texto, valor_inicial, opciones):
        contenedor = _fila_etiquetada(clave, etiqueta_texto)

        etiquetas_opciones = [o[0] for o in opciones]
        etiqueta_por_valor = {v: e for e, v in opciones}
        valor_por_etiqueta = {e: v for e, v in opciones}
        valor_por_defecto_desconocido = opciones[0][1] if opciones else None

        var_combo = tk.StringVar(value=etiqueta_por_valor.get(valor_inicial, etiquetas_opciones[0]))
        combo = ttk.Combobox(
            contenedor, textvariable=var_combo, values=etiquetas_opciones,
            state="readonly", style="Discreta.TCombobox"
        )
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", lambda _e: aplicar())

        controles[clave] = (
            lambda var=var_combo, m=valor_por_etiqueta, d=valor_por_defecto_desconocido: m.get(var.get(), d)
        )
        valores_conocidos[clave] = valor_inicial

        def _actualizar_desde_afuera(v, var=var_combo, m=etiqueta_por_valor, etqs=etiquetas_opciones):
            var.set(m.get(v, etqs[0]))
        actualizadores[clave] = _actualizar_desde_afuera

    def _crear_lista_dinamica(clave, etiqueta_texto, valor_inicial):
        """Lista cuyas opciones dependen de ESTA máquina (dispositivos
        de audio conectados, ventanas abiertas ahora mismo): se piden
        en vivo con GetInputPropertiesListPropertyItems en vez de
        fijarlas a mano, tal como pide el punto 2.2 del plan."""
        opciones = []
        try:
            resp_items = E.cliente_obs.get_input_properties_list_property_items(nombre, clave)
            items = mod_obs_eventos._valor(resp_items, "property_items", "propertyItems") or []
            for item in items:
                habilitado = mod_obs_eventos._valor(item, "item_enabled", "itemEnabled")
                if habilitado is False:
                    continue
                etq = mod_obs_eventos._valor(item, "item_name", "itemName")
                val = mod_obs_eventos._valor(item, "item_value", "itemValue")
                if etq is None or val is None:
                    continue
                opciones.append((etq, val))
        except Exception as e:
            print(f"No se pudo leer la lista de '{clave}' para '{nombre}': {e}")

        if not opciones:
            # Esta versión de OBS no informó nada para este campo (o el
            # pedido no aplica): se cae a un campo de texto simple con
            # el valor crudo, para no dejar el campo sin ningún control.
            _crear_texto(clave, etiqueta_texto, valor_inicial)
            return

        valores_presentes = {v for _e, v in opciones}
        if valor_inicial not in valores_presentes and valor_inicial not in (None, ""):
            # El valor guardado no está entre los dispositivos/ventanas
            # que hay AHORA (por ejemplo, un micrófono desenchufado):
            # se agrega igual como opción, para no pisarlo con otra
            # cosa ni esconder cuál es el valor real guardado.
            opciones = [(f"(actual, no disponible) {valor_inicial}", valor_inicial)] + opciones

        _crear_lista_fija(clave, etiqueta_texto, valor_inicial, opciones)

    def _crear_texto(clave, etiqueta_texto, valor_inicial):
        contenedor = _fila_etiquetada(clave, etiqueta_texto)
        var_txt = tk.StringVar(value=valor_inicial or "")
        entrada = tk.Entry(
            contenedor, textvariable=var_txt, bg="#1a202b", fg="white",
            insertbackground="white", relief="flat", font=(E.FUENTE_UI, 9)
        )
        entrada.pack(fill="x", ipady=3)
        entrada.bind("<Return>", aplicar)
        entrada.bind("<FocusOut>", aplicar)

        controles[clave] = var_txt.get
        valores_conocidos[clave] = valor_inicial

        def _actualizar_desde_afuera(v, var=var_txt):
            var.set(v or "")
        actualizadores[clave] = _actualizar_desde_afuera

    def _crear_archivo(clave, etiqueta_texto, valor_inicial):
        marco_campo = _fila_etiquetada(clave, etiqueta_texto)

        var_txt = tk.StringVar(value=valor_inicial or "")
        entrada = tk.Entry(
            marco_campo, textvariable=var_txt, bg="#1a202b", fg="white",
            insertbackground="white", relief="flat", font=(E.FUENTE_UI, 9), state="readonly",
            readonlybackground="#1a202b"
        )
        entrada.pack(side="left", fill="x", expand=True, ipady=3)

        def _examinar():
            elegido = filedialog.askopenfilename(
                parent=editor, title=f"Elegir {etiqueta_texto}"
            )
            if elegido:
                var_txt.set(elegido)
                aplicar()

        tk.Button(
            marco_campo, text="Examinar…", command=_examinar,
            bg="#3d4d66", fg="white", relief="flat", font=(E.FUENTE_UI, 8)
        ).pack(side="right", padx=(6, 0))

        controles[clave] = var_txt.get
        valores_conocidos[clave] = valor_inicial

        def _actualizar_desde_afuera(v, var=var_txt):
            var.set(v or "")
        actualizadores[clave] = _actualizar_desde_afuera

    esquema = E.ESQUEMA_PROPIEDADES_ENTRADA.get(input_kind)

    if esquema:
        for campo in esquema:
            clave = campo["clave"]
            valor_inicial = _valor_efectivo(clave, campo.get("defecto"))
            tipo = campo["tipo"]
            if tipo == "lista_dinamica":
                _crear_lista_dinamica(clave, campo["etiqueta"], valor_inicial)
            elif tipo == "lista":
                _crear_lista_fija(clave, campo["etiqueta"], valor_inicial, campo.get("opciones") or [])
            elif tipo == "archivo":
                _crear_archivo(clave, campo["etiqueta"], valor_inicial)
            elif tipo == "bool":
                _crear_check(clave, campo["etiqueta"], valor_inicial)
            elif tipo == "texto":
                _crear_texto(clave, campo["etiqueta"], valor_inicial)
            else:
                _crear_barra(
                    clave, campo["etiqueta"], campo["minimo"], campo["maximo"],
                    campo["paso"], campo["sufijo"], valor_inicial, tipo == "int"
                )

        # Campos que sólo se muestran según el valor de OTRO campo del
        # mismo esquema (ver 'visible_si'), por ejemplo "Ruta del
        # archivo" sólo si "Archivo local" está tildado: mismo criterio
        # que en el editor de filtros.
        def _campo_visible(campo_dep):
            condicion = campo_dep.get("visible_si")
            if not condicion:
                return True
            clave_ctrl, valor_esperado = condicion
            obtener_ctrl = controles.get(clave_ctrl)
            if obtener_ctrl is None:
                return True
            # "visible_si" acepta un único valor -("is_local_file", True)-
            # o varios -("method", (0, 2))-, porque en OBS hay campos que
            # se muestran para más de una opción del mismo desplegable
            # (por ejemplo "Área del cliente", que vale tanto para
            # "Automático" como para "Captura de gráficos de Windows").
            valores_ok = valor_esperado if isinstance(valor_esperado, (tuple, list, set)) else (valor_esperado,)
            try:
                return obtener_ctrl() in valores_ok
            except Exception:
                return True

        def _actualizar_visibilidad_condicional():
            # Se re-empaquetan TODAS las filas del esquema en su orden
            # original: si se volviera a hacer pack() sólo de la que
            # reaparece, Tk la mandaría al final de la lista y el orden
            # de la ventana dejaría de coincidir con el de OBS.
            hay_cambio = False
            for campo_dep in esquema:
                fila_dep = filas_por_clave.get(campo_dep["clave"])
                if fila_dep is None:
                    continue
                if bool(fila_dep.winfo_ismapped()) != _campo_visible(campo_dep):
                    hay_cambio = True
                    break
            if not hay_cambio:
                return

            for clave_fila in orden_filas:
                fila_dep = filas_por_clave.get(clave_fila)
                if fila_dep is not None:
                    fila_dep.pack_forget()
            for clave_fila in orden_filas:
                fila_dep = filas_por_clave.get(clave_fila)
                if fila_dep is None:
                    continue
                campo_dep = next((c for c in esquema if c["clave"] == clave_fila), None)
                if campo_dep is not None and not _campo_visible(campo_dep):
                    continue
                relleno = 2 if (campo_dep or {}).get("tipo") == "bool" else 4
                fila_dep.pack(fill="x", pady=relleno)

        _actualizar_visibilidad_condicional()

        claves_conocidas = {c["clave"] for c in esquema}
        for clave, valor in ajustes.items():
            if clave not in claves_conocidas:
                claves_avanzadas[clave] = valor
    else:
        # Tipo de fuente sin esquema fijo (Captura de ventana,
        # Navegador, Fuente de color, video, etc.): se arma un control
        # genérico por cada ajuste, igual que hace el editor de un
        # filtro sin esquema. Se combinan los ajustes por defecto de
        # OBS con los guardados (el guardado pisa al default) para que
        # una fuente recién creada, sin nada tocado todavía, igual
        # muestre el juego completo de controles.
        ajustes_combinados = dict(ajustes_por_defecto)
        ajustes_combinados.update(ajustes)
        for clave, valor in ajustes_combinados.items():
            if isinstance(valor, bool):
                _crear_check(clave, clave, valor)
            elif isinstance(valor, (int, float)):
                minimo, maximo = mod_audio_filtros._rango_para_campo(clave, valor)
                es_entero = isinstance(valor, int) and not isinstance(valor, bool)
                _crear_barra(clave, clave, minimo, maximo, (1 if es_entero else 0.1), "", valor, es_entero)
            elif isinstance(valor, str):
                _crear_texto(clave, clave, valor)
            else:
                claves_avanzadas[clave] = valor

        if not ajustes_combinados:
            tk.Label(
                marco_campos, text="Esta fuente no tiene propiedades editables conocidas.",
                bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9)
            ).pack(pady=20)

    if claves_avanzadas:
        tk.Label(
            marco_campos,
            text=f"({len(claves_avanzadas)} ajuste(s) avanzado(s) no se muestran acá,\n"
                 "pero se conservan tal cual al aplicar.)",
            bg="#10141b", fg="#79859f", font=(E.FUENTE_UI, 7), justify="left"
        ).pack(anchor="w", pady=(12, 0))

    def _cerrar_editor():
        if trabajo_sondeo["id"] is not None:
            try:
                editor.after_cancel(trabajo_sondeo["id"])
            except Exception:
                pass
            trabajo_sondeo["id"] = None
        if E._dialogo_propiedades_abierto.get("nombre") == nombre:
            E._dialogo_propiedades_abierto["nombre"] = None
            E._dialogo_propiedades_abierto["ventana"] = None
        editor.destroy()

    def _aplicar_y_cerrar():
        aplicar()
        _cerrar_editor()

    def _restaurar_por_defecto():
        """Mismo botón "Por defecto" que tiene OBS: vuelve a dejar la
        fuente con los ajustes de fábrica de su tipo
        (GetInputDefaultSettings), sin cerrar la ventana."""
        if not ajustes_por_defecto:
            messagebox.showinfo(
                "Por defecto",
                "OBS no informó ajustes de fábrica para este tipo de fuente.",
                parent=editor,
            )
            return
        for clave, actualizador in actualizadores.items():
            if clave in ajustes_por_defecto:
                try:
                    actualizador(ajustes_por_defecto[clave])
                except Exception:
                    pass
        aplicar()

    def _cancelar():
        """Como el "Cancelar" de OBS: los cambios se fueron viendo en
        vivo, así que al cancelar hay que devolver la fuente tal cual
        estaba cuando se abrió la ventana. Se manda sin superponer
        (overlay=False) para que también se deshagan las claves que
        antes no existían."""
        try:
            E.cliente_obs.set_input_settings(nombre, ajustes_originales, False)
        except Exception as e:
            print(f"No se pudieron restaurar las propiedades de '{nombre}': {e}")
        _cerrar_editor()

    barra_botones = tk.Frame(editor, bg="#10141b")
    barra_botones.pack(fill="x", padx=12, pady=10)

    tk.Button(
        barra_botones, text="Por defecto", command=_restaurar_por_defecto,
        bg="#3d4d66", fg="white", relief="flat", font=(E.FUENTE_UI, 9)
    ).pack(side="left", ipadx=10, ipady=3)

    tk.Button(
        barra_botones, text="Aceptar", command=_aplicar_y_cerrar,
        bg=E.color_acento(), fg="#131825", relief="flat", font=(E.FUENTE_UI, 9, "bold")
    ).pack(side="right", ipadx=16, ipady=3)

    tk.Button(
        barra_botones, text="Cancelar", command=_cancelar,
        bg="#3d4d66", fg="white", relief="flat", font=(E.FUENTE_UI, 9)
    ).pack(side="right", padx=(0, 8), ipadx=12, ipady=3)

    # La "X" de la ventana cancela, igual que en OBS.
    editor.protocol("WM_DELETE_WINDOW", _cancelar)

    E._dialogo_propiedades_abierto["nombre"] = nombre
    E._dialogo_propiedades_abierto["ventana"] = editor

    # ------------------------------------------------------------------
    # Sincronización EN VIVO desde OBS hacia este editor (punto 2.3 del
    # plan): igual mecanismo que en el editor de un filtro -sondeo cada
    # 500 ms, salteando el control que el usuario tenga agarrado en ese
    # instante-, porque OBS-WebSocket tampoco avisa con un evento
    # cuando cambian los AJUSTES de una fuente (ver el comentario
    # grande al principio de esta función).
    def _sondear_cambios_externos():
        if not E.conectado:
            trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)
            return
        try:
            info_actual = E.cliente_obs.get_input_settings(nombre)
            ajustes_actuales = mod_obs_eventos._valor(info_actual, "input_settings", "inputSettings") or {}
        except Exception:
            trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)
            return

        for clave, actualizador in actualizadores.items():
            if arrastrando.get(clave):
                continue
            defecto = next((c.get("defecto") for c in esquema if c["clave"] == clave), None) if esquema else None
            valor_actual = mod_audio_filtros._valor_obs_o_defecto(ajustes_actuales, clave, defecto)
            if valor_actual is None:
                continue
            if not mod_audio_filtros._valores_equivalentes(valores_conocidos.get(clave), valor_actual):
                valores_conocidos[clave] = valor_actual
                actualizador(valor_actual)

        if esquema:
            _actualizar_visibilidad_condicional()

        trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)

    trabajo_sondeo["id"] = editor.after(500, _sondear_cambios_externos)
