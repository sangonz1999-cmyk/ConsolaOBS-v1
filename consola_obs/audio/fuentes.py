"""Fase 3 del plan de mejoras: agregar una fuente de audio nueva desde
la consola, sin tener que ir a OBS.

Mismo criterio de siempre: el selector se arma con lo que ESTA
instancia de OBS realmente tiene registrado (GetInputKindList), no con
una lista fija, y al crear la fuente (CreateInput) se abre en el acto
la ventana de Propiedades de la Fase 2 para configurarla, tal como
hace OBS cuando agregás una fuente desde el "+" de una escena.
"""

import sys
import time
import tkinter as tk

from tkinter import messagebox, simpledialog, ttk

from consola_obs import estado as E
from consola_obs import red as mod_red
from consola_obs.obs import eventos as mod_obs_eventos
from consola_obs.audio import filtros as mod_audio_filtros
from consola_obs.audio import propiedades as mod_audio_propiedades
from consola_obs.ui import dibujo as mod_ui_dibujo
from consola_obs.ui import tarjeta_fuente as mod_ui_tarjeta


class _ListaNoLeida(Exception):
    """No se pudo leer la kind list del OBS (enlace caído/lento). No
    es lo mismo que 'no trae el tipo': distingue el cartel."""


def _plataforma_obs_efectiva():
    """Plataforma del OBS al que estamos conectados (remoto: la que
    informó al conectar; misma PC: la local), en minúsculas."""
    try:
        if E.conectado and not mod_red.es_localhost(E.host_conectado or "localhost"):
            return str(getattr(E, "plataforma_obs", "") or "").lower()
    except Exception:
        pass
    try:
        p = str(sys.platform or "").lower()
    except Exception:
        return ""
    if p.startswith("win"):
        return "windows"
    if p.startswith("darwin"):
        return "macos"
    return "linux"


def _primer_kind_para_obs(candidatos):
    """Candidatos ordenados según la plataforma del OBS (para cuando no
    se pudo leer la kind list: antes se ofrecía wasapi primero en
    todos lados y en un OBS Linux eso era error 605 seguro)."""
    if not candidatos:
        return None
    plat = _plataforma_obs_efectiva()
    if "mac" in plat or "darwin" in plat:
        marcas = ("coreaudio",)
    elif "linux" in plat:
        marcas = ("pulse", "pipewire", "jack")
    elif "win" in plat:
        marcas = ("wasapi",)
    else:
        return candidatos[0]

    def _rango(kind):
        for i, marca in enumerate(marcas):
            if marca in kind:
                return (i, candidatos.index(kind))
        return (len(marcas), candidatos.index(kind))

    try:
        return sorted(candidatos, key=_rango)[0]
    except Exception:
        return candidatos[0]


def _leer_kinds_obs(intentos=3):
    """Kind list del OBS con reintentos (el enlace remoto a veces
    pierde una): lista o None si ni así se pudo leer. Nunca lanza."""
    ultimo = None
    for intento in range(max(1, intentos)):
        try:
            respuesta = E.cliente_obs.get_input_kind_list()
            kinds = mod_obs_eventos._valor(respuesta, "input_kinds", "inputKinds") or []
            return list(kinds)
        except Exception as e:
            ultimo = e
            try:
                if intento < intentos - 1:
                    time.sleep(0.4)
            except Exception:
                pass
    try:
        print(f"No se pudo leer la lista de tipos de fuente: {ultimo}")
    except Exception:
        pass
    return None


