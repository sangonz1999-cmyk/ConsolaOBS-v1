"""Qué motor de audio local hay disponible (para el aviso en Ajustes y
para el log). Nunca lanza."""
from consola_obs.audio import motor_mci as mod_motor_mci

_cache = {}


def motor():
    """'miniaudio', 'mci' o 'ninguno'."""
    if "motor" in _cache:
        return _cache["motor"]
    detalle = ""
    try:
        import miniaudio  # noqa: F401
        resultado = "miniaudio"
    except Exception as e:
        detalle = str(e)
        resultado = "mci" if mod_motor_mci.disponible() else "ninguno"
    _cache["motor"] = resultado
    _cache["detalle"] = detalle
    try:
        from consola_obs import red as mod_red
        extra = f" (miniaudio: {detalle})" if detalle else ""
        mod_red.log_conexion("AUDIO", f"motor de audio local = {resultado}{extra}")
    except Exception:
        pass
    return resultado


def texto_estado():
    m = motor()
    if m == "miniaudio":
        return "Motor de audio local: miniaudio (OK).", False
    if m == "mci":
        return ("Motor de audio local: reproductor de Windows (miniaudio no está "
                "instalado; funciona igual)."), False
    return ("SIN audio local: falta instalar miniaudio (pip install miniaudio) "
            "y este sistema no tiene reproductor alternativo."), True
