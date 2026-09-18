# ConsolaOBS v1

Panel de control de audio para **OBS Studio** (Tkinter): mixer con VU meters LED, editor de filtros en vivo y soundboard de efectos. El código está separado en el paquete `consola_obs/` (configuración, OBS, audio e interfaz cada uno en su módulo).

## Características

- **Mixer en tiempo real**: faders en dB, medidores VU LED, mute, monitoreo, renombrado, colores, fuentes principales y drag & drop.
- **Soundboard**: pads con sonido e imagen; clic reproduce, clic de nuevo detiene con fundido; menú contextual y drag & drop.
- **Detección de carpetas**: los audios nuevos de `assets/Sondidos_pad/` se convierten solos en pads (entran primeros en la fila) con su imagen gemela de `assets/Imagenes_pad/`.
- **Audio local**: cada efecto suena en OBS y a la vez en los parlantes de la PC (miniaudio), con on/off en Ajustes → Audio.
- **Tipografías**: selector en Ajustes → Apariencia ("Tipografia de obs" = Open Sans por defecto, Predeterminada + las de `assets/fuentes/`), se aplica a toda la interfaz.
- **Editor de filtros** de audio de OBS en vivo (compresor, EQ, etc.).
- **Ventana de Propiedades** por fuente (clic derecho > Propiedades), calcada de la de OBS por tipo de entrada.
- **Agregar fuente** desde la consola (clic derecho en el panel de fuentes), con los tipos de audio de OBS, sus iconos SVG originales y sincronización con fuentes creadas/borradas desde OBS.
- **Eliminar fuente** desde la consola (clic derecho > Eliminar fuente…), borra la fuente de OBS con confirmación y protección de fuentes globales e internas.
- **Quitar de todas las escenas** (clic derecho), saca la fuente de todas las escenas sin borrarla de OBS.
- **Vaciar vs Eliminar pad**: el soundboard distingue entre vaciar el sonido (deja el botón vacío) y eliminar el pad de la grilla (corre los siguientes para cerrar el hueco).

## Requisitos

- Python 3.x y `pip install -r requirements.txt` (`obsws-python`, `Pillow`, `miniaudio`, `pymupdf`).
- OBS Studio con el servidor WebSocket v5 activado (puerto 4455).

## Uso

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Con doble clic en `compilar.bat` se genera `ConsolaOBS.exe` en la misma carpeta (con el icono de `assets/iconos/`).

## Estructura

```text
main.py
consola_obs/
├── app.py            # arranque (ventana + menú de ajustes)
├── estado.py         # estado compartido
├── constantes.py     # colores, medidas, esquemas
├── rutas.py          # carpetas y archivos
├── compat.py         # Pillow opcional
├── plataforma.py     # Windows/DPI/fuentes del sistema
├── configuracion.py  # JSONs de configuración
├── utilidades.py
├── obs/              # cliente + eventos de OBS
├── audio/            # filtros + propiedades de fuente + agregar fuente + reproducción (OBS y local)
└── ui/               # dibujo, medidores, tarjeta, soundboard, ventana, cabecera
```

## Documentación técnica

Funcionamiento, mecánicas y arquitectura en detalle:

## Índice
0. ¿Qué es?
1. Requisitos y dependencias
2. Arquitectura general (ventana Tk, dos clientes OBS, hilos)
3. Conexión a OBS (config, estado, formato de datos)
4. Modelo de datos / estado global
5. Eventos de OBS en tiempo real (bidireccional)
6. Medidores VU tipo LED + medidores de niveles (VU meters)
7. Saturación / "rojo" en el medidor
8. Fader/fuentes (tarjetas, mute, monitoreo, arrastre, menú)
8b. Eliminar fuente (clic derecho > Eliminar fuente…)
8c. Quitar de todas las escenas (clic derecho)
9. Fuentes "principales" (favoritos que se generan siempre)
## 10. Filtros de audio (crear, editar, ajustes en tiempo real)
## 10b. Propiedades de fuente (clic derecho > Propiedades)
## 11. Soundboard (pads de sonido, arrastre, miniaturas, configuración)
## 11b. Agregar fuente (clic derecho en el panel > Agregar fuente)
## 11c. Vaciar pad vs Eliminar pad
## 12. Cabecera, panel de fuentes, paneles drag con arrastre reordenable
## 13. Redimensionado responsive (factor de escala, velo, supersampling)
## 14. Persistencia (config JSON)
## 15. Estética y dibujo a mano (sombra, gradiente, engranaje, iconos)
## 16. Windows: anti-parpadeo nativo (WM_SETREDRAW, pincel de fondo)
## 17. Flux de arranque / cierre
## 18. Consideraciones de hilos y concurrencia
## 19. Cómo compilar el .exe


## 0. ¿QUÉ ES?
Programa de escritorio (Tkinter) que
actúa como "consola de sonido" remota para OBS Studio, conectándose al
plugin OBS WebSocket v5. Reemplaza el flujo incómodo de "ir al mixer
de OBS → buscar la fuente → mover fader" por un panel estilizado tipo
mesa de mezcla, con:

- Un fader (deslizador de volumen en dB) por cada fuente de audio.
- Medidores de nivel VU tipo LED con saturación en rojo.
- Botones de mute (🔇) y de monitoreo por auriculares (🎧).
- Filtros de audio reales de OBS editables en vivo (compresor, EQ...).
- Un soundboard con pads que reproducen sonidos/efectos bajo demanda.
- Fuentes marcadas como "principales" que se aseguran activas en todas las escenas.
- Reordenamiento por arrastre tanto de tarjetas de fuente como de pads.
- Todo sincronizado en tiempo real con OBS, en ambas direcciones.