def _crear_fuente_con_reintento(escena, nombre_final, kind_pedido):
    """Crea la fuente; si OBS rechaza el kind (605: no soportado en
    esa versión/plataforma), reintenta solo con los otros kinds del
    mismo grupo que SÍ informa GetInputKindList. Devuelve el kind con
    el que se creó. Si nada anda, relanza el último error."""
    ultimo_error = None
    try:
        E.cliente_obs.create_input(escena, nombre_final, kind_pedido, None, True)
        return kind_pedido
    except Exception as e:
        ultimo_error = e
        if "605" not in str(e):
            raise
    # 605: buscar alternativas del mismo grupo entre lo que el OBS dice tener
    ofrecidos = _leer_kinds_obs()
    if ofrecidos is None:
        raise _ListaNoLeida(
            "No se pudo leer la lista de tipos de este OBS. Reintentá en unos segundos.")
    ofrecidos = set(ofrecidos)
    grupo = None
    for _nombre, _icono, candidatos in E.ENTRADAS_DE_AUDIO_PERMITIDAS:
        if kind_pedido in candidatos:
            grupo = candidatos
            break
    if grupo:
        for alternativo in grupo:
            if alternativo == kind_pedido or alternativo not in ofrecidos:
                continue
            try:
                E.cliente_obs.create_input(escena, nombre_final, alternativo, None, True)
                return alternativo
            except Exception as e2:
                ultimo_error = e2
    raise ultimo_error


def _tipos_de_entrada_disponibles(kinds_que_ofrece_obs, incluir_todos=False):
    """Cruza el catálogo fijo (ENTRADAS_DE_AUDIO_PERMITIDAS) con lo que
    esta instancia de OBS informa en GetInputKindList, para no ofrecer
    un tipo de fuente que esta versión/plataforma de OBS no trae.
    Devuelve una lista de (nombre_amigable, archivo_svg, kind_real).

    Con incluir_todos=True se agregan además, al final y en orden
    alfabético, todos los demás kinds que informó OBS: son los tipos
    que no son de audio (captura de ventana, navegador, imagen, etc.).
    No se les puede poner un nombre amigable a mano porque dependen de
    los plugins instalados, así que se muestran con su propio kind."""
    conjunto = set(kinds_que_ofrece_obs)
    opciones = []
    kinds_usados = set()

    for nombre, icono, kinds_posibles in E.ENTRADAS_DE_AUDIO_PERMITIDAS:
        kind_real = next((k for k in kinds_posibles if k in conjunto), None)
        if kind_real:
            opciones.append((nombre, icono, kind_real))
            kinds_usados.add(kind_real)

    if incluir_todos:
        for kind in sorted(k for k in conjunto if k not in kinds_usados):
            opciones.append((kind, E.SVG_POR_INPUT_KIND.get(kind, E.ICONO_ENTRADA_DESCONOCIDA), kind))

    return opciones


def _escena_donde_crear():
    """OBS exige una escena al crear una fuente (CreateInput), porque una
    fuente nueva siempre nace como ítem de alguna escena. Se usa la que
    está al aire; si por algo no se puede leer, la primera de la lista."""
    try:
        respuesta = E.cliente_obs.get_current_program_scene()
        escena = mod_obs_eventos._valor(
            respuesta,
            "current_program_scene_name", "currentProgramSceneName",
            "scene_name", "sceneName",
        )
        if escena:
            return escena
    except Exception as e:
        print(f"No se pudo leer la escena al aire: {e}")

    try:
        escenas = [
            mod_obs_eventos._valor(s, "scene_name", "sceneName")
            for s in E.cliente_obs.get_scene_list().scenes
        ]
        for escena in escenas:
            if escena:
                return escena
    except Exception as e:
        print(f"No se pudieron listar las escenas: {e}")

    return None


def _nombres_de_fuentes_existentes():
    try:
        return {
            mod_obs_eventos._valor(i, "input_name", "inputName")
            for i in E.cliente_obs.get_input_list().inputs
        }
    except Exception as e:
        print(f"No se pudo leer la lista de fuentes: {e}")
        return set(E.fuentes.keys())


def tipos_de_audio_para_menu():
    """Los tipos de entrada de AUDIO que esta instancia de OBS tiene
    registrados, listos para armar el submenú de "Agregar fuente" del
    clic derecho. Devuelve (nombre_amigable, archivo_svg, kind).

    Si por lo que sea no se puede preguntar (justo se cayó la conexión),
    se devuelve el catálogo ordenado por plataforma: el menú se puede
    dibujar igual y al crear se reintenta solo con lo que el OBS traiga."""
    kinds = _leer_kinds_obs()
    if kinds is None:
        return [(n, i, _primer_kind_para_obs(ks)) for n, i, ks in E.ENTRADAS_DE_AUDIO_PERMITIDAS]

    return _tipos_de_entrada_disponibles(kinds, incluir_todos=False)


