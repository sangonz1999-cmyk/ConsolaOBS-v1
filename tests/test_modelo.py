"""Pruebas del modelo del mezclador, los avisos y los pedidos por lote.

Correr con:  py -m pytest tests
"""
import json
import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from consola_obs import estado as E  # noqa: E402
from consola_obs.nucleo import avisos, hilo_ui  # noqa: E402
from consola_obs.nucleo.modelo import Mezclador, tipo_monitor_normalizado  # noqa: E402
from consola_obs.obs import cliente  # noqa: E402


@pytest.fixture
def recibidos():
    avisos.limpiar()
    lista = []
    avisos.suscribir("fuente_cambiada", lambda *a: lista.append(a))
    yield lista
    avisos.limpiar()


def _despachar():
    hilo_ui.ejecutar_pendientes()


def test_solo_avisa_lo_que_cambio(recibidos):
    m = Mezclador()
    m.actualizar("Mic", volumen_db=-10.0, muted=False, tipo_monitor=0)
    _despachar()
    assert recibidos == [("Mic", {"volumen_db": -10.0, "muted": False,
                                  "tipo_monitor": "OBS_MONITORING_TYPE_NONE"}, "obs")]
    recibidos.clear()
    m.actualizar("Mic", volumen_db=-10.01, muted=False)   # dentro de la tolerancia
    _despachar()
    assert recibidos == []
    m.actualizar("Mic", origen="local", muted=True)
    _despachar()
    assert recibidos == [("Mic", {"muted": True}, "local")]


def test_silencio_cuenta_como_igual(recibidos):
    m = Mezclador()
    m.actualizar("Mic", volumen_db=-100.0, avisar=False)
    m.actualizar("Mic", volumen_db=-60.0)
    _despachar()
    assert recibidos == []


def test_forzar_avisa_aunque_coincida(recibidos):
    m = Mezclador()
    m.actualizar("Mic", muted=True, avisar=False)
    m.actualizar("Mic", origen="resync", forzar=True, muted=True)
    _despachar()
    assert recibidos == [("Mic", {"muted": True}, "resync")]


def test_renombrar_y_limpiar():
    m = Mezclador()
    m.actualizar("Viejo", muted=True, avisar=False)
    m.renombrar("Viejo", "Nuevo")
    assert m.obtener("Viejo") is None
    assert m.obtener("Nuevo").muted is True
    m.limpiar()
    assert m.nombres() == []


def test_monitor_numerico():
    assert tipo_monitor_normalizado(2) == "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT"
    assert tipo_monitor_normalizado("1") == "OBS_MONITORING_TYPE_MONITOR_ONLY"
    assert tipo_monitor_normalizado("OBS_MONITORING_TYPE_NONE") == "OBS_MONITORING_TYPE_NONE"


def test_suscriptor_que_explota_no_frena_a_los_demas():
    avisos.limpiar()
    llegaron = []
    avisos.suscribir("x", lambda: 1 / 0)
    avisos.suscribir("x", lambda: llegaron.append(1))
    avisos.emitir("x")
    _despachar()
    assert llegaron == [1]
    avisos.limpiar()


def test_la_capa_obs_no_carga_la_interfaz():
    """El ciclo obs/cliente -> obs/eventos -> ui/tarjeta_fuente quedó roto."""
    codigo = ("import sys; import consola_obs.obs.cliente, consola_obs.obs.eventos;"
              "print([m for m in sys.modules if m.startswith('consola_obs.ui')])")
    salida = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ,
                            capture_output=True, text=True, check=True).stdout.strip()
    assert salida == "[]"


# ---------------------------------------------------------------------
# Pedidos por lote
# ---------------------------------------------------------------------
class _SocketFalso:
    def __init__(self, respuestas_previas=()):
        self.enviados = []
        self._cola = [json.dumps(r) for r in respuestas_previas]

    def send(self, texto):
        mensaje = json.loads(texto)
        self.enviados.append(mensaje)
        d = mensaje["d"]
        resultados = []
        for p in d["requests"]:
            nombre = (p.get("requestData") or {}).get("inputName")
            if nombre == "NoExiste":
                resultados.append({"requestId": p["requestId"], "requestType": p["requestType"],
                                   "requestStatus": {"result": False, "code": 600}})
            else:
                resultados.append({"requestId": p["requestId"], "requestType": p["requestType"],
                                   "requestStatus": {"result": True, "code": 100},
                                   "responseData": {"inputMuted": nombre == "Mic"}})
        self._cola.append(json.dumps({"op": 9, "d": {"requestId": d["requestId"],
                                                     "results": resultados}}))

    def recv(self):
        return self._cola.pop(0)


class _ClienteConSocket:
    def __init__(self, ws):
        self.base_client = type("B", (), {"ws": ws})()

    def disconnect(self):
        pass


def test_lote_devuelve_en_orden_y_tolera_fallos(monkeypatch):
    monkeypatch.setattr(E, "conectado", True)
    ws = _SocketFalso(respuestas_previas=[{"op": 7, "d": {"requestId": "viejo"}}])
    envoltorio = cliente._ClienteOBSSincronizado(_ClienteConSocket(ws), "h", 1, "")
    pedidos = [("GetInputMute", {"inputName": n}) for n in ("Mic", "NoExiste", "Musica")]
    resultado = envoltorio.lote(pedidos)
    assert resultado == [(True, {"inputMuted": True}), (False, 600), (True, {"inputMuted": False})]
    assert len(ws.enviados) == 1 and ws.enviados[0]["op"] == 8


def test_lote_se_parte_en_tramos(monkeypatch):
    monkeypatch.setattr(E, "conectado", True)
    ws = _SocketFalso()
    envoltorio = cliente._ClienteOBSSincronizado(_ClienteConSocket(ws), "h", 1, "")
    resultado = envoltorio.lote([("GetInputMute", {"inputName": "Mic"})] * 130, tamano=60)
    assert len(resultado) == 130 and all(ok for ok, _ in resultado)
    assert [len(m["d"]["requests"]) for m in ws.enviados] == [60, 60, 10]


def test_ganancia_desde_la_lista_de_filtros():
    from consola_obs import constantes as C
    from consola_obs.obs import eventos
    kind, campo = next(iter(C.CAMPOS_GANANCIA_FILTRO.items()))
    filtros = [
        {"filterKind": kind, "filterEnabled": True, "filterSettings": {campo: 6.0}},
        {"filterKind": kind, "filterEnabled": False, "filterSettings": {campo: 20.0}},
        {"filterKind": "otro", "filterEnabled": True, "filterSettings": {}},
    ]
    assert eventos._ganancia_de_lista_filtros(filtros) == 6.0
    # Sin ajustes (OBS viejo): hay que pedirlos de a uno.
    assert eventos._ganancia_de_lista_filtros([{"filterKind": kind, "filterEnabled": True}]) is None