Todo el dibujo de la interfaz se hace a mano sobre Canvas de Tk (sin
imágenes externas obligatorias), con estética oscura profesional y
fuentes tipográficas propias opcionales (assets/fuentes/*.ttf|*.otf).


## 1. REQUISITOS Y DEPENDENCIAS
Python 3.x (se usa solo biblioteca estándar de Tk, más):

- obsws-python  → cliente de OBS WebSocket v5 (IMPORTANTE: es la base de toda la integración). Instalar:  pip install obsws-python
- Pillow (opcional) → mejora de calidad:
  - Miniaturas de pads redondeadas/antialias (LANCZOS).
  - Círculos/bordes con supersampling para evitar el pixelado.
  - Captura de imagen de la ventana para el "velo" de redimensionado.
  - Carga de logo/fondos de cabecera. Si Pillow falta, el programa intenta instalarlo solo con pip en el primer arranque; si no se puede, funciona igual con bordes lisos.

Importaciones dinámicas y tolerantes:
- PIL (Image, ImageDraw, ImageOps, ImageTk, ImageFile).
- PIL.ImageGrab (se importa por separado; si falta, no rompe).
- En Windows: ctypes/usuario32/gdi32 (solo para trucos nativos de anti-parpadeo y registro de fuentes).

OBS: debe estar corriendo un servidor OBS-WebSocket v5 (puerto por
defecto 4455). La contraseña/host/puerto se guardan en
config_conexion.json.


## 2. ARQUITECTURA GENERAL
Código separado en el paquete `consola_obs/` (cada parte en su módulo, con el estado compartido en `estado.py` y las constantes en `constantes.py`):

(a) Dos clientes OBS separados (`obs/cliente.py` + `obs/eventos.py`):
  - cliente_obs  → cliente SÍNCRONO (con lock) para ejecutar comandos (pedidos) contra OBS. Todos los comandos se serializan con un threading.Lock para no mandar dos pedidos sobre el mismo socket a la vez.
  - cliente_eventos → cliente asíncrono de EVENTOS (OBS-WebSocket push de eventos), que se registra con callbacks para recibir actualizaciones en tiempo real.

(b) Arquitectura de hilos:
  - La UI corre en el hilo principal de Tk (ventana.mainloop()).
  - La conexión, los pedidos de volumen, la lectura de niveles VU y los refrescos de ganancia corren en hilos daemon.
  - NUNCA se llama a la red desde el hilo de Tk directamente: las operaciones de red van a hilos secundarios y los resultados se entregan a la UI con ventana.after(0, ...) o se guardan en diccionarios globales que el bucle VU lee cada 33 ms.
  - `_lock_pedidos_obs` protege el socket síncrono (see clase _ClienteOBSSincronizado, que envuelve cada método con threading.Lock vía __getattr__).
  - `_lock_sincronizar_escenas` serializa las operaciones de crear/mover fuentes entre escenas (evita duplicarla dos veces si dos hilos corren a la vez).

(c) Ciclos de refresco (ventana.after):
  - Medidores VU: cada INTERVALO_VU_MS (33 ms ≈ 30 fps).
  - Ganancia de filtros: cada INTERVALO_REFRESCO_GANANCIA_MS (1000 ms).
  - Sondeo de cambios externos de filtros mientras un editor está abierto: cada ~500 ms.
  - Redibujado de la cabecera (degradado): con throttle tras 120 ms.
  - Reajuste de columnas de fuentes y soundboard: con throttle tras 30 ms (solo reubica, nunca reconstruye).


## 3. CONEXIÓN A OBS
CS: Se guarda en config_conexion.json {host, puerto, password}.
Defaults: host "localhost", puerto 4455.

### Flujo:
- al arrancar se carga la config previa y se muestra el panel de conexión en la cabecera (Host, Puerto, Contraseña, botón CONECTAR).
- conectarse obs() → comprueba conectado y conecta con obsws-python: ClienteWebSocket(host, puerto, password). Si hay error de conexión lo muestra en un messagebox.
- tras conectar: lista fuentes (get_input_list), escenas (get_scene_list), y dispara el refresco de estados.

Formato de datos: OBS-WebSocket devuelve tanto nombres snake_case como
camelCase según la versión del cliente. Se usa `_valor(datos, clave_obs,
clave_obs_camel)` para leer un campo tolerando ambos nombres, y
`_valor_obs_o_defecto` para los ajustes de filtros.

### Cambios de estado que se afectan al conectar/desconectar:
- estados globales conectado (bool).
- el medidor se pone en gris/atenuado cuando la fuente NO está en la escena activa (ver abajo).


## 4. ESTADO GLOBAL / MODELO DE DATOS
Globals relevantes:
- conectado: bool de estado.
- cliente_obs, cliente_eventos: los dos clientes.
- fuentes: dict nombre → dict de widgets de la tarjeta de la fuente ({"contenedor", "cabecera", "fader", "mute", "monitor", "vu_canvas", "db", "color", "muted", "atenuado", ...}).
- niveles_actuales / niveles_crudos: último nivel por fuente (multiplicadores lineales, crudos y ya procesados).
- ultima_vez_saturado / ultima_vez_saturada_nivel: timestamps por fuente para el "clipping" sostenido.
- fuentes_principales: set() de nombres marcados como principal.
- orden_fuentes: lista (orden visible de las tarjetas).
- colores_fuentes: dict nombre → color de etiqueta de tarjeta.
- escena_actual_nombres / escena_actual_obtenida: fuente activa en la escena en vivo.
- config_soundboard: dict índice→{nombre, archivo, imagen, color} de los pads.
- config_conexion, config_interfaz, cargadas al inicio y guardadas al cerrar.


## 5. EVENTOS DE OBS EN TIEMPO REAL (OBS → UI, bidireccional)
El programa se suscribe a los callbacks de eventos de OBS-WebSocket y
los refleja en la UI al instante:

Inputs / auditorio:
- on_input_audio_monitor_type_changed → actualiza botón 🎧 monitor.
- on_input_mute_state_changed → actualiza botón 🔊/🔇.
- on_input_name_changed / on_input_removed → renombra/elimina tarjeta (al eliminar también limpia `fuentes_principales`, `colores_fuentes` y cierra Filtros/Propiedades de esa fuente, sección 8b).
- on_input_volume_meters → NUEVO: llega en un hilo; se guarda en niveles_actuales/niveles_crudos y se marca saturación.
- on_input_audio_* (monitor type, volume, ...) en general.

Escena / showing:
- on_current_program_scene_changed
- on_scene_item_* (created/removed/enable state changes) Se usa para saber qué fuentes están al aire en la escena activa y atenuar (poner en gris) las que no están.

Filtros:
- on_source_filter_created / removed / enable_state_changed / list_reindexed / name_changed → refrescan el editor de filtros.

Volumen en dB → fader: se sondea cada ~1 s la ganancia de cada fuente
(_sondear_ganancia_db) y se muestra en la tarjeta.

### REFRESCO DEL Volumen en % del fader:
- Cuando el usuario mueve el fader se ejecuta set_input_volume con el valor en dB (cambiar_volumen). Si el valor es muy bajo (< UMBRAL), set_input_volume con vol_mul=0.

### UI → OBS (cambios de la consola aplicados a OBS):
- Al mover el fader: set_input_volume.
- Al mutear: set_input_muted.
- Al monitorear: set_input_audio_monitor_type.
- Al editar/cambiar filtros: set_source_filter_settings, create_source_filter, set_source_filter_enabled, remove_source_filter, set_source_filter_index.
- Al reproducir un pad: set_input_settings + trigger_media_input_action (RESTART) sobre la fuente de efectos.
- Al crear/asegurar fuentes principales: create_scene_item.
- Al eliminar una fuente: remove_input (sección 8b). Todo esta sincronización es EN AMBAS DIRECCIONES y en tiempo real.


## 6. MEDIDORES VU TIPO LED
Cada tarjeta de fuente tiene un medidor de dos canales (barra LED
vertical, NUM_SEGMENTOS_VU=24 segmentos) que imita el medidor de OBS.
En Moderna es barra continua de dos canales con divisora fina del color del fondo
(`_dibujar_barra_obs`): mismo largo que el fader, cortes duros de color sin difuminado,
marcas perpendiculares de escala dB pegadas a la barra y línea de pico.

### Mecánica:
- Los niveles vienen de on_input_volume_meters (datos de OBS en tiempo real, no reconstruidos a mano excepto en el caso mute, ver abajo).
- `_y_para_db`: convierte dB (0..-60) en coordenada Y del canvas.
- MARCAS_DB = [0,-10,-20,-30,-40,-50,-60] dibujadas a la derecha.
- El medidor se actualiza en el bucle actualizar_vu_meters_ui cada INTERVALO_VU_MS (33 ms).
- `CAIDA_POR_CUADRO`: el nivel VISUAL cae suavemente (decaimiento animado parecido a un pico de consola real) mientras el nivel real sube de golpe: `db_visual = max(db_objetivo, db_visual - caida)`. Conserva el pico hasta que decae.
- Escala: el medidor va de -60 dB (abajo) a 0 dB (arriba).

### Lógica del nivel cuando está muteado (importante):
- Mientras la fuente está MUTEADA, OBS deja de reportar 'niveles_actuales' (los corta a 0), así que el medidor se reconstruye a mano: nivel_mul = niveles_crudos * ganancia_fader * ganancia_calibracion. Según el caso (ver CALIBRACION_VU_MUTEADO_DB, UMBRAL_NIVEL_MUTEADO_DIRECTO).
- A este nivel reconstruido se le aplica la atenuación por color gris si la fuente está atenuada.

### Silencio:
- UMBRAL_SILENCIO = -60 dB: por debajo se considera silencio (la etiqueta muestra "SILENCIO").

### Debug opcional:
- DEBUG_VU_FUENTE: si se le asigna un nombre de fuente, imprime en consola cada INTERVALO_DEBUG_VU_SEG (0,25 s) el nivel crudo y en dB, para calibrar el medidor. (Variables _log_debug_vu, _mostrar_debug_vu).

### Sincronía con los filtros:
- La ganancia de los filtros se suma al nivel mostrado (se refleja en el medidor) leyendo la ganancia real de cada filtro de audio (sección CALIBRACIÓN al inicio): así el medidor muestra el "post fader + filtros".


## 7. SATURACIÓN / "ROJO"
Cuando una fuente pasa de 0 dB(UMBRAL_SATURACION_MUL = 0.999, es decir
≈ 0 dB), el medidor LED se pone TODO EN ROJO (todos los segmentos
encendidos del color de saturación).

### Mecánica:
- Se detecta en el bucle de VU: si el nivel crudo >= UMBRAL, se registra el timestamp (ultima_vez_saturado[nombre] = time.monotonic()).
- El rojo se sostiene DURACION_SATURACION_SEG (1,0 s) después del pico: así el LED queda "pegado" en rojo aunque el pico haya sido un instante (igual que el indicador de clipping de OBS).
- Si la fuente está atenuada (gris) también hay rojo equivalente en gris (COLOR_LED_SATURADO_GRIS) para el modo gris.
- Los segmentos prendidos se pintan con color de saturación mientras `saturado` está activo; el resto queda apagado.
- Al desconectar se limpia ultima_vez_saturado.clear().

Medidor de clip "verdadero" también se marca desde
on_input_volume_meters (niveles >= 0 dB) y el bucle VU maneja el
decaimiento suave.

### Colores LED (degradado) por dB:
- Verde  (abajo)  → Amarillo (medio, -20..-9) → Rojo (arriba, -9..0).
- En modo gris: la misma escala pero en gris (COLOR_LED_*_GRIS).
- Segmento saturado: todo rojo (o gris claro si atenuado).


## 8. TARJETAS DE FUENTE (el fader)
Por cada fuente de audio de OBS se crea una tarjeta con:

Cabecera de la tarjeta:
- Nombre (doble clic = renombrar), en cabecera de alto fijo: los títulos largos se achican (hasta 5) y, si ni así entran en 2 renglones, se recortan con '…' para no desalinear el resto.
- Botón circular de mute 🔊/🔇 (toggle).
- Botón de monitoreo (en Moderna, SVG originales de OBS: auricular sobre cuadrado de estado verde con borde en salida, azul en solo-yo, headphones-off apagado; mute con X).
- LED de estado (verde si está en escena activa / encendida, gris si atenuada).
- Menú contextual (clic derecho) con: renombrar, "marcar como principal/quitar de principales", "Filtros…", "Propiedades…", color de etiqueta, "Quitar de todas las escenas…" y "Eliminar fuente…".
- Arrastre: clic sostenido sobre la cabecera + arrastre para REORDENAR las tarjetas (intercambio de posición).

Cuerpo de la tarjeta:
- Línea divisoria de acento bajo la cabecera (solo Moderna).
- Alto regulable en Ajustes → Apariencia → "Alto" (Compacto/Normal/Alto/Muy alto): el canal se estira y el alto total lo acompaña; combina con Chico/Mediano/Grande.
- Fader vertical (tk.Scale de -60..0 dB, resolución 0,5) que llama cambiar_volumen. Al arrastrar se congela/descongela el repintado para no parpadear y se espera a soltar.
- En Moderna el fader es estilo OBS (`_FaderOBS`): pista negra angosta prerenderizada con extremos redondos suaves del mismo largo que el medidor, relleno azul opaco hasta el final, pastilla que viaja de extremo a extremo sin cortarse y marcas perpendiculares cada 10 dB (0 a -50).
- Etiqueta de dB (solo cuando > UMBRAL).
- Medidor VU (ver sección 6).
- Alto con ajuste anti-recorte: si las métricas de fuente de la PC superan el alto fijo, la tarjeta crece lo justo (parejo en todas) para no cortar los iconos de abajo.

Atributo clave: `fuentes[nombre]` guarda entrada con la referencia del
algo "muted", "monitor", "principal", "atenuado", "vu_canvas", etc.

### diseños responsive:
- _ancho_preferido_fuente: calcula el ancho de catálogo de las tarjetas según el tamaño de ícono (Chico/Mediano/Grande).
- _reubicar_fuentes(): reposiciona las tarjetas en la grilla según las columnas disponibles, SIN recrearlas, para no perder el estado del fader mientras se redimensiona.
- _columna_disponible_fuentes: cuántas tarjetas entran por fila (histéresis de 40 px).


## 8b. ELIMINAR FUENTE (clic derecho > Eliminar fuente…)
`_eliminar_fuente` en `ui/tarjeta_fuente.py`: a diferencia del resto del menú, esto borra la fuente de OBS de verdad (no sólo la tarjeta), vía `remove_input` en un hilo daemon:
- Pide conexión activa; bloquea la fuente interna del soundboard (`Soundboard_Efectos`).
- Chequea en un hilo si es fuente global (Mic/Aux, Audio de escritorio de Configuración > Audio, vía `_leer_fuentes_globales_obs`): si lo es, no permite borrarla desde la consola para no dejar ese canal roto en OBS.
- Pide confirmación ("no se puede deshacer"); la tarjeta se quita sola al llegar `on_input_removed`, igual que si se hubiera borrado desde OBS.
- Limpieza centralizada (`_limpiar_referencias_fuente_borrada`): al desaparecer una fuente —desde la consola o desde OBS— se la saca de `fuentes_principales` y `colores_fuentes` (con guardado de config) y se cierran sus ventanas de Filtros/Propiedades si estaban abiertas.


## 8c. QUITAR DE TODAS LAS ESCENAS (clic derecho)
`_quitar_fuente_de_escenas` en `ui/tarjeta_fuente.py` + `quitar_fuente_de_todas_las_escenas` en `obs/cliente.py`: recorre todas las escenas y borra con `remove_scene_item` cada ítem de primer nivel que referencie a la fuente, SIN borrar el input (sigue existiendo y se puede reagregar desde OBS). Corre en hilo daemon, serializado con `_lock_sincronizar_escenas`, pide confirmación, bloquea la fuente interna del soundboard y las marcadas como principales (esas se mantienen en escena por definición), y al terminar refresca la lista e informa en cuántas escenas estaba. La tarjeta queda atenuada hasta que la fuente vuelva a alguna escena.


## 9. FUENTES "PRINCIPALES" (favoritas que se generan SIEMPRE)
Una fuente marcada como "principal" (★ en el menú contextual de la
tarjeta) se comporta distinto al resto:

- Se guarda en fuentes_principales (set) y se persiste en config_interfaz.json ("fuentes_principales": [..]).
- `_asegurar_fuente_en_todas_las_escenas(nombre)`: se asegura de que esa fuente esté creada Y ACTIVA en TODAS las escenas de OBS:
  - recorre cada escena (get_scene_list),
  - si no existe el item en esa escena → create_scene_item(escena, nombre, True),
  - si existe pero está deshabilitada → set_scene_item_enabled. Serializado con _lock_sincronizar_escenas (para no crear la fuente dos veces si dos hilos corren en paralelo).
- Se ejecuta al iniciar la conexión (`asegurar_fuentes_principales_en_todas_las_escenas()` al conectar) y cada vez que se marca una fuente como principal.
- Visualmente la tarjeta principal tiene borde de color teal resaltado (COLOR_BORDE_PRINCIPAL, borde más grueso).
- Renombrar: si se renombra una fuente principal, se actualiza el nombre en fuentes_principales también (ver `_renombrar_fuente()`).

DIFERENCIA CLAVE con el resto: el resto de las fuentes SOLO se muestran
tal como estén (grises si no están en la escena activa); las principales
se fuerzan a estar activas en todas las escenas siempre.


## 10. FILTROS DE AUDIO (tiempo real, bidireccional)
Ventana "Filtros" por fuente (desde el menú contextual):
- Lista los filtros de audio reales de la fuente (get_source_filter_list).
- Cada filtraje tiene: nombre + tipo + checkbox "habilitado" y botón de eliminar (✕) y botón Ajustes.
- Botón "➕ Agregar filtro": selector de nuevo filtro con los tipos de filtros de SONIDO permitidos (FILTROS_DE_SONIDO_PERMITIDOS), ícono y nombre amigable, cruzado contra la lista de kinds que OBS realmente ofrece (get_source_filter_kind_list).
- Al crear: se llama al editor de ajustes del filtro en el acto.

### Editor de ajustes de filtro (_abrir_editor_ajustes_filtro):
- Se dibujan CONTROLES según el tipo de filtro (no un editor genérico):
  - Slider (tk.Scale) para valores numéricos.
  - Checkbox para valores booleanos.
  - Combobox para listas (por ejemplo sidechain del compresor).
  - Entry de texto para el resto.
- Se usa ESQUEMA_FILTROS_CONOCIDOS: para limitador, compresor, ecualizador de 3 bandas y ecualizador básico se definen los campos REALES con nombre, rango, paso, sufijo y valor por defecto. Para otros tipos se usa un esquema genérico (RANGOS_CAMPOS_FILTRO) que adivina rango por el nombre del campo.
- SINCRONIZACIÓN BIDIRECCIONAL EN VIVO:
  - Al mover un slider → set_source_filter_settings(..., nombre, datos, True) se aplica al INSTANTE a OBS (y por tanto el sonido cambia a oído en vivo).
  - Mientras el editor está abierto se sondea cada ~500 ms get_source_filter_settings para traer cambios que vengan de OBS (o de otra instancia) y actualiza los controles, PERO sin pisar el slider que el usuario está arrastrando en ese instante. Usa _valores_equivalentes para no "temblar" por redondeos de dB.
  - También se suscribe a eventos de filtros de OBS para refrescar la lista en vivo (on_source_filter_*).
- Ganancia se refleja en el VU: _refrescar_ganancia_fuente, en un hilo, suma la ganancia de todos los filtros habilitados que aportan dB (gain_filter.db, compressor output_gain, etc.) y el medidor la muestra (sin reconstruir el nivel a mano: usa el nivel crudo).


## 10b. PROPIEDADES DE FUENTE (clic derecho > Propiedades)
Ventana "Propiedades" por fuente (`consola_obs/audio/propiedades.py`), agregada al menú contextual junto a Filtros:
- Arma los controles según el `inputKind` real de la fuente (get_input_settings), con el mismo criterio de esquema fijo que los filtros: ESQUEMA_PROPIEDADES_ENTRADA en estado.py cubre Mic/Aux y Audio de escritorio (WASAPI/CoreAudio/Pulse), Captura de audio de aplicación, Fuente de medios y Captura de ventana — calcados campo por campo, mismo orden y mismas opciones que la ventana real de OBS.
- Campos "lista_dinamica" (dispositivo de audio, ventana a capturar) se piden en vivo con get_input_properties_list_property_items, porque dependen de la PC de cada uno.
- Campos condicionales (`visible_si`) muestran/ocultan filas según el valor de otro campo — por ejemplo "Compatibilidad multiadaptador" sólo con método BitBlt en Captura de ventana — y se re-empaquetan en su ORDEN original al reaparecer, no al final de la lista.
- Cualquier tipo de fuente sin esquema fijo cae en un editor genérico (una fila por ajuste, adivinando el control por tipo de dato), igual criterio que un filtro sin esquema.
- Botonera igual a la de OBS: "Por defecto" (get_input_default_settings), "Cancelar" (restaura los ajustes que tenía la fuente al abrir la ventana, incluida la "X") y "Aceptar".
- SINCRONIZACIÓN BIDIRECCIONAL EN VIVO: los cambios se mandan con set_input_settings al instante, y se sondea cada ~500 ms para traer cambios hechos desde OBS, salteando el control que el usuario tiene agarrado — mismo mecanismo que el editor de filtros, porque OBS-WebSocket tampoco emite un evento de "ajustes de fuente cambiados".
- Fuente de medios (ffmpeg_source) calcada exacto a la ventana de OBS: mismo orden y etiquetas (incluidos decodificación por hardware y velocidad), con el Buffer visible sólo en modo red como en OBS.


## 11. SOUNDBOARD (pads con efectos)
El soundboard es una grilla de "pads" (botones) que reproducen sonidos
via una fuente de efectos de OBS (NOMBRE_FUENTE_EFECTOS, por defecto
"Soundboard_Efectos" — una fuente de extensión de medios "media_source").

### Estado y configuración:
- num_pads_soundboard (crece con "＋ AGREGAR PAD").
- config_soundboard.json guarda por índice: nombre (texto), archivo (ruta de audio), imagen (ruta de la miniatura), color (de etiqueta).
- Si no hay archivo asignado, el pad se dibuja vacío (gris, sin pulso).
- Detección de carpetas (`detectar_sonidos_carpeta`, al arrancar y con el botón 🔍): cada audio nuevo de `assets/Sondidos_pad/` entra primero (posición 0, corriendo a los demás) con su imagen gemela de `assets/Imagenes_pad/`; también completa imágenes faltantes en pads existentes. Sólo agrega pads nuevos al final si no hay ningún hueco.

### Dibujo de cada pad (_dibujar_pad, en construir_soundboard):
- Tarjeta plana con bordes redondeados en Canvas.
- Borde teal (#2fd693) si tiene sonido asignado, gris si vacío.
- LED de estado (verde si tiene sonido, gris si no).
- Imagen de fondo (miniatura con Pillow) o ícono ▶.
- Nombre debajo del pad (o "— VACÍO —").
- Hover: aclara la tarjeta.

### Acciones del pad:
- Clic = REPRODUCIR. La fuente de efectos se configura con el archivo (set_input_settings {local_file, ...}) y se lanza con trigger_media_input_action(RESTART) en un hilo. En paralelo, el mismo efecto sale por los parlantes de la PC (miniaudio, `audio/reproduccion.py`), con on/off en Ajustes → Audio.
- Clic de nuevo sobre el pad que suena = DETENER con fundido de 2 s (igual con o sin OBS: sin conexión el fundido lo hace el audio local). Mientras se apaga se ignoran más clics hasta que termina, para que el spam no buguee el sonido; la luz se apaga sola al terminar el audio.
- Botón de mute/escuchar ya cubierto por el fader de la fuente.
- Doble clic o menú contextual (clic derecho) del pad: reproducir, detener, reiniciar, asignar/cambiar sonido, asignar imagen, color de etiqueta, renombrar, vaciar o eliminar (sección 11c).
- Fuente en reposo siempre vacía: al terminar un sonido (fin natural, STOP, fundido o cierre de la app) se limpia `local_file` de `Soundboard_Efectos` (`_vaciar_fuente_efectos`), así al abrir OBS no se reproduce solo el último sonido aunque la consola esté cerrada.

### Arrastre de pads (reordenar):
- Se puede arrastrar un pad para reordenarlos (mismo mecanismo que las tarjetas de fuente: _iniciar_arrastre_pad, _mover_arrastre_pad, _soltar_arrastre_pad). Al soltar sobre otro pad se intercambian.
- Indices se persisten (orden en config + configuración de interfaz).

Colores de etiqueta de pads: paleta PALETA_ETIQUETAS (con color del
pad de borde y del LED).

### Miniaturas (Pillow):
- `_obtener_imagen_decodificada`/`_cargar_miniatura`: carga y cachea la imagen decodificada por ruta, y genera miniaturas por (indice, tamaño). Redimensiona la imagen para que entre completa en el pad sin recortarla (contain) o la escala con LANCZOS.
- Cache `_imagenes_decodificadas` y `_miniaturas_cargadas` por (ruta, tamaño), para no reabrir/redecodificar archivos pesados al reconstruir el soundboard (muy importante para no tildar).

### Grilla responsive del soundboard (_columnas_disponibles):
- Calcula cuántas columnas entran según el ancho del canvas y la medida real del pad (pad_ancho + 12 de padx, con tolerancia 25% para la última columna).
- El panel copia el ancho del canvas (sin esto quedaba angosto con un hueco a la derecha) y el sobrante se reparte parejo entre columnas con las celdas centradas (`_repartir_columnas_grilla`), así la grilla usa todo el ancho.
- Al cambiar el ancho sólo se reubica (`_reubicar_pads`); nunca se reconstruye por resize.

### Config de medidas (TAMANOS_ICONO):
- "Chico", "Mediano" (default), "Grande": cambian diámetro del botón, fuente de botón, ancho/alto del pad, íconos, fuente del nombre, etc.


## 11b. AGREGAR FUENTE (clic derecho en el panel > Agregar fuente)
Módulo nuevo `consola_obs/audio/fuentes.py`. Clic derecho sobre una zona VACÍA del panel de fuentes (no sobre una tarjeta: esa tiene su propio menú) abre `_abrir_menu_contextual_panel_fuentes` (en `ui/tarjeta_fuente.py`), atado tanto al canvas como al frame interno para cubrir cualquier hueco vacío.
- El menú tiene un submenú "➕ Agregar fuente" con los tipos de entrada de AUDIO (ENTRADAS_DE_AUDIO_PERMITIDAS en estado.py: Captura de audio de aplicación, Captura de entrada audio, Captura de salida de audio, Multimedia), cruzados en el momento contra get_input_kind_list para no ofrecer un tipo que esa instancia/plataforma de OBS no tenga — mismo criterio que FILTROS_DE_SONIDO_PERMITIDOS. Nombres y orden calcados del menú "Agregar fuente" real de OBS.
- "⋯ Otros tipos de fuente…" abre el selector completo (`abrir_selector_nueva_fuente`), con checkbox "Mostrar todos los tipos que informa OBS" para los tipos que no son de audio (captura de ventana, navegador, etc., listados con su kind crudo porque dependen de los plugins de cada usuario).
- Al elegir un tipo desde el submenú (`agregar_fuente_de_tipo`): pide el nombre (sugerido = nombre del tipo), lo numera si ya existe (los nombres de fuente son únicos en todo OBS, no por escena), crea la fuente en la escena AL AIRE con create_input(..., None, True) (nace con los ajustes de fábrica del tipo) y abre automáticamente su ventana de Propiedades (sección 10b) a los 400 ms.
- SINCRONIZACIÓN: on_input_created/on_input_removed (obs/eventos.py) refrescan la lista sola cuando una fuente se crea o se borra desde DENTRO de OBS (antes sólo se enteraba si el cambio tocaba la escena activa, así que una fuente global de audio —Mic/Aux, Audio de escritorio— no se detectaba hasta apretar "Actualizar fuentes"). Los refrescos se agrupan con ~400 ms de espera para no relanzar una actualización completa por cada evento si OBS manda varios juntos, y esperan a que termine un refresco en curso en vez de superponerse.
- El botón "AGREGAR FUENTE" del menú de Ajustes (barra lateral) sigue existiendo como atajo al selector completo.


## 11c. VACIAR PAD vs ELIMINAR PAD
Menú contextual del pad en `ui/soundboard.py` (100% local: los pads no son objetos de OBS, todos comparten la única fuente `Soundboard_Efectos`):
- **Vaciar pad** (`_quitar_pad`, sólo si tiene sonido): borra nombre/archivo/imagen pero deja el botón vacío en su lugar (conserva el color de etiqueta). Invalida su miniatura cacheada.
- **Eliminar pad** (`_eliminar_pad`, siempre visible): saca el pad de la grilla por completo, corre todos los posteriores una posición hacia atrás para cerrar el hueco (inverso a `_insertar_pad_al_principio`) y decrementa `num_pads_soundboard` (guarda `config_soundboard.json` + `config_interfaz.json`). Corta la reproducción activa antes de reordenar para no dejar la sesión apuntando a otro índice, e invalida las miniaturas cacheadas desde ese índice.


## 12. CABECERA Y PANELES
Cabecera (ventana_cabecera):
- Fondo con degradado vertical (COLOR_CABECERA_ARRIBA → COLOR_CABECERA_ABAJO) dibujado en Canvas.
- Logo (marco_icono_cabecera): carga assets/iconos/logo_cabecera.png con Pillow (o dibuja un ecualizador a mano si no está → _dibujar_icono_ecualizador).
- Título "CONSOLA OBS" + subtítulo.
- Estado de conexión: etiqueta ● CONECTADO / ● DESCONECTADO (chips).
- Botón engranaje (⚙) que abre un menú desplegable "Ajustes" (barra superpuesta con: Host, Puerto, Contraseña, botones CONECTAR/ DESCONECTAR/ACTUALIZAR, selector de diseño y orientación, selector de tamaño de íconos, tipografía). El cambio de tipografía se aplica en el acto a todo (cuerpo reconstruido + menú/cabecera re-fuenteados, sin reabrir).
- Botón CONECTAR principal.
- Selector de diseño de la vista (TAMANOS_ICONO): Chico/Mediano/Grande.

Barra de acción inferior: botones para agregar pads, conectar, etc.

### Orquestación de paneles (orientacion_paneles):
- Las dos grillas (fuentes y soundboard) se ordenan según la config "orientacion_paneles" (vertical/horizontal) y "orden_paneles" (fuentes arriba/abajo o izquierda/derecha), persistidos en config_interfaz.json. La posición del divisor se guarda al cerrar.


## 13. REDIMENSIONADO (estilo soundboard de Nico)
Tamaños fijos por ajuste de íconos (Chico/Mediano/Grande), sin importar
el tamaño de la ventana. Al mover el borde o el divisor, las grillas
sólo se REUBICAN (grid_forget + grid, sin destruir ni crear nada, con
un toque de calma de 30 ms): los pads y faders se mueven de fila/
columna en vivo y nunca parpadean. Si falta espacio, aparece scroll.
Sólo se reconstruye con acciones explícitas (tamaño de íconos, diseño,
tipografía, agregar/quitar pads).
Regla de columnas: pads con tolerancia 25% (la última columna puede
quedar tapada hasta un cuarto); faders a piso estricto (apenas algo
queda tapado, baja de fila).
Render gate: al moverse algo, sólo los pads se tapan hasta asentarse
(reacomodo + pintado forzado + destape a los 150 ms de quietud); los
faders nunca se ocultan, y cada tarjeta tapada por el borde no se
muestra hasta volver a verse.

### Anti-parpadeo al redimensionar (win32):
- _fijar_color_fondo_nativo: cambia el pincel de fondo de la clase de ventana (SetClassLongPtrW + CreateSolidBrush) para que el fondo sea del color oscuro correcto (evita el flash blanco).
- Velo de redimensionado: se usa sólo en reconstrucciones explícitas, tapando con una "foto" (ImageGrab) mientras se arma todo de una sola vez.

### Supersampling (antialias sin pixelado):
- FACTOR_SUPERSAMPLING_CIRCULOS = 6: los círculos (botones, LED, pads) se dibujan en un canvas 6 veces más grande y se reducen con ImageOps.fit + LANCZOS para que los bordes salgan suaves.
- _dibujar_rect_redondeado, _dibujar_boton_circular, _dibujar_gradiente etc. dibujan a mano, con Pillow si disponible.

Al cambiar el tamaño, tanto faders (_reubicar_fuentes) como pads
(_reubicar_pads) sólo se reposicionan en la grilla: ningún widget se
destruye ni se recrea, así no hay nada que parpadee.


## 14. PERSISTENCIA (JSON)
Archivos (se guardan en `config/` junto al .py/.exe):

- config/config_conexion.json   {host, puerto, password}
- config/config_soundboard.json {num_pads_soundboard, pads: {indice: {nombre, archivo, imagen, color}}}
- config/config_interfaz.json   {orientacion_paneles, orden_paneles, tamano_icono, colores_fuentes, fuentes_principales, posicion_divisor_*, geometria_ventana, columnas_soundboard?}

Se cargan al arrancar (si existen) con try/except, y se guardan al
cerrar (al_cerrar) junto con la posición/geometría de la ventana y la
config del usuario. Todo cambio de fuente principal, color, orden, etc.
se guarda de inmediato (guardar_config_interfaz / guardar_config_soundboard).
`config_conexion.json` y `config_*.json` están ignorados por git (la contraseña de OBS nunca se versiona).

### Assets (se auto-generan carpetas + LEEME.txt de ejemplo):
- assets/iconos/   (app_icon.ico|.png, logo_cabecera.png)
- assets/fondos/   (fondos opcionales)
- assets/fuentes/  (.ttf/.otf libres de instalar)

### Fuentes personalizadas:
- _registrar_fuentes_personalizadas: por cada .ttf/.otf en la carpeta, lee el nombre real de la familia desde la tabla 'name' del archivo (struct) y la registra SOLO para este proceso:
  - Windows: AddFontResourceExW (PRIVATE).
  - macOS:   CTFontManagerRegisterFontsForURL.
  - Linux:   copia a ~/.local/share/fonts + fc-cache. Si falla, ignora y sigue con la fuente del sistema.


## 15. ESTÉTICA / DIBUJO A MANO
Todo se dibuja sobre tk.Canvas aleatoriamente con funciones propias:

- _dibujar_rect_redondeado(canvas, x0,y0,x1,y1, radio, fill, outline...): rectángulo con esquinas redondeadas (Pillow si hay, sino con arcos).
- _dibujar_boton_circular / _crear_boton_circular: botón circular de "vidrio" con anillo teal, icono central y hover (resalta). Se usa para mute/monitor y botones pequeños de los pads.
- _crear_boton_circular con gradiente y sombra difusa.
- _dibujar_gradiente_vertical: sobre un Canvas con bandas de color.
- _dibujar_engranaje: polígono de 10 dientes (para el botón ajustes).
- _dibujar_icono_ecualizador: barras de EQ dibujadas con canvas.
- _aclarar_color/_oscurecer_color/_mezclar: helpers de color.
- Colores principales: fondo #10141b, tarjetas #1a202b, acento teal #2fd693, rojo #ff5d6c, texto blanco.
- FUENTE_UI = "Segoe UI" (Windows) o fuente del sistema.

Paletas de color por etiqueta: PALETA_ETIQUETAS (rojo, naranja,
amarillo, verde, teal, azul, índigo, violeta, magenta).


## 16. WINDOWS: ANTI-PARPADEO NATIVO
Solo en win32, con ctypes:
- _congelar_pintado_ventana(): envía WM_SETREDRAW(0) al HWND real de la ventana (mediante _hwnd_ventana_real, que sube por la jerarquía hasta la ventana raíz de Windows) para que Windows deje de repintar las franjas nuevas durante el arrastre del borde.
- _descongelar_pintado_ventana(): WM_SETREDRAW(1) y RedrawWindow con RDW_INVALIDATE|ERASE|ALLCHILDREN|UPDATENOW para un único repintado limpio al soltar.
- _fijar_color_fondo_nativo(hex): SetClassLongPtrW + CreateSolidBrush para que el color de FONDO nativo de la clase de ventana sea el mismo oscuro (evita el flash blanco de Windows al borrar).
- Manejo correcto de tipos: se especifican los argumentos/retorno (c_void_p, c_uint... ) para que los HWND de 64 bits no se trunquen.

Esto se invoca durante el arrastre de redimensionado, así el usuario
ve el último cuadro completo hasta que suelta (sin parpadeos).


## 17. FLUJO DE ARRANQUE / CIERRE
Arranque:
1. Leer config (si existe).
2. Registrar fuentes personalizadas.
3. Construir ventana + cabecera (engranaje, estado, logo).
4. Conectar a OBS (si la config lo permite) y refrescar fuentes.
5. Arrancar ciclos: medidores VU (after 33ms), sondeo de ganancia,
sondeo de filtros (si editor abierto), etc.
6. Mostrar ventana (mainloop).

### Cierre (al_cerrar):
- Desconectar de OBS de forma segura.
- Guardar config de conexión, soundboard e interfaz (incluida la posición del divisor y geometría).
- Cerrar la ventana (ventana.destroy()).


## 18. CONCURRENCIA (útil para reconstruir)
Reglas de oro implementadas:
- La red y los medidores VU corren en hilos daemon; la UI se toca solo desde el hilo principal vía ventana.after(0,...).
- Todos los comandos OBS pasan por un lock (un único socket síncrono compartido).
- Las operaciones de crear la misma fuente dos veces se previenen con lock y con la comprobación "¿ya está en la lista?" ANTES de crear.
- Las ventanas de diálogo se guardan en structs globales para no abrir dos iguales (por ej. un solo editor de filtros a la vez).
- El redimensionado se "congela" nativamente y se reconstruye una vez al soltar (con velo), evitando trabajo en cada evento.
- Cachés de imágenes por ruta para no redecodificar en cada reconstrucción del soundboard.

### HILOS (resumen):
- hilo principal: Tk (UI).
- hilo de VU: recorre fuentes y pide niveles a OBS.
- hilo de eventos OBS: recibe callbacks push.
- hilos puntuales para: reproducir sonido del pad (daemon), asegurar fuente en todas las escenas, sondeo de ganancia de filtros, refresco de estados al conectar.
- Los valores que comparten los hilos con la UI (niveles_actuales, ultima_vez_saturado, fuentes...) viven en dicts globales y se protegen con locks cuando hay riesgo de carrera; el resto se copia por valor (inmutables) hacia la UI.


## 19. CÓMO COMPILAR A .EXE
Doble clic en `compilar.bat` (usa PyInstaller, Windows):

```
py -m PyInstaller --onefile --windowed --name ConsolaOBS --hidden-import cffi --collect-all pymupdf --version-file "version_info.txt" --icon "assets\iconos\app_icon.ico" main.py
```

- --onefile: un solo .exe (queda en la misma carpeta, junto a `main.py`).
- --windowed: sin consola (GUI).
- --hidden-import cffi: miniaudio lo necesita a nivel C y PyInstaller no lo detecta solo; sin esto el .exe no tiene audio local.
- Los JSON de configuración y `assets/` viven junto al ejecutable (ver `rutas.py`: en modo congelado usa la carpeta del .exe real).

Nota: al estar "congelado" (sys.frozen), CARPETA_SCRIPT apunta a la
carpeta del ejecutable (sys.executable) y no a la temporal _MEIxxxx,
para que los JSON de configuración y los assets persistan junto al
.exe real.


## Estado actual del proyecto
- Entrada: `main.py` → paquete `consola_obs/` (ver Estructura arriba).
- El .exe se genera con `compilar.bat` en esta misma carpeta (`ConsolaOBS.exe`, no se versiona).
- La contraseña de OBS vive en `config/config_conexion.json` (local, ignorado por git); el resto de la config en `config/config_soundboard.json` y `config/config_interfaz.json`.