def agregar_fuente_de_tipo(kind, nombre_sugerido):
    """Crea una fuente del tipo 'kind' en la escena que está al aire y
    le abre la ventana de Propiedades, preguntando antes qué nombre
    ponerle (igual que OBS, que también pide el nombre primero).

    Es el camino corto que usa el clic derecho sobre una zona vacía del
    panel de fuentes; el selector completo
    (abrir_selector_nueva_fuente) sigue existiendo para cuando hace
    falta elegir entre todos los tipos que informa OBS."""
    if not E.conectado:
        messagebox.showinfo("Sin conexión", "Conectate a OBS para agregar una fuente.")
        return

    escena = _escena_donde_crear()
    if not escena:
        messagebox.showerror(
            "Sin escenas",
            "No hay ninguna escena en OBS donde crear la fuente.\nCreá una escena primero.",
        )
        return

    nombre_pedido = simpledialog.askstring(
        "Agregar fuente",
        f"Nombre de la fuente nueva ({nombre_sugerido}):",
        initialvalue=nombre_sugerido,
        parent=E.ventana,
    )
    if nombre_pedido is None:
        return
    nombre_pedido = nombre_pedido.strip()
    if not nombre_pedido:
        return

    # En OBS el nombre de una fuente es único en TODO el programa, no
    # por escena: si ya existe, se numera en vez de fallar.
    existentes = _nombres_de_fuentes_existentes()
    nombre_final = nombre_pedido
    contador = 2
    while nombre_final in existentes:
        nombre_final = f"{nombre_pedido} {contador}"
        contador += 1

    try:
        # inputSettings en None = nace con los ajustes de fábrica de su
        # tipo, igual que al crearla desde OBS. Si el kind pedido no va
        # en este OBS (típico 605: menú armado contra otro OBS), se
        # reintenta solo con los del mismo grupo que este OBS sí trae.
        kind_final = _crear_fuente_con_reintento(escena, nombre_final, kind)
    except _ListaNoLeida as e:
        messagebox.showerror("Sin respuesta del OBS", str(e))
        return
    except Exception as e:
        if "605" in str(e):
            messagebox.showerror(
                "Tipo no soportado",
                f"Este OBS no trae ningún tipo compatible con '{nombre_sugerido}'.\n"
                 "Probá con otro tipo (ej Multimedia) o revisá los plugins del OBS.",
            )
        else:
            messagebox.showerror("Error", f"No se pudo crear la fuente.\n\n{e}")
        return

    mod_ui_tarjeta.actualizar()
    E.ventana.after(400, lambda: mod_audio_propiedades.abrir_propiedades(nombre_final))


