"""Política de reconexión automática (sin Tkinter ni OBS: se prueba sola).

Tiempos de espera crecientes entre intentos: reintentar muy seguido
satura la red y el log; esperar mucho deja al usuario sin consola. Se
arranca rápido (2 s) porque el corte típico es un hipo de la red o un
reinicio de OBS, y se estabiliza en 30 s.
"""
ESPERAS_S = (2, 4, 8, 15, 30)


def espera_para_intento(numero_intento):
    """Segundos a esperar antes del intento N (el primero es 1)."""
    if numero_intento < 1:
        numero_intento = 1
    indice = min(numero_intento - 1, len(ESPERAS_S) - 1)
    return ESPERAS_S[indice]
