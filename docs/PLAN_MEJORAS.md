# Plan de mejora de ConsolaOBS

## Contexto

ConsolaOBS funciona, pero se siente básico por tres motivos que encontré al leer el código (unas 26.800 líneas de Python):

- **La interfaz está en Tkinter**, dibujada a mano sobre Canvas. Para disimular sus límites el código usa trucos (tapar la ventana con una captura al redimensionar, pausar los medidores, reconstruir todas las tarjetas al cambiar un ajuste). Hay unos 470 colores escritos a mano en 116 tonos distintos, emojis como iconos, textos de 6 a 8 pt y unas 45 ventanas modales nativas.
- **La interfaz habla directo con OBS.** Mover un fader, mutear o conectar hace el pedido de red en el hilo de la ventana, así que cualquier demora de OBS congela el programa hasta 5 s. De ahí venían también los dos errores que ya corregimos.
- **No hay red de seguridad.** No hay tests, no hay registro de errores (los `print` se pierden en el `.exe`), casi 600 errores se tragan con `except: pass`, y los ajustes se guardan de forma que un corte los puede corromper.

Decisiones tuyas que este plan asume: **migrar la interfaz a Qt (PySide6)** y sumar (sin atajos globales ni presets: se descartaron). Cambio de escenas, control de transmisión y control desde el celular quedan fuera, pero la arquitectura nueva los deja fáciles de agregar después.

Resultado buscado: un programa que se vea y se sienta como una app profesional de audio, que nunca se congele ni se desincronice de OBS, y que se pueda seguir mejorando sin miedo a romperlo.

## Requisito de paridad (obligatorio)

El programa nuevo debe cumplir **todas** las funciones y micro funciones del programa actual; nada se pierde en la migración.

- La fuente de verdad es el `README.md` del repo (845 líneas), completado con lo que haga el código y el README no mencione.
- Antes de empezar la Etapa 2 se arma `docs/PARIDAD.md`: una lista de control con cada función y micro función (mezclador, filtros, propiedades, escenas permitidas, efectos, nivelación, música, audio en la PC, sincronización, actualizador, ajustes, menús contextuales, arrastres, comportamientos al conectar y al cerrar).
- Cada ítem lleva estado: pendiente, hecho en Qt, verificado contra la versión Tkinter.
- La interfaz Tkinter (`consola_obs/ui/`) no se borra hasta que todos los ítems estén verificados.
- Las mejoras de las etapas 2 y 3 se suman a lo existente; si una mejora cambia un comportamiento actual, se consulta antes.

## Enfoque general

Se hace en 4 etapas (la 3 se descartó). Cada una termina con el programa funcionando y se puede publicar por separado. La versión Tkinter sigue siendo la que se usa hasta que la versión Qt la iguale; recién ahí se borra (al final de la Etapa 2).

La idea central: separar un **núcleo sin interfaz** (OBS, audio, configuración, sync) de la **capa visual**. El núcleo se arma primero y lo usan las dos interfaces durante la transición.

```
consola_obs/
  nucleo/     estado del mezclador, servicio OBS, config, presets, atajos   (sin Tk ni Qt)
  audio/      se mantiene, sin importar nada de ui/
  sync/ update/   se mantienen
  ui/         interfaz Tkinter actual (se elimina al final de la etapa 2)
  qt/         interfaz nueva en PySide6
```

---

## Etapa 0 — Poner la casa en orden

Trabajos chicos que hacen falta antes de tocar nada grande.

1. **Repositorio.** La carpeta del Drive no es un repositorio git, por eso los cambios se pierden entre versiones. Trabajar en un clon real del repo y dejar el Drive solo para el `.exe` publicado. Unir la rama `fix/sincronizacion-y-vigilancia-obs` a `main`.
2. **Registro de errores.** Reemplazar los 127 `print` y el `log_conexion` de `red.py` por `logging` con archivo rotativo en `config/`. Agregar `sys.excepthook` y captura de errores de la ventana, para que un fallo deje rastro.
3. **Guardado seguro de ajustes.** Generalizar la escritura atómica que hoy solo tiene `config_musica.json` (`configuracion.py:123`) a todos los archivos de config.
4. **Bug de orden borrado.** `desconectar_obs` vacía `E.orden_fuentes` y al cerrar se guarda vacío (`obs/cliente.py`, `ui/ventana.py:1483`). Tu `config_interfaz.json` ya tiene el orden y los colores vacíos por esto.
5. **Rutas absolutas en la config.** Los 32 pads apuntan a `D:\Documentos\ConsolaOBS-v1\...`. Guardar rutas relativas a `assets/`.
6. **Versión en un solo lugar.** Hoy está en 4 archivos a mano; dejar `update/version.py` como fuente y generar los demás en `compilar.bat`.
7. **Contraseña de OBS y clave de sync** fuera del texto plano: cifrarlas con DPAPI de Windows.
8. **Regla de firewall.** Dejar de crearla en cada conexión en la PC de la consola (`obs/cliente.py`, paso FIREWALL): no sirve para llegar a un OBS remoto. Queda solo el botón manual.

