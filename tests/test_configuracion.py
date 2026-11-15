"""Pruebas del guardado de ajustes, el cifrado de secretos y el registro.

Correr con:  py -m pytest tests
Todo se redirige a una carpeta temporal: no toca la config real.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consola_obs import rutas as R  # noqa: E402
from consola_obs import configuracion as cfg  # noqa: E402
from consola_obs import estado as E  # noqa: E402
from consola_obs import secretos  # noqa: E402
from consola_obs.sync import configuracion as cfg_sync  # noqa: E402

SOLO_WINDOWS = pytest.mark.skipif(not sys.platform.startswith("win"), reason="DPAPI es de Windows")


@pytest.fixture(autouse=True)
def config_temporal(tmp_path, monkeypatch):
    carpeta = tmp_path / "config"
    carpeta.mkdir()
    monkeypatch.setattr(R, "CARPETA_CONFIG", str(carpeta))
    for nombre in ("ARCHIVO_CONEXION", "ARCHIVO_SOUNDBOARD", "ARCHIVO_INTERFAZ", "ARCHIVO_MUSICA"):
        monkeypatch.setattr(R, nombre, str(carpeta / os.path.basename(getattr(R, nombre))))
    monkeypatch.setattr(cfg_sync, "ARCHIVO_SYNC_CONFIG", str(carpeta / "sync_config.json"))
    monkeypatch.delenv(cfg_sync.VAR_ENTORNO_KEY, raising=False)
    return carpeta


@SOLO_WINDOWS
def test_secretos_ida_y_vuelta():
    protegido = secretos.proteger("clave-ñ-123")
    assert protegido.startswith(secretos.PREFIJO)
    assert secretos.desproteger(protegido) == "clave-ñ-123"


def test_secretos_texto_plano_y_blob_invalido():
    assert secretos.desproteger("plana") == "plana"
    assert secretos.desproteger("dpapi:no-es-valido") == ""
    assert secretos.proteger("") == ""


@SOLO_WINDOWS
def test_password_de_obs_no_queda_en_texto_plano():
    cfg.guardar_config_conexion("192.168.1.10", 4455, "secreta")
    with open(R.ARCHIVO_CONEXION, encoding="utf-8") as f:
        assert "secreta" not in f.read()
    datos = cfg.cargar_config_conexion()
    assert datos["password"] == "secreta" and datos["host"] == "192.168.1.10"


def test_password_vieja_en_texto_plano_se_sigue_leyendo():
    with open(R.ARCHIVO_CONEXION, "w", encoding="utf-8") as f:
        json.dump({"host": "x", "puerto": "1", "password": "vieja"}, f)
    assert cfg.cargar_config_conexion()["password"] == "vieja"


def test_interfaz_conserva_las_demas_claves():
    cfg.guardar_config_interfaz({"a": 1})
    cfg.guardar_config_interfaz({"b": 2})
    assert cfg.cargar_config_interfaz() == {"a": 1, "b": 2}
    assert not os.path.exists(R.ARCHIVO_INTERFAZ + ".tmp")


def test_interfaz_ilegible_no_se_pisa():
    with open(R.ARCHIVO_INTERFAZ, "w", encoding="utf-8") as f:
        f.write("{roto")
    cfg.guardar_config_interfaz({"c": 3})
    with open(R.ARCHIVO_INTERFAZ, encoding="utf-8") as f:
        assert f.read() == "{roto"


def test_rutas_de_pads_relativas_en_disco_y_absolutas_en_memoria(tmp_path, monkeypatch):
    raiz = tmp_path / "programa"
    sonido = raiz / "assets" / "Sondidos_pad" / "aplausos.mp3"
    sonido.parent.mkdir(parents=True)
    sonido.write_bytes(b"x")
    monkeypatch.setattr(R, "CARPETA_SCRIPT", str(raiz))
    monkeypatch.setattr(R, "CARPETA_ASSETS", str(raiz / "assets"))
    with open(R.ARCHIVO_SOUNDBOARD, "w", encoding="utf-8") as f:
        json.dump({
            # ruta absoluta de otra instalación: se reubica en la nuestra
            "0": {"archivo": r"X:\otra\ConsolaOBS\assets\Sondidos_pad\aplausos.mp3",
                  "nivel_archivo": "assets/Sondidos_pad/aplausos.mp3", "imagen": None},
            # fuera de la carpeta del programa: queda tal cual
            "1": {"archivo": r"C:\fuera\x.mp3"},
        }, f)
    cfg.cargar_config_soundboard()
    assert os.path.samefile(E.config_soundboard["0"]["archivo"], sonido)
    assert os.path.samefile(E.config_soundboard["0"]["nivel_archivo"], sonido)

    cfg.guardar_config_soundboard()
    with open(R.ARCHIVO_SOUNDBOARD, encoding="utf-8") as f:
        guardado = json.load(f)
    assert guardado["0"]["archivo"] == "assets/Sondidos_pad/aplausos.mp3"
    assert guardado["1"]["archivo"] == r"C:\fuera\x.mp3"
    assert os.path.isabs(E.config_soundboard["0"]["archivo"])


def test_soundboard_ilegible_no_se_pisa_con_vacio():
    with open(R.ARCHIVO_SOUNDBOARD, "w", encoding="utf-8") as f:
        f.write("{roto")
    cfg.cargar_config_soundboard()
    cfg.guardar_config_soundboard()
    with open(R.ARCHIVO_SOUNDBOARD, encoding="utf-8") as f:
        assert f.read() == "{roto"


@SOLO_WINDOWS
def test_clave_de_sync_cifrada_y_estable():
    clave = cfg_sync.obtener_api_key()
    with open(cfg_sync.ARCHIVO_SYNC_CONFIG, encoding="utf-8") as f:
        assert clave not in f.read()
    assert cfg_sync.cargar()["api_key"] == clave
    assert cfg_sync.obtener_api_key() == clave
