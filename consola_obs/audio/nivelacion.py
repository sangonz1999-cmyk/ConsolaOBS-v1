"""Nivelación de efectos (ReplayGain simple por pico).

Problema: cada pad suena a un volumen distinto porque los mp3 vienen
masterizados distinto. Solución: se mide el pico de cada archivo una
sola vez (se guarda por pad) y al reproducir se compensa con la
ganancia justa para que todos piquen al mismo objetivo.

Se aplica en los DOS caminos del sonido:
- Parlantes de la PC: se multiplican las muestras (ver
  _aplicar_ganancia en reproduccion.py).
- OBS: filtro Gain propio ("Nivelador ConsolaOBS") en la fuente de
  efectos, con los dB del pad que suena (sin tocar el fader del
  usuario).

Es por PICO, no por sonoridad (LUFS): para efectos cortos de
soundboard iguala bien y es barato de calcular. Si un día hiciera
falta más precisión se cambia medir_pico por RMS/LUFS sin tocar el
resto (la interfaz ganancia_db_para no cambia).
"""
import math

# A qué pico apuntan todos los efectos (dBFS). -1.5 deja un poco de
# aire antes del clip.
PICO_OBJETIVO_DB = -1.5
# Techo de compensación: si un archivo necesitaría más, algo raro hay
# (o es silencio) y mejor no amplificar ruido hasta el infinito.
GANANCIA_MIN_DB = -24.0
GANANCIA_MAX_DB = 24.0


def medir_pico(ruta):
    """Pico lineal del archivo (1.0 = 0 dBFS) o None si no se pudo.
    Lee a bytes con Python y decodifica en memoria porque miniaudio
    no abre en Windows rutas con caracteres raros (igual que en
    leer_duracion_local de musica.py)."""
    try:
        with open(ruta, "rb") as f:
            crudo = f.read()
    except Exception:
        return None
    if not crudo:
        return None
    try:
        import miniaudio
        decodificado = miniaudio.decode(crudo)
        muestras = decodificado.samples
        # El typecode se lee del ARRAY (DecodedSoundFile no lo expone).
        tipo = getattr(muestras, "typecode", None)
        escala = {"b": 128.0, "h": 32768.0, "i": float(2 ** 31),
                  "l": float(2 ** 31), "q": float(2 ** 63)}.get(tipo, 1.0)
    except Exception:
        return None
    try:
        pico = 0.0
        for m in muestras:
            v = abs(float(m)) / escala
            if v > pico:
                pico = v
        return pico
    except Exception:
        return None


def ganancia_db_para(ruta, objetivo_db=PICO_OBJETIVO_DB):
    """dB a aplicar para que el pico quede en objetivo_db (0.0 si no
    se pudo medir o el archivo es silencio). Siempre acotada."""
    try:
        pico = medir_pico(ruta)
    except Exception:
        return 0.0
    if pico is None or pico <= 0.0:
        return 0.0
    try:
        objetivo_lin = 10.0 ** (float(objetivo_db) / 20.0)
        db = 20.0 * math.log10(objetivo_lin / pico)
    except Exception:
        return 0.0
    return max(GANANCIA_MIN_DB, min(GANANCIA_MAX_DB, db))


def lineal_desde_db(db):
    """dB -> multiplicador lineal para las muestras locales."""
    try:
        return 10.0 ** (float(db) / 20.0)
    except Exception:
        return 1.0
