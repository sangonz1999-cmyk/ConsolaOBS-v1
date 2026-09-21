"""Nivelación de efectos (por sonoridad, con referencia).

Problema: cada pad suena a un volumen distinto porque los mp3 vienen
masterizados distinto. Unos (aura, roca) vienen "planchados" bien
fuertes y otros (aplausos) con mucho pico pero poca energía: igualar
solo por PICO los deja igual de desparejos al oído (medido: aura
tiene +19 dB de RMS sobre aplausos con el mismo pico).

Solución: se mide el RMS (energía ~ lo que se percibe) y se iguala
todo al RMS de `aplausos.mp3`, que es el nivel "normal" de
referencia. Además la ganancia se recorta para que el pico final
nunca pase de -1 dB (anti-clip).

Se aplica en los DOS caminos del sonido:
- Parlantes de la PC: se multiplican las muestras (ver
  _aplicar_ganancia en reproduccion.py).
- OBS: filtro Gain propio ("Nivelador ConsolaOBS") en la fuente de
  efectos, con los dB del pad que suena (sin tocar el fader del
  usuario).
"""
import math
import os

# Referencia de nivel "normal": el RMS de este archivo manda.
NOMBRE_REFERENCIA = "aplausos.mp3"
# Si la referencia no existe o no se puede leer, este valor.
RMS_REFERENCIA_FALLBACK_DB = -27.0
# El pico final nunca pasa de acá, gane lo que gane por RMS.
PICO_TECHO_DB = -1.0
# Techo de compensación por seguridad (silencios, rarezas).
GANANCIA_MIN_DB = -24.0
GANANCIA_MAX_DB = 24.0
# Versión del cálculo: si cambia el algoritmo, los pads guardados se
# vuelven a medir solos (ver nivel_version en reproduccion.py).
NIVEL_VERSION = 2


def medir_nivel(ruta):
    """Devuelve (pico, rms) lineales (1.0 = 0 dBFS) o (None, None).
    Lee a bytes con Python y decodifica en memoria porque miniaudio
    no abre en Windows rutas con caracteres raros."""
    try:
        with open(ruta, "rb") as f:
            crudo = f.read()
    except Exception:
        return (None, None)
    if not crudo:
        return (None, None)
    try:
        import miniaudio
        decodificado = miniaudio.decode(crudo)
        muestras = decodificado.samples
        # El typecode se lee del ARRAY (DecodedSoundFile no lo expone).
        tipo = getattr(muestras, "typecode", None)
        escala = {"b": 128.0, "h": 32768.0, "i": float(2 ** 31),
                  "l": float(2 ** 31), "q": float(2 ** 63)}.get(tipo, 1.0)
    except Exception:
        return (None, None)
    try:
        pico = 0.0
        energia = 0.0
        n = 0
        for m in muestras:
            v = abs(float(m)) / escala
            if v > pico:
                pico = v
            energia += (float(m) / escala) ** 2
            n += 1
        if n == 0:
            return (None, None)
        return (pico, math.sqrt(energia / n))
    except Exception:
        return (None, None)


def medir_pico(ruta):
    """Solo el pico (compat: lo usa el fundido/local para chequear)."""
    pico, _rms = medir_nivel(ruta)
    return pico


_ref_cache = {"ruta": None, "db": None}


def _rms_referencia_db():
    """RMS de referencia en dB: el de aplausos.mp3 si existe, si no el
    fallback. Se cachea por ruta."""
    try:
        from consola_obs import rutas as R
        ruta = os.path.join(R.CARPETA_SONIDOS_PAD, NOMBRE_REFERENCIA)
    except Exception:
        return RMS_REFERENCIA_FALLBACK_DB
    if _ref_cache["ruta"] == ruta and _ref_cache["db"] is not None:
        return _ref_cache["db"]
    try:
        _pico, rms = medir_nivel(ruta)
        db = 20.0 * math.log10(rms) if rms and rms > 0 else None
    except Exception:
        db = None
    if db is None:
        db = RMS_REFERENCIA_FALLBACK_DB
    _ref_cache["ruta"] = ruta
    _ref_cache["db"] = db
    return db


def limitar_por_techo(pico_db, ganancia_db, techo_db=PICO_TECHO_DB):
    """Recorta la ganancia para que pico+ganancia no pase el techo."""
    try:
        return min(float(ganancia_db), float(techo_db) - float(pico_db))
    except Exception:
        return ganancia_db


def ganancia_db_para(ruta, techo_db=PICO_TECHO_DB):
    """dB a aplicar para que suene como la referencia (0.0 si no se
    pudo medir o el archivo es silencio). Siempre acotada y con
    techo anti-clip."""
    try:
        pico, rms = medir_nivel(ruta)
    except Exception:
        return 0.0
    if pico is None or rms is None or rms <= 0.0 or pico <= 0.0:
        return 0.0
    try:
        ref_db = _rms_referencia_db()
        rms_db = 20.0 * math.log10(rms)
        pico_db = 20.0 * math.log10(pico)
        db = limitar_por_techo(pico_db, ref_db - rms_db, techo_db)
    except Exception:
        return 0.0
    return max(GANANCIA_MIN_DB, min(GANANCIA_MAX_DB, db))


def lineal_desde_db(db):
    """dB -> multiplicador lineal para las muestras locales."""
    try:
        return 10.0 ** (float(db) / 20.0)
    except Exception:
        return 1.0
