"""Pruebas del núcleo de pedidos a OBS (sin OBS real ni ventana).

Correr con:  py -m pytest tests
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consola_obs.nucleo import hilo_ui  # noqa: E402
from consola_obs.nucleo import reconexion  # noqa: E402
from consola_obs.nucleo.servicio_obs import ServicioPedidos, sondeo_si_libre  # noqa: E402


def _esperar(condicion, limite=3.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        hilo_ui.ejecutar_pendientes()
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_pedidos_en_orden_y_resultado_en_la_ventana():
    servicio = ServicioPedidos("prueba-orden")
    hechos, resultados = [], []
    for n in range(5):
        servicio.encolar(lambda n=n: hechos.append(n) or n * 10,
                         al_terminar=resultados.append)
    assert _esperar(lambda: len(resultados) == 5)
    assert hechos == [0, 1, 2, 3, 4]
    assert resultados == [0, 10, 20, 30, 40]
    servicio.detener()


def test_misma_clave_solo_manda_el_ultimo_valor():
    """El caso del fader: mientras OBS está ocupado, los valores
    intermedios se descartan y sólo viaja el último."""
    servicio = ServicioPedidos("prueba-fader")
    liberar = threading.Event()
    enviados = []
    servicio.encolar(lambda: liberar.wait(2))          # OBS "ocupado"
    for db in range(-30, 1):
        servicio.encolar(lambda db=db: enviados.append(db), clave=("volumen", "Mic"))
    liberar.set()
    assert _esperar(lambda: servicio.pendientes() == 0 and enviados)
    time.sleep(0.05)
    assert enviados == [0]
    servicio.detener()


def test_error_llega_a_al_fallar_y_el_hilo_sigue_vivo():
    servicio = ServicioPedidos("prueba-error")
    errores, despues = [], []

    def _rompe():
        raise TimeoutError("OBS no contesta")

    servicio.encolar(_rompe, al_fallar=errores.append)
    servicio.encolar(lambda: "ok", al_terminar=despues.append)
    assert _esperar(lambda: errores and despues)
    assert isinstance(errores[0], TimeoutError)
    assert despues == ["ok"]
    servicio.detener()


def test_una_a_la_vez_descarta_si_ya_hay_uno():
    servicio = ServicioPedidos("prueba-una")
    liberar = threading.Event()
    corridas = []
    assert servicio.una_a_la_vez("escena", lambda: liberar.wait(2) and corridas.append(1))
    assert not servicio.una_a_la_vez("escena", lambda: corridas.append(2))
    liberar.set()
    assert _esperar(lambda: corridas == [1])
    assert _esperar(lambda: servicio.una_a_la_vez("escena", lambda: corridas.append(3)))
    assert _esperar(lambda: corridas == [1, 3])
    servicio.detener()


def test_vaciar_descarta_lo_pendiente():
    servicio = ServicioPedidos("prueba-vaciar")
    liberar = threading.Event()
    hechos = []
    servicio.encolar(lambda: liberar.wait(2))
    servicio.encolar(lambda: hechos.append("viejo"))
    time.sleep(0.05)
    servicio.vaciar()
    liberar.set()
    servicio.encolar(lambda: hechos.append("nuevo"))
    assert _esperar(lambda: hechos == ["nuevo"])
    servicio.detener()


def test_sondeo_no_se_apila():
    liberar = threading.Event()
    corridas = []
    assert sondeo_si_libre("prueba", lambda: (corridas.append(1), liberar.wait(2)))
    for _ in range(10):
        assert not sondeo_si_libre("prueba", lambda: corridas.append(2))
    liberar.set()
    assert _esperar(lambda: sondeo_si_libre("prueba", lambda: corridas.append(3)))
    assert _esperar(lambda: corridas == [1, 3])


def test_esperas_de_reconexion_crecen_y_se_estabilizan():
    esperas = [reconexion.espera_para_intento(n) for n in range(1, 9)]
    assert esperas[:5] == [2, 4, 8, 15, 30]
    assert esperas[5:] == [30, 30, 30]
    assert reconexion.espera_para_intento(0) == 2
