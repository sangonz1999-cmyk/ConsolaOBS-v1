# Lista de paridad: Tkinter → Qt

Regla: la interfaz nueva (Qt) tiene que hacer **todo** lo que hace la actual (Tkinter). La interfaz vieja (`consola_obs/ui/`) no se borra hasta que cada ítem de este archivo esté verificado.

Fuente: el `README.md` (secciones 0 a 19), el código de `consola_obs/ui/`, `app.py` y `consola_obs/{sync,update}/`, y lo que se agregó en las Etapas 0 y 1.

## Cómo se marca cada ítem

| Marca | Significa |
|---|---|
| `[ ]` | pendiente |
| `[Q]` | hecho en Qt, todavía sin comparar con la versión Tkinter |
| `[x]` | verificado: se probó lado a lado con Tkinter y hace lo mismo |
| `[-]` | se descarta a propósito (anotar por qué y quién lo decidió) |

Los ítems con `(¿?)` los vi en el código pero el README no los explica: antes de darlos por buenos hay que mirar qué hacen exactamente.

Una mejora de diseño nunca justifica sacar una función. Si algo cambia de comportamiento, se anota acá y se consulta.

---

## A. Conexión con OBS

- [ ] A1. Campos Host, Puerto y Contraseña en Ajustes → Conexión; valores por defecto `localhost` / `4455`.
- [ ] A2. Botón CONECTAR / DESCONECTAR / CANCELAR según el estado.
- [ ] A3. Estado visible en la cabecera: CONECTADO, CONECTANDO…, RECONECTANDO…, DESCONECTADO.
- [ ] A4. Clic en el estado: reconecta con lo guardado; reintenta ya si está reconectando; abre Ajustes → Conexión si no hay nada guardado.
- [ ] A5. Conexión automática al abrir el programa si hay datos guardados.
- [ ] A6. Conexión en segundo plano (la ventana no se congela).
- [ ] A7. Vigilancia de la conexión (canal de eventos vivo + OBS contesta) y aviso "Es probable que se haya perdido la conexión…".
- [ ] A8. Reconexión automática con esperas de 2, 4, 8, 15 y 30 s; aviso de "Conexión recuperada".
- [ ] A9. Error de conexión manual explicado (host no resuelve, puerto, contraseña, firewall) con el paso donde falló.
- [ ] A10. Aviso de OBS menor a 28 (WebSocket 5.x).
- [ ] A11. Validación del puerto (tiene que ser un número).
- [ ] A12. Botón 📋 COPIAR MI IP (copia la IP de la PC al portapapeles con explicación).
- [ ] A13. Botón 🛡 FIREWALL (crea la regla del puerto; pide administrador si hace falta).
- [ ] A14. Campo Carpeta OBS (ruta de `assets` en la PC del OBS), con aviso si no corresponde al sistema del OBS, se guarda al salir del campo y se completa sola al sincronizar o al detectar un archivo bien puesto.
- [ ] A15. Atajo "Carpeta OBS" aprendida: si en OBS se pone un archivo a mano, el programa lo detecta y aprende la carpeta.
- [ ] A16. Los datos de conexión se guardan solo tras una conexión exitosa; la contraseña va cifrada.
- [ ] A17. Registro de la conexión en `config/conexion.log` y de errores en `config/consola.log`.

## B. Mezclador: tarjeta de fuente