def abrir_selector_nueva_fuente():
    """Ventana para elegir QUÉ tipo de fuente agregar y con qué nombre,
    equivalente al "+" de la lista de fuentes de OBS. Al confirmar crea
    la fuente en OBS, refresca la consola y abre automáticamente su
    ventana de Propiedades (punto 3.2 del plan)."""
    if not E.conectado:
        messagebox.showinfo("Sin conexión", "Conectate a OBS para agregar una fuente.")
        return

    try:
        kinds = _leer_kinds_obs()
    except Exception as e:
        messagebox.showerror(
            "Error",
            f"No se pudo obtener la lista de tipos de fuente disponibles.\n\n{e}",
        )
        return
    if kinds is None:
        messagebox.showerror(
            "Sin respuesta del OBS",
            "No se pudo leer la lista de tipos de fuente de este OBS.\n"
            "Reintentá en unos segundos.",
        )
        return

    if not kinds:
        messagebox.showinfo(
            "Sin tipos disponibles",
            "Esta versión de OBS no informó ningún tipo de fuente.",
        )
        return

    selector = tk.Toplevel(E.ventana)
    selector.title("Agregar fuente")
    selector.configure(bg="#10141b")
    selector.geometry("420x560")
    selector.transient(E.ventana)
    selector.grab_set()

    tk.Label(
        selector, text="Agregar fuente de audio", bg="#10141b", fg="white",
        font=(E.FUENTE_UI, 11, "bold"),
    ).pack(anchor="w", padx=12, pady=(12, 2))

    tk.Label(
        selector, text="Elegí el tipo de fuente:", bg="#10141b", fg="#8e9ab3",
        font=(E.FUENTE_UI, 9),
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
    mod_audio_filtros._habilitar_scroll_con_rueda(canvas_tipos)

    var_tipo_elegido = tk.StringVar(value="")
    var_nombre_fuente = tk.StringVar(value="")
    var_mostrar_todos = tk.BooleanVar(value=False)
    nombre_por_kind = {}
    _ultimo_sugerido = {"texto": ""}
    # Referencias vivas de los SVG del listado (sin esto Tk los
    # recolecta y las filas quedan sin icono).
    selector._imagenes_tipos = []

    def _al_cambiar_tipo(*_ignorar):
        # Si el usuario todavía no tocó el nombre a mano, se le sugiere
        # el nombre amigable del tipo elegido; si ya lo editó, se
        # respeta tal cual (mismo criterio que el selector de filtros).
        sugerido_nuevo = nombre_por_kind.get(var_tipo_elegido.get(), var_tipo_elegido.get())
        if var_nombre_fuente.get().strip() == _ultimo_sugerido["texto"]:
            var_nombre_fuente.set(sugerido_nuevo)
        _ultimo_sugerido["texto"] = sugerido_nuevo

    var_tipo_elegido.trace_add("write", _al_cambiar_tipo)

    def _reconstruir_lista():
        for hijo in marco_lista_tipos.winfo_children():
            hijo.destroy()
        selector._imagenes_tipos.clear()

        opciones = _tipos_de_entrada_disponibles(kinds, var_mostrar_todos.get())
        nombre_por_kind.clear()
        nombre_por_kind.update({kind: nombre for nombre, _icono, kind in opciones})

        if not opciones:
            tk.Label(
                marco_lista_tipos,
                text="Esta versión de OBS no informó ninguno de los tipos\n"
                     "de entrada de audio esperados.",
                bg="#10141b", fg="#8e9ab3", font=(E.FUENTE_UI, 9), justify="left",
            ).pack(anchor="w", pady=10)
            var_tipo_elegido.set("")
            return

        for nombre_amigable, icono, kind in opciones:
            foto = mod_ui_dibujo._imagen_svg(icono, 16)
            if foto is not None:
                selector._imagenes_tipos.append(foto)
                tk.Radiobutton(
                    marco_lista_tipos, text=nombre_amigable, image=foto, compound="left",
                    value=kind,
                    variable=var_tipo_elegido, bg="#10141b", fg="white",
                    activebackground="#1c2331", activeforeground="white",
                    selectcolor="#1a202b", font=(E.FUENTE_UI, 10), anchor="w",
                    justify="left", indicatoron=True, padx=6, pady=5, wraplength=340,
                ).pack(fill="x")
            else:
                tk.Radiobutton(
                    marco_lista_tipos, text=nombre_amigable, value=kind,
                    variable=var_tipo_elegido, bg="#10141b", fg="white",
                    activebackground="#1c2331", activeforeground="white",
                    selectcolor="#1a202b", font=(E.FUENTE_UI, 10), anchor="w",
                    justify="left", indicatoron=True, padx=6, pady=5, wraplength=340,
                ).pack(fill="x")

        # Si el tipo que estaba elegido desapareció al destildar
        # "mostrar todos", se vuelve al primero de la lista.
        if var_tipo_elegido.get() not in nombre_por_kind:
            var_tipo_elegido.set(opciones[0][2])
            var_nombre_fuente.set(opciones[0][0])
            _ultimo_sugerido["texto"] = opciones[0][0]

    _reconstruir_lista()

    tk.Checkbutton(
        selector, text="Mostrar todos los tipos que informa OBS (no sólo los de audio)",
        variable=var_mostrar_todos, command=_reconstruir_lista,
        bg="#10141b", fg="#8e9ab3", activebackground="#10141b", activeforeground="white",
        selectcolor="#1a202b", font=(E.FUENTE_UI, 8), anchor="w", wraplength=380,
        justify="left",
    ).pack(fill="x", padx=12, pady=(6, 0))

    marco_nombre = tk.Frame(selector, bg="#10141b")
    marco_nombre.pack(fill="x", padx=12, pady=(8, 4))
    tk.Label(
        marco_nombre, text="Nombre de la fuente:", bg="#10141b", fg="#8e9ab3",
        font=(E.FUENTE_UI, 9),
    ).pack(anchor="w")
    entrada_nombre = tk.Entry(
        marco_nombre, textvariable=var_nombre_fuente, bg="#1a202b", fg="white",
        insertbackground="white", relief="flat", font=(E.FUENTE_UI, 9),
    )
    entrada_nombre.pack(fill="x", ipady=3)

    etiqueta_error = tk.Label(
        selector, text="", bg="#10141b", fg="#ff8a95", font=(E.FUENTE_UI, 8),
        wraplength=390, justify="left",
    )
    etiqueta_error.pack(fill="x", padx=12)

    def _confirmar():
        kind = var_tipo_elegido.get()
        if not kind:
            etiqueta_error.config(text="Elegí un tipo de fuente.")
            return

        nombre_pedido = var_nombre_fuente.get().strip()
        if not nombre_pedido:
            etiqueta_error.config(text="Poné un nombre para la fuente.")
            return

        escena = _escena_donde_crear()
        if not escena:
            etiqueta_error.config(
                text="No hay ninguna escena en OBS donde crear la fuente.\n"
                     "Creá una escena primero."
            )
            return

        # En OBS el nombre de una fuente es único en TODO el programa
        # (no por escena): si ya existe, se numera igual que hace el
        # selector de filtros, para no chocar ni pisar nada.
        existentes = _nombres_de_fuentes_existentes()
        nombre_final = nombre_pedido
        contador = 2
        while nombre_final in existentes:
            nombre_final = f"{nombre_pedido} {contador}"
            contador += 1

        try:
            # inputSettings en None = la fuente nace con los ajustes de
            # fábrica de su tipo, igual que al crearla desde OBS; los
            # ajustes reales se tocan enseguida en la ventana de
            # Propiedades que se abre a continuación. Con reintento por
            # si el kind listado no se puede crear (605).
            _crear_fuente_con_reintento(escena, nombre_final, kind)
        except Exception as e:
            etiqueta_error.config(text=f"No se pudo crear la fuente.\n{e}")
            return

        selector.destroy()

        # Refresco de la consola + ventana de Propiedades de la fuente
        # recién creada (punto 3.2). Se da un respiro para que OBS
        # termine de registrarla antes de pedirle sus ajustes.
        mod_ui_tarjeta.actualizar()
        E.ventana.after(
            400, lambda: mod_audio_propiedades.abrir_propiedades(nombre_final)
        )

    marco_botones = tk.Frame(selector, bg="#10141b")
    marco_botones.pack(fill="x", padx=12, pady=10)

    tk.Button(
        marco_botones, text="Cancelar", command=selector.destroy,
        bg="#323b4c", fg="white", relief="flat", font=(E.FUENTE_UI, 9),
    ).pack(side="right", padx=(6, 0))

    tk.Button(
        marco_botones, text="Agregar", command=_confirmar,
        bg=E.color_acento(), fg="#131825", relief="flat", font=(E.FUENTE_UI, 9, "bold"),
    ).pack(side="right", ipadx=8)

    entrada_nombre.focus_set()
    entrada_nombre.select_range(0, "end")
    entrada_nombre.bind("<Return>", lambda e: _confirmar())
