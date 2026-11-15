"""Pruebas de la capa OBS con un OBS simulado: socket de pedidos que se
reabre tras un timeout y comparación de volúmenes de la resincronización.

Correr con:  py -m pytest tests
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consola_obs import estado as E  # noqa: E402
from consola_obs.obs import cliente  # noqa: E402
from consola_obs.obs import eventos  # noqa: E402


class _ClienteFalso:
    """Simula un ReqClient de obsws-python."""
    creados = []

    def __init__(self, falla_con=None):
        self.falla_con = falla_con
        self.desconectado = False
        _ClienteFalso.creados.append(self)

    def get_version(self):
        if self.falla_con is not None:
            raise self.falla_con
        return "ok"

    def disconnect(self):
        self.desconectado = True


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    _ClienteFalso.creados = []
    monkeypatch.setattr(cliente.obs, "ReqClient", lambda **k: _ClienteFalso())
    monkeypatch.setattr(cliente.mod_red, "log_conexion", lambda *a, **k: None)
    monkeypatch.setattr(E, "conectado", True)
    monkeypatch.setattr(E, "_resync_pendiente", False, raising=False)
    monkeypatch.setattr(E, "_socket_pedidos_roto", False, raising=False)


def test_timeout_reabre_el_socket_y_pide_resincronizar():
    viejo = _ClienteFalso(falla_con=cliente.obs.error.OBSSDKTimeoutError("t"))
    envoltorio = cliente._ClienteOBSSincronizado(viejo, "host", 4455, "")
    with pytest.raises(cliente.obs.error.OBSSDKTimeoutError):
        envoltorio.get_version()
    assert viejo.desconectado
    assert E._resync_pendiente is True
    assert envoltorio.get_version() == "ok"       # ya usa el socket nuevo


def test_error_de_obs_bien_formado_no_reabre():
    error = cliente.obs.error.OBSSDKRequestError("GetInput", 600, "no existe")
    viejo = _ClienteFalso(falla_con=error)
    envoltorio = cliente._ClienteOBSSincronizado(viejo, "host", 4455, "")
    with pytest.raises(cliente.obs.error.OBSSDKRequestError):
        envoltorio.get_version()
    assert not viejo.desconectado
    assert E._resync_pendiente is False


def test_sin_poder_reabrir_marca_el_socket_roto(monkeypatch):
    def _no_conecta(**_k):
        raise ConnectionRefusedError("OBS cerrado")
    monkeypatch.setattr(cliente.obs, "ReqClient", _no_conecta)
    viejo = _ClienteFalso(falla_con=ConnectionResetError("corte"))
    envoltorio = cliente._ClienteOBSSincronizado(viejo, "host", 4455, "")
    with pytest.raises(ConnectionResetError):
        envoltorio.get_version()
    assert E._socket_pedidos_roto is True


def test_callback_que_explota_no_mata_el_hilo_de_eventos():
    def on_input_mute_state_changed(_datos):
        raise KeyError("fuente")
    envuelto = cliente._seguro(on_input_mute_state_changed)
    assert envuelto.__name__ == "on_input_mute_state_changed"   # obsws lo busca por nombre
    envuelto({})   # no lanza


@pytest.mark.parametrize("a, b, iguales", [
    (-12.0, -12.02, True),
    (-12.0, -11.5, False),
    (-100.0, -60.0, True),     # los dos en silencio
    (0.0, None, True),          # dato ilegible: no se toca nada
])
def test_mismo_volumen(a, b, iguales):
    assert eventos._mismo_volumen(a, b) is iguales


def test_cambio_local_reciente_manda_sobre_la_resincronizacion():
    eventos.nota_cambio_local("Mic")
    import time
    assert eventos._cambiado_hace_poco("Mic", time.monotonic())
    assert not eventos._cambiado_hace_poco("Otra", time.monotonic())


def test_host_local():
    assert cliente._host_es_esta_pc("localhost")
    assert cliente._host_es_esta_pc("pc", ["127.0.0.1"])
    assert not cliente._host_es_esta_pc("192.0.2.55", ["192.0.2.55"])