- [ ] B1. Una tarjeta por cada fuente de audio de OBS (se omiten las que no tienen audio).
- [ ] B2. Nombre en la cabecera: títulos largos se achican (hasta 5) y se recortan con "…" si no entran en 2 renglones.
- [ ] B3. Doble clic en el nombre: renombrar (en OBS también; si es principal, se actualiza su nombre).
- [ ] B4. Fader vertical de -60 a 0 dB, resolución 0,5; etiqueta de dB y "SILENCIO" por debajo de -60.
- [ ] B5. Marcas de escala en el fader (cada 10 dB, 0 a -50).
- [ ] B6. Mover el fader aplica el volumen a OBS al instante, sin lag; por debajo del umbral manda silencio.
- [ ] B7. Botón de mute con icono propio (parlante / parlante tachado) y color según estado.
- [ ] B8. Botón de monitoreo: clic izquierdo alterna entre apagado y "yo + stream" (nunca pasa por "solo yo").
- [ ] B9. Monitoreo: clic derecho abre menú con los tres estados (🎧 OFF, 🎧 SOLO YO, 🎧 YO + STREAM), con su color (apagado, azul, verde).
- [ ] B10. El estado de mute, monitoreo y volumen se refleja en tiempo real cuando cambia desde OBS.
- [ ] B11. La tarjeta se ve atenuada (gris) si la fuente está muteada o fuera de la escena al aire.
- [ ] B12. Etiqueta de color por fuente (paleta de 9 colores) visible en la tarjeta.
- [ ] B13. Borde resaltado en las fuentes principales ★.
- [ ] B14. Arrastrar la cabecera para reordenar las tarjetas.
- [ ] B15. Grilla responsive: reacomoda las tarjetas según el ancho disponible sin recrearlas; scroll si falta lugar.
- [ ] B16. Tamaños de ícono Chico / Mediano / Grande.
- [ ] B17. Alto de tarjeta Compacto / Normal / Alto / Muy alto.
- [ ] B18. La tarjeta nunca recorta sus iconos según las métricas de la fuente de la PC.
- [ ] B19. Al arrastrar el fader no se repinta por eventos de OBS (no salta).
- [ ] B20. Quitar una fuente desde OBS la saca de la consola (y limpia principales, colores y ventanas abiertas de esa fuente).
- [ ] B21. Una fuente nueva creada desde OBS aparece sola (agrupando eventos ~400 ms).
- [ ] B22. Cambio de colección de escenas: título con 📁 y refresco completo.

## C. Medidores

- [ ] C1. Medidor de nivel por tarjeta, de -60 a 0 dB.
- [ ] C2. Tema Profesional: LED de 24 segmentos (verde → amarillo → rojo) con marcas a la derecha.
- [ ] C3. Tema Moderna: barra continua de dos canales con divisora, marcas de escala (0, -6, -12, -18, -24, -30, -36, -48, -60) y línea de pico.
- [ ] C4. Caída suave del nivel visual y pico sostenido (decaimiento animado).
- [ ] C5. Saturación: todo rojo a ≥ 0 dB, sostenido 1 s.
- [ ] C6. Gris equivalente cuando la tarjeta está atenuada.
- [ ] C7. Con la fuente muteada, el medidor sigue mostrando el nivel de la señal (se reconstruye con nivel crudo × fader).
- [ ] C8. La ganancia de los filtros se suma al nivel mostrado (post fader + filtros), refrescada cada 1 s y al tocar un filtro.
- [ ] C9. Fuente oculta: medidor apagado.
- [ ] C10. Actualización a ~30 fps sin trabar la ventana.
- [-] C11. Modo de depuración del medidor (`DEBUG_VU_FUENTE`): es una constante de desarrollo, apagada por defecto y sin interfaz. Se pasa al registro de errores si hace falta.

## D. Menú contextual de una fuente (clic derecho)

- [ ] D1. Renombrar…
- [ ] D2. Marcar como principal ★ / Quitar de principales.
- [ ] D3. Ocultar fuente / Mostrar fuente.
- [ ] D4. Filtros… (sección F).
- [ ] D5. Propiedades… (sección G).
- [ ] D6. Color de etiqueta (9 colores + quitar).
- [ ] D7. Quitar de todas las escenas… (con confirmación, bloqueado para la fuente de efectos y las principales).
- [ ] D8. Eliminar fuente… (con confirmación; bloqueado para la fuente de efectos y las globales de OBS).

## E. Orden, ocultas, principales y escenas permitidas

