"""Prueba rápida de audio local SIN abrir la consola ni OBS.

Sirve para responder "¿esta PC emite sonido?" cuando un efecto no se
escucha: si acá suena, el problema está en OBS/rutas; si acá tampoco,
es audio local (parlantes, drivers, miniaudio).

Uso:
    python probar_sonido.py --listar        muestra los audios disponibles
    python probar_sonido.py                 reproduce el primero
    python probar_sonido.py 3               reproduce el número 3
    python probar_sonido.py aww             reproduce el que contenga "aww"
    python probar_sonido.py "C:\\x\\y.mp3"  reproduce un archivo puntual

Los audios se buscan junto a este script (assets/Sondidos_pad), con
el mismo mecanismo que el programa: anda desde cualquier carpeta.
"""
import os
import sys
import time

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_SONIDOS = os.path.join(CARPETA_SCRIPT, "assets", "Sondidos_pad")
EXTENSIONES = (".mp3", ".wav", ".ogg", ".flac", ".m4a")


def _miniaudio():
    try:
        import miniaudio
        return miniaudio
    except Exception:
        print("ERROR: falta 'miniaudio' (audio local).")
        print("Instalalo con: pip install -r requirements.txt")
        return None


def archivos_disponibles():
    if not os.path.isdir(CARPETA_SONIDOS):
        return []
    return sorted(f for f in os.listdir(CARPETA_SONIDOS)
                  if f.lower().endswith(EXTENSIONES))


def listar():
    if not os.path.isdir(CARPETA_SONIDOS):
        print(f"No existe la carpeta: {CARPETA_SONIDOS}")
        return []
    archivos = archivos_disponibles()
    for i, nombre in enumerate(archivos, 1):
        ruta = os.path.join(CARPETA_SONIDOS, nombre)
        try:
            mb = os.path.getsize(ruta) / 1048576
        except Exception:
            mb = 0.0
        print(f"{i:3d}. {nombre}  ({mb:.1f} MB)")
    if not archivos:
        print("Carpeta vacía: poné .mp3 en assets/Sondidos_pad/")
    return archivos


def elegir(archivos, pedido):
    if pedido is None:
        return os.path.join(CARPETA_SONIDOS, archivos[0]) if archivos else None
    if os.path.isfile(pedido):
        return pedido
    if pedido.isdigit():
        i = int(pedido) - 1
        if 0 <= i < len(archivos):
            return os.path.join(CARPETA_SONIDOS, archivos[i])
        print(f"No hay sonido número {pedido} (hay {len(archivos)}).")
        return None
    bajos = [a for a in archivos if pedido.lower() in a.lower()]
    if len(bajos) == 1:
        return os.path.join(CARPETA_SONIDOS, bajos[0])
    if bajos:
        print(f"Varios coinciden con {pedido!r}:")
        for b in bajos:
            print(f"  - {b}")
        return None
    print(f"Nada coincide con {pedido!r}.")
    return None


def formatear(segundos):
    try:
        s = max(0, int(segundos))
        return f"{s // 60:02d}:{s % 60:02d}"
    except Exception:
        return "??:??"


def reproducir(ruta):
    miniaudio = _miniaudio()
    if miniaudio is None:
        return 1
    print(f"Abriendo: {ruta}")
    try:
        with open(ruta, "rb") as f:
            crudo = f.read()
    except Exception as e:
        print(f"No se pudo leer el archivo: {e}")
        return 1
    try:
        decodificado = miniaudio.decode(crudo)
    except Exception as e:
        print(f"El archivo no se pudo decodificar ({e}).")
        print("Probá con otro formato (wav o mp3 común).")
        return 1
    try:
        total = (len(decodificado.samples) / max(1, decodificado.nchannels or 1)
                 / max(1, decodificado.sample_rate or 1))
    except Exception:
        total = 0.0
    print(f"Suena {formatear(total)} por los parlantes... (Ctrl+C para cortar)")
    try:
        flujo = miniaudio.stream_file(ruta)
    except Exception as e:
        print(f"No se pudo abrir el audio ({e}).")
        return 1
    try:
        dispositivo = miniaudio.PlaybackDevice()
    except Exception as e:
        print(f"No hay salida de audio disponible: {e}")
        print("En Linux hace falta servidor de sonido (PulseAudio/PipeWire).")
        return 1
    inicio = time.time()
    try:
        dispositivo.start(flujo)
        while True:
            durmio = 0.0
            while durmio < 0.25:
                time.sleep(0.05)
                durmio += 0.05
            pasado = time.time() - inicio
            print(f"\r  {formatear(pasado)} / {formatear(total)}", end="", flush=True)
            if total > 0 and pasado >= total + 0.5:
                break
    except KeyboardInterrupt:
        print()
    finally:
        try:
            dispositivo.close()
        except Exception:
            pass
    print("\nListo. Si sonó, el audio local anda: el problema está en otro lado.")
    return 0


def main(argv):
    if "--listar" in argv or "-l" in argv:
        listar()
        return 0
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    pedido = argv[1] if len(argv) > 1 else None
    if pedido is not None and os.path.isfile(pedido):
        return reproducir(pedido)
    archivos = archivos_disponibles()
    if not archivos:
        print(f"No hay audios en: {CARPETA_SONIDOS}")
        return 1
    if pedido is None:
        listar()
        return reproducir(os.path.join(CARPETA_SONIDOS, archivos[0]))
    ruta = elegir(archivos, pedido)
    return reproducir(ruta) if ruta else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
