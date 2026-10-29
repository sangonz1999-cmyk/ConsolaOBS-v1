"""Volumen general de salida (Ajustes > Audio).

Dos barras, una por destino:

- OBS (stream): mueve a la vez los faders de OBS de las dos fuentes
  internas (Efectos y Música), conservando la diferencia entre ellas.
  La barra muestra el fader más alto. OBS avisa cada cambio y las
  tarjetas de las fuentes se actualizan solas con ese eco.
- Parlantes (PC): volumen general de lo que suena en esta PC (efectos
  con 'Escuchar acá' y música con 'Música en PC'). No toca nada de lo
  que sale por OBS. Se guarda en la configuración de interfaz.

Los imports de reproduccion/musica son perezosos: esos módulos importan
a éste para aplicar el volumen de la PC.
"""

from consola_obs import estado as E
from consola_obs import constantes as C
from consola_obs import configuracion as mod_configuracion


def _fuentes_obs():
    return (C.NOMBRE_FUENTE_EFECTOS, C.NOMBRE_FUENTE_MUSICA)


def _acotar(db):
    try:
        return max(-60.0, min(0.0, round(float(db) * 10) / 10))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------
# Parlantes (PC)
# ---------------------------------------------------------------------

def volumen_pc_db():
    """Volumen general de los parlantes en dB (0 a -60)."""
    try:
        return _acotar(getattr(E, "volumen_pc_db", 0.0))
    except Exception:
        return 0.0


def factor_pc():
    """Multiplicador lineal del audio local. Siempre 1.0 (volumen completo)."""
    return 1.0


def establecer_volumen_pc(db, guardar=False):
    """No-op: el volumen de los parlantes siempre está al máximo."""
    pass


def guardar_volumen_pc():
    try:
        db = volumen_pc_db()
        # Silencio total no se persiste: al reabrir vuelve a 0 dB.
        mod_configuracion.guardar_config_interfaz(
            {"volumen_pc_db": 0.0 if db <= E.UMBRAL_SILENCIO else db})
    except Exception:
        pass


# ---------------------------------------------------------------------
# OBS (stream)
# ---------------------------------------------------------------------

# Estado del gesto de arrastre actual.
#   offsets: {fuente: dB respecto del fader más alto} al EMPEZAR el gesto.
#            Se congelan durante todo el arrastre: así el resultado sólo
#            depende de la posición de la barra y no de los ecos (viejos
#            o fuera de orden) que OBS va devolviendo.
#   pend:    último valor de la barra que todavía no se mandó a OBS.
_arrastre = {"offsets": None, "t": 0.0, "pend": None, "job": None, "envio_t": 0.0}
# Últimos offsets "audibles": si la barra llevó todo a silencio, al volver
# a subirla se recupera cada fuente a donde estaba (antes se perdía).
_memoria = {"offsets": {}}
# Mínimo entre dos envíos a OBS mientras se arrastra (segundos).
_INTERVALO_ENVIO_S = 0.03
# Si pasa este tiempo sin movimiento ni soltar, el gesto se da por terminado.
_VIDA_GESTO_S = 1.5


def _faders_actuales():
    """{fuente: dB} de las fuentes internas que tienen tarjeta."""
    faders = {}
    for nombre in _fuentes_obs():
        try:
            widgets = (E.fuentes or {}).get(nombre)
            if widgets:
                faders[nombre] = float(widgets["fader"].get())
        except Exception:
            pass
    return faders


def hay_fuentes_obs():
    return bool(E.conectado and _faders_actuales())


def volumen_obs_db():
    """Lo que muestra la barra: el fader más alto de las dos fuentes
    (0 si todavía no hay tarjetas)."""
    faders = _faders_actuales()
    if not faders:
        return 0.0
    return _acotar(max(faders.values()))


def arrastrando_obs():
    import time
    if _arrastre["offsets"] is None:
        return False
    if time.monotonic() - _arrastre.get("t", 0.0) > _VIDA_GESTO_S:
        _arrastre["offsets"] = None
        return False
    return True


def _tomar_offsets():
    """La barra manda ABSOLUTO: Efectos y Música quedan en el mismo
    nivel que marca la barra (100 % = 0 dB en los dos). Así volver a 100
    siempre devuelve el máximo, sin importar por dónde se pasó."""
    base = _faders_actuales()
    if not base:
        return None
    return {n: 0.0 for n in base}


def _aplicar_obs(db_barra):
    """Manda a OBS (y a las tarjetas) los faders que corresponden a la
    posición de la barra. Cada fuente = barra + su offset del gesto."""
    import time
    if not E.conectado or E.cliente_obs is None:
        return
    if _arrastre["offsets"] is None or arrastrando_obs() is False:
        _arrastre["offsets"] = _tomar_offsets()
    offsets = _arrastre["offsets"]
    if not offsets:
        return
    _arrastre["t"] = time.monotonic()
    try:
        from consola_obs.obs import eventos as mod_obs_eventos
    except Exception:
        mod_obs_eventos = None
    for nombre, offset in offsets.items():
        nuevo = _acotar(float(db_barra) + offset)
        silencio = nuevo <= E.UMBRAL_SILENCIO
        try:
            E.cliente_obs.set_input_volume(nombre, vol_db=-100.0 if silencio else nuevo)
        except Exception as e:
            print(f"No se pudo mover el volumen de {nombre}: {e}")
            continue
        # La tarjeta, el nivel base de los fundidos y el audio local se
        # actualizan YA, sin esperar el eco de OBS (que puede llegar tarde
        # o desordenado). Así el volumen queda "recordado" en la app.
        if mod_obs_eventos is not None:
            try:
                mod_obs_eventos._sincronizar_volumen_remoto(
                    nombre, E.UMBRAL_SILENCIO if silencio else nuevo)
            except Exception:
                pass


def _enviar_pendiente():
    import time
    _arrastre["job"] = None
    db = _arrastre["pend"]
    _arrastre["pend"] = None
    if db is None:
        return
    _arrastre["envio_t"] = time.monotonic()
    _aplicar_obs(db)


def mover_obs(db_barra):
    """La barra pasó a db_barra. Los envíos a OBS se agrupan (como mucho
    uno cada ~30 ms, siempre con el último valor) para no saturar la
    conexión ni la interfaz mientras se arrastra."""
    import time
    if not E.conectado or E.cliente_obs is None:
        return
    _arrastre["pend"] = float(db_barra)
    if _arrastre["offsets"] is None:
        _arrastre["t"] = time.monotonic()
    if _arrastre["job"] is not None:
        return
    espera = max(0.0, _INTERVALO_ENVIO_S - (time.monotonic() - _arrastre["envio_t"]))
    try:
        _arrastre["job"] = E.ventana.after(int(espera * 1000), _enviar_pendiente)
    except Exception:
        _enviar_pendiente()


def terminar_arrastre_obs():
    """Se soltó la barra: se manda el último valor pendiente y el gesto
    queda cerrado (el próximo arrastre toma una foto nueva)."""
    job = _arrastre.get("job")
    if job is not None:
        try:
            E.ventana.after_cancel(job)
        except Exception:
            pass
        _arrastre["job"] = None
    if _arrastre["pend"] is not None:
        _enviar_pendiente()
    _arrastre["offsets"] = None