- [ ] E1. Botón ☰ de orden con criterios combinables: Favoritos, Con colores, Activas, Escena actual, Alfabético; "↩ Orden manual" para volver.
- [ ] E2. El orden manual por arrastre se respeta dentro de cada grupo y se guarda.
- [ ] E3. Interruptor para mostrar u ocultar las fuentes ocultas.
- [ ] E4. Ocultar: mutea, apaga monitoreo, va al fondo casi negra con el ojo 👁‍🗨, dB escondidos y medidor apagado.
- [ ] E5. Una fuente oculta que se toca desde OBS vuelve a quedar muteada y sin monitoreo.
- [ ] E6. Mostrar: restaura el mute y el monitoreo anteriores (también tras reiniciar el programa).
- [ ] E7. Principales ★: se crean/activan solo en las escenas permitidas; si el input ya no existe en OBS se sacan con aviso.
- [ ] E8. Escenas permitidas ✅: lista de casilleros por colección de escenas; tildar arma todo en esa escena, destildar no borra nada.
- [ ] E9. Sin ninguna escena tildada, vale la del aire; en cuanto se tilda una, rige estricto.
- [ ] E10. 🧹 Quitar Efectos/Música de otras escenas (deja solo la del aire).
- [ ] E11. Migración automática del formato viejo de escenas permitidas.
- [ ] E12. Con una escena no permitida al aire, el efecto sale solo por parlantes y la música no se inyecta (sin error).
- [ ] E13. Menú del fondo del panel de fuentes: Agregar fuente, Actualizar fuentes, Quitar Efectos/Música de otras escenas…, Escenas permitidas…
- [ ] E14. Tarjetas grises para las fuentes que no están en la escena al aire; título del panel con la escena y la colección.
- [ ] E15. Vigilancia de la escena al aire cada 5 s (por si se pierde un evento).

## F. Filtros de audio

- [ ] F1. Ventana de filtros por fuente (una sola abierta por fuente).
- [ ] F2. Lista de filtros reales con: habilitar/deshabilitar, ✕ eliminar, botón Ajustes.
- [ ] F3. ➕ Agregar filtro: solo tipos de sonido, cruzados con los que ese OBS ofrece, con icono y nombre amigable.
- [ ] F4. Al crear un filtro se abre su editor de ajustes.
- [ ] F5. Editor por esquema para limitador, compresor, ecualizador de 3 bandas y ecualizador básico (rango, paso, sufijo, valor por defecto).
- [ ] F6. Esquema genérico para los demás tipos (rango adivinado por el nombre del campo).
- [ ] F7. Controles: slider para números, casilla para booleanos, lista desplegable, texto.
- [ ] F8. Cada cambio se aplica a OBS al instante (se oye en vivo).
- [ ] F9. Sondeo cada ~500 ms de cambios hechos en OBS, sin pisar el control que se está arrastrando ni "temblar" por redondeos.
- [ ] F10. Refresco en vivo de la lista por los eventos de filtros de OBS.
- [-] F11. Reordenar filtros: el README lo nombra pero el código actual no lo usa en ningún lado, así que hoy no existe. No hay nada que igualar (se puede sumar después como mejora).
- [ ] F12. La ventana se cierra sola si la fuente se borra.
- [ ] F13. Rueda del mouse en las listas con scroll.

## G. Propiedades de la fuente

- [ ] G1. Ventana de Propiedades según el tipo real de la fuente (Mic/Aux, Audio de escritorio, Captura de audio de aplicación, Fuente de medios, Captura de ventana, y editor genérico para el resto), campo por campo como la de OBS.
- [ ] G2. Listas dinámicas (dispositivo de audio, ventana a capturar) pedidas en vivo a OBS.
- [ ] G3. Campos condicionales que aparecen y desaparecen en su orden original.
- [ ] G4. Botones Por defecto, Cancelar (restaura lo que había al abrir) y Aceptar.
- [ ] G5. Cambios aplicados a OBS al instante y sondeo cada ~500 ms de lo que cambie en OBS.
- [ ] G6. Fuente de medios con el orden y las etiquetas de OBS (Buffer solo en modo red).
- [ ] G7. Se abre sola al crear una fuente nueva.
- [ ] G8. Scroll con barra flotante que se oculta.