## Etapa 1 — Núcleo sin interfaz

Lo que arregla la fluidez y la sincronía de raíz, antes de cambiar una sola pantalla.

1. **Servicio OBS con hilo propio** (`nucleo/servicio_obs.py`). Un único hilo trabajador con una cola de pedidos; la interfaz nunca más llama a OBS directamente. Reemplaza al envoltorio `_ClienteOBSSincronizado` y a los 44 lugares que crean hilos sueltos. Incluye:
   - conexión en segundo plano (hoy `conectar_obs()` entero corre en el hilo de la ventana);
   - **reconexión automática** con reintentos crecientes; el cartel de "se perdió la conexión" pasa a ser un aviso no bloqueante con el estado "reconectando…";
   - conexión automática al abrir el programa si hay datos guardados;
   - faders con límite de envío (un pedido cada ~30 ms, siempre el último valor) en vez de uno por cada movimiento del mouse.
2. **Modelo de estado** (`nucleo/modelo.py`). Clases `Fuente`, `Pad`, `SesionMusica` que avisan cuando cambian. Reemplaza de a poco los 213 atributos sueltos de `estado.py`. Los eventos de OBS actualizan el modelo y la interfaz solo lo refleja; así el programa y OBS no pueden mostrar cosas distintas.
3. **Resincronización completa.** Hoy cubre mute y monitoreo (`resincronizar_estado_audio` en `obs/eventos.py`); sumar volumen y hacerla al reconectar.
4. **Menos sondeos.** Agrupar con pedidos por lote de obs-websocket el refresco de ganancia (cada 1 s, varios pedidos por fuente), el de escena (5 s) y el de estado de pads (150 ms), y evitar que se acumulen hilos si OBS tarda.
5. **Romper los ciclos de importación** (`obs/cliente` → `obs/eventos` → `ui/tarjeta_fuente` → `obs/cliente`): el núcleo emite avisos y no importa nada de `ui/`.
6. **Tests del núcleo** con `pytest` y un OBS simulado: orden de respuestas, reconexión, resincronización, guardado de config, presets.

## Etapa 2 — Interfaz nueva en Qt

1. **Sistema de diseño** (`qt/tema/`):
   - una paleta de tokens (fondo, superficie, borde, texto, acento, peligro) con tema oscuro y claro; se termina el color escrito a mano;
   - escala tipográfica de 4 tamaños, mínimo 11 pt, con Inter (ya está en `assets/fuentes`);
   - juego de iconos SVG propio y consistente en vez de emojis (`assets/iconos` ya tiene una parte);
   - color de acento elegible por el usuario.
2. **Ventana principal:**
   - barra superior compacta con estado de conexión, escena actual, selector de preset y acceso a ajustes;
   - paneles acoplables de Qt (mezclador, efectos, música) que se reordenan, se separan a otro monitor y recuerdan su lugar; reemplaza las 4 disposiciones fijas y los trucos de redimensionado;
   - barra de estado inferior con conexión, latencia y última sincronización.
3. **Mezclador:** tira por fuente con fader, medidor estéreo real dibujado con QPainter (hoy los dos canales muestran el mismo valor), mute, auricular, filtros y etiqueta de color. Estados visibles de "pendiente" y "falló" en cada botón. Arrastrar para reordenar con animación.
4. **Efectos:** grilla de pads con imagen, progreso animado, atajo visible en el pad y búsqueda. Edición del pad en un panel lateral en vez de diálogos `askstring`.
5. **Música:** reproductor con carátula, cola visible, biblioteca con búsqueda, y varias listas guardadas (hoy hay una sola y se vacía al abrir).
6. **Avisos:** notificaciones tipo toast para lo rutinario ("Sin conexión", errores de refresco) y diálogos propios solo para confirmar acciones destructivas.
7. **Ajustes:** ventana con secciones, búsqueda y vista previa en vivo del tema.
8. **Primer uso:** asistente corto de conexión a OBS (host, puerto, contraseña, prueba) y ayuda emergente en cada botón.
9. **Accesibilidad:** navegación por teclado, contraste AA, modo compacto y "siempre visible".