## H. Agregar y borrar fuentes

- [ ] H1. Clic derecho en el fondo del panel → ➕ Agregar fuente con los 4 tipos de audio (cruzados con los de ese OBS), con icono SVG original.
- [ ] H2. ⋯ Otros tipos de fuente… con selector completo y casilla "Mostrar todos los tipos que informa OBS".
- [ ] H3. Pide el nombre (sugerido = nombre del tipo), lo numera si existe, crea la fuente en la escena al aire.
- [ ] H4. Mensajes claros si el OBS no trae el tipo pedido.
- [ ] H5. Botones "+ AGREGAR FUENTE" y "ACTUALIZAR FUENTES" en Ajustes → Conexión.
- [ ] H6. Eliminar fuente: borra de OBS tras confirmar, bloqueando las globales y la interna.
- [ ] H7. Quitar de todas las escenas: borra los ítems de escena sin borrar la fuente; informa en cuántas escenas estaba.

## I. Soundboard

- [ ] I1. Grilla de pads con placa de color, imagen o ▶ si está vacío, nombre, y color de etiqueta en el marco.
- [ ] I2. Clic: reproduce (en OBS y, si está activado, por los parlantes de la PC).
- [ ] I3. Clic sobre el pad que suena: lo detiene con fundido de 2 s, ignorando clics hasta que termina.
- [ ] I4. Doble clic y menú contextual: reproducir, detener, reiniciar.
- [ ] I5. Barra de progreso semitransparente que barre el pad al ritmo real del audio.
- [ ] I6. El pad se ilumina mientras suena y se apaga solo al terminar (también sin conexión, por reloj).
- [ ] I7. Asignar o cambiar sonido; asignar imagen; renombrar; color de etiqueta.
- [ ] I8. Vaciar pad (deja el botón vacío) y Eliminar pad (corre los siguientes y baja el contador).
- [ ] I9. 🧹 Vaciar pads vacíos (menú del pad): elimina de una vez todos los pads sin sonido, con confirmación; corta antes lo que esté sonando y corre los índices.
- [ ] I10. ＋ AGREGAR PAD al pie del panel.
- [ ] I11. 🔍 DETECTAR SONIDOS DE LA CARPETA: los audios nuevos de `assets/Sondidos_pad/` entran primeros con su imagen gemela de `assets/Imagenes_pad/`; también completa imágenes que falten.
- [ ] I12. La detección corre sola al abrir el programa.
- [ ] I13. Arrastrar un pad para reordenar (se intercambian) y se guarda.
- [ ] I14. Volumen propio de cada pad, en porcentaje: barra horizontal dentro del menú del pad; se oye en el acto si está sonando y se guarda al soltar.
- [ ] I15. Nivelación: todos los pads suenan igual (medido una vez por archivo, compensado en parlantes y en OBS con un filtro de ganancia propio), con interruptor.
- [ ] I16. La fuente de efectos queda siempre vacía en reposo (al terminar, parar o cerrar el programa).
- [ ] I17. Miniaturas con caché (contain, antialias) sin reabrir archivos al reconstruir.
- [ ] I18. Grilla responsive con el sobrante repartido entre columnas.
- [ ] I19. Tamaños Chico / Mediano / Grande.
- [ ] I20. Si no hay conexión, el pad igual suena por los parlantes.
- [ ] I21. Aviso claro cuando el archivo del pad no existe o OBS no lo encuentra.

## J. Música

- [ ] J1. Mini reproductor al pie de las fuentes: play/pausa, stop, reiniciar, anterior (con más de 3 s reinicia el tema), siguiente, modo (repetir / aleatorio / apagado).
- [ ] J2. Título, tiempos y barra de progreso clickeable con salto exacto.
- [ ] J3. Botón Biblioteca ▲/▼ que expande el panel (playlist a la izquierda, biblioteca a la derecha).
- [ ] J4. Pestañas por cada subcarpeta de `assets/Musica/`, buscador en toda la biblioteca, orden por columnas, duraciones detectadas en segundo plano con caché.
- [ ] J5. Armar la playlist por arrastre y por clic derecho (Agregar a la playlist, Reproducir ahora, Sacar de la playlist).
- [ ] J6. Clic en un tema lo reproduce; doble clic en una pestaña suena la carpeta sin tocar la playlist; ⇄ intercambia entre playlist y carpeta retomando cada una.
- [ ] J7. Resaltado del tema que suena.
- [ ] J8. Recientes automáticos; la playlist arranca vacía en cada inicio.
- [ ] J9. Volumen desde el fader de la tarjeta `Música`.
- [ ] J10. Si el tema se cambia desde OBS, el programa lo detecta y lo sigue.
- [ ] J11. Avance automático al terminar un tema.
- [ ] J12. Música en PC (parlantes): OBS manda; la consola copia play/pausa/stop/seek y corrige la deriva sola.
- [ ] J13. Sincronización al conectar con Música en PC (OBS vacío, OBS sonando, tema que no está en la biblioteca).
- [ ] J14. Barra de volumen propia del reproductor para el audio de la PC (bocina).
- [ ] J15. La música sigue sonando en OBS al desconectar la consola.

## K. Audio local en la PC

- [ ] K1. Interruptor "Escuchar acá" (efectos por los parlantes).
- [ ] K2. Interruptor "Nivelar efectos".
- [ ] K3. Interruptor "Música en PC".
- [ ] K4. Motor miniaudio con respaldo MCI en Windows; sin audio local los efectos igual salen al stream.
- [-] K5. Barra de volumen de salida del audio local en Ajustes → Audio: el código dice "Volumen de salida removido: el audio siempre suena a volumen completo" y la función que la dibujaba (`_tarjeta_volumen`) no se usa. No se construye. La única barra de volumen local que queda es la de la bocina del reproductor de música (J14) y la de cada pad (I14).

## L. Ajustes (ventana)

- [ ] L1. Ventana de Ajustes con 5 pestañas: Conexión, Apariencia, Audio, Sincronización, Actualización, cada una con su ayuda.
- [ ] L2. Se abre con el engranaje; se cierra con la X, Escape o el engranaje.
- [ ] L3. Apariencia: tamaño de ícono, alto de tarjeta, diseño (orientación), tipografía, tema.
- [ ] L4. El cambio de tipografía se aplica en el acto a toda la interfaz, sin reabrir.
- [ ] L5. Audio: los tres interruptores de la sección K.

## M. Apariencia y ventana

- [ ] M1. Dos temas: Profesional (oscuro, acento verde) y Moderna (gris azulado estilo OBS, acento azul).
- [ ] M2. Selector de tipografía: "Tipografia de obs" (Open Sans, por defecto), Predeterminada y las de `assets/fuentes/`.
- [ ] M3. Fuentes personalizadas registradas solo para este proceso (Windows, macOS y Linux).
- [ ] M4. Diseño de paneles: vertical u horizontal, con el orden de los paneles; intercambiar paneles arrastrando su título.
- [ ] M5. Divisor entre paneles con posición guardada por orientación.
- [ ] M6. Geometría de la ventana guardada y restaurada (tamaño mínimo respetado).
- [ ] M7. Cabecera con logo (o ecualizador dibujado si falta), título "CONSOLA OBS", subtítulo y estado.
- [ ] M8. Iconos SVG originales de OBS (mute, monitoreo, tipos de fuente, menús); respaldo con emoji si falta el motor.
- [ ] M9. Menús contextuales propios con icono, separadores y casilleros.
- [ ] M10. Sin parpadeo ni flash blanco al redimensionar; los pads y tarjetas solo se reubican, no se reconstruyen.
- [ ] M11. Soporte de DPI por monitor.
- [ ] M12. Aviso "build" con fecha en el título de la ventana.

## N. Sincronización de assets entre PCs