Orden de construcción: tema y ventana → mezclador → efectos → música → ajustes. Se arranca con `main.py --qt` hasta tener paridad.

## Etapa 3 — DESCARTADA

Se quitó del plan por decisión del usuario: el programa siempre va a estar en primer plano, así que los atajos de teclado globales no hacen falta, y con ellos se descartan los presets, los pads simultáneos, el fundido cruzado, la bajada automática de música y el deshacer. Si más adelante se quiere alguna, se vuelve a evaluar por separado.

La eliminación de la interfaz Tkinter (`consola_obs/ui/`) que estaba al final de esa etapa pasa al final de la Etapa 2, cuando todos los ítems de `docs/PARIDAD.md` estén verificados.

## Etapa 4 — Lo que no se ve pero importa

1. **Actualizador** (`updater.py`):
   - verificar el hash SHA-256 de la descarga; hoy no se comprueba nada;
   - separar los assets (cerca de 1 GB) del programa, para que una actualización baje unos MB;
   - no continuar si la app no se cerró (hoy sigue igual tras 90 s);
   - rollback automático real en lugar del `ConsolaOBS_anterior.exe` copiado a mano.
2. **Sincronización LAN** (`sync/`):
   - `sync_server_mini.py` acepta cualquier emparejamiento sin preguntar durante 120 s: pedir confirmación siempre;
   - caché de hashes (hoy recalcula ~750 MB en cada consulta) y transferencia por bloques en vez de cargar el archivo entero en memoria;
   - corregir la regla de conflicto: el código hace "gana lo local" y la documentación dice "gana lo más nuevo".
3. **Compilación:** pasar de `--onefile` a carpeta con instalador (arranca mucho más rápido), firmar el `.exe` si conseguís un certificado, y compilar en GitHub Actions al crear una versión.
4. **Repositorio:** sacar `impact.ttf` y `TIMESBD.TTF` (son fuentes de Microsoft, no se pueden redistribuir), agregar LICENSE y CHANGELOG, actualizar el README, corregir la carpeta `Sondidos_pad`.
5. **Memoria:** poner límite a las cachés de imágenes que hoy solo crecen.

---

## Archivos clave

| Qué | Dónde |
|---|---|
| Conexión, vigilancia, envoltorio de pedidos | `consola_obs/obs/cliente.py` |
| Eventos de OBS y resincronización | `consola_obs/obs/eventos.py` |
| Estado global a reemplazar | `consola_obs/estado.py` |
| Guardado de ajustes | `consola_obs/configuracion.py` |
| Lógica de pads y música a conservar | `consola_obs/audio/reproduccion.py`, `audio/musica.py` |
| Interfaz actual (referencia de comportamiento) | `consola_obs/ui/tarjeta_fuente.py`, `ui/soundboard.py`, `ui/musica.py`, `app.py` |
| Actualizador y empaquetado | `updater.py`, `armar_release.py`, `compilar.bat` |

Se reutiliza sin reescribir: motor de audio local (`audio/motor_local.py`), nivelación (`audio/nivelacion.py`), plantillas de filtros (`estado.py:257-490`), lógica de escenas permitidas, sync y verificador de versiones.

## Riesgos

- **PySide6 con Python 3.14:** tu PC tiene Python 3.14.7. Hay que confirmar que existe versión compatible de PySide6 antes de empezar la etapa 2; si no, se compila con Python 3.12.
- **Tamaño del `.exe`:** Qt suma unos 40–60 MB. Se compensa quitando `pymupdf` (Qt ya dibuja SVG).
- **Alcance:** la etapa 2 es la más larga, porque rehace unas 11.000 líneas de interfaz. Por eso va por pantallas y con la versión vieja disponible.
- **Pads simultáneos:** exige crear varias fuentes en OBS; hay que cuidar que no ensucie las escenas del usuario.

## Verificación

- **Etapa 0:** cerrar el programa desconectado y comprobar que el orden de fuentes se conserva; forzar un error y verlo en el archivo de registro.
- **Etapa 1:** `pytest` con OBS simulado. Con OBS real: mover faders rápido sin que la ventana se trabe, cerrar OBS y ver "reconectando…", abrirlo y ver que todo vuelve solo, mutear desde OBS y desde la consola alternando 50 veces sin diferencias.
- **Etapa 2:** lista de paridad pantalla por pantalla contra la versión Tkinter; redimensionar y mover entre monitores con distinto escalado; medidores a 60 fps con 20 fuentes.
- **Etapa 4:** actualizar desde la versión anterior con una descarga corrupta (debe rechazarla) y con una buena; intentar emparejar sync sin confirmación.