- [ ] N1. Pestaña Sincronización: carpeta local, IP de la otra PC, puerto 4456, clave.
- [ ] N2. 🔍 BUSCAR PCS en la red y 🔗 VINCULAR (la otra PC acepta una vez; la clave viaja sola).
- [ ] N3. 🔑 VER CLAVE y variable de entorno `CONSOLAOBS_SYNC_KEY`.
- [ ] N4. 🔄 SINCRONIZAR en ambas direcciones (nombre + tamaño + fecha + sha256), con registro de lo copiado y borrado.
- [ ] N5. Alcance limitado a `Sondidos_pad`, `Imagenes_pad` y `Musica`.
- [ ] N6. Los borrados siempre se confirman (Sí = todo, No = solo copiar lo nuevo).
- [ ] N7. Botón 🛡 FIREWALL del sync.
- [ ] N8. El servidor de sync arranca con el programa (y avisa si falta FastAPI).
- [ ] N9. Compatibilidad con `sync_server_mini.py` en la PC del OBS.
- [ ] N10. Al sincronizar se completa la Carpeta OBS.
- [ ] N11. Mensajes de error específicos (timeout, firewall, clave).

## O. Actualización automática

- [ ] O1. Chequeo de la última Release de GitHub al arrancar (con demora) y con 🔍 BUSCAR ACTUALIZACIONES.
- [ ] O2. Pregunta [Actualizar] / [Más tarde].
- [ ] O3. Descarga con barra de progreso.
- [ ] O4. `updater.exe` reemplaza archivos preservando `config/`, verifica la instalación y reabre el programa.
- [ ] O5. Si algo falla, la instalación actual no se toca.

## P. Arranque y cierre

- [ ] P1. Comprobación de dependencias al arrancar (Python, Tk/Qt, obsws-python) con mensaje claro; las opcionales solo avisan.
- [ ] P2. Instancia única con aviso "ya hay otra abierta" y opción de ejecutar igual.
- [ ] P3. Creación automática de carpetas y `LEEME.txt` de ejemplo en `assets/`.
- [ ] P4. Al cerrar: detener el efecto y vaciar la fuente, desconectar de OBS, guardar conexión, pads e interfaz (geometría y divisor), y asegurar que el proceso muere.
- [ ] P5. Funciona en Windows; Linux y macOS con los respaldos actuales.

## Q. Persistencia (formato de los archivos)

- [ ] Q1. Se siguen leyendo los `config/*.json` que ya existen (`config_interfaz`, `config_soundboard`, `config_musica`, `sync_config`, `ultimo_indice`).
- [ ] Q2. Las instalaciones que vienen de versiones anteriores no pierden nada (colores, orden, pads, principales, escenas permitidas, ocultas con su estado previo).
- [ ] Q3. `config_interfaz.json` y `config_soundboard.json` siguen versionados en git.

## R. Lo que se agregó en las Etapas 0 y 1 y no puede perderse

- [ ] R1. Registro de errores a archivo y captura de errores de la ventana.
- [ ] R2. Guardado atómico de todos los archivos de ajustes.
- [ ] R3. Rutas de los pads relativas.
- [ ] R4. Contraseña de OBS y clave de sync cifradas.
- [ ] R5. Pedidos a OBS en hilo propio; botones con respuesta instantánea.
- [ ] R6. Modelo de estado único del mezclador y avisos entre capas.
- [ ] R7. Resincronización cada 10 s por lote (mute, monitoreo y volumen) y reapertura del socket tras un timeout.
- [ ] R8. Avisos que no bloquean (en Qt, toasts).

---

### Cómo se usa esta lista

1. Antes de construir cada pantalla en Qt se leen sus ítems.
2. Al terminar una sección se marca `[Q]` y se prueba lado a lado con la versión Tkinter (`py main.py` vs `py main.py --qt`).
3. Solo cuando todos los ítems estén en `[x]` o `[-]` se borra `consola_obs/ui/`.
4. Si al probar se encuentra una función que no está en la lista, se agrega primero acá y después se implementa.
