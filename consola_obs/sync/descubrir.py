"""Descubrimiento y vinculación en LAN (sin Tk, testeable).

Dos PCs con el programa abierto se encuentran solas por broadcast UDP
(puerto 4457) y pueden VINcularse con un clic: la que pide manda su
clave y la otra la adopta al aceptar. Así la clave se escribe CERO
veces (queda guardada: es configuración de una sola vez).

Protocolo (JSON por datagrama, app="ConsolaOBS-sync", v=1):
  -> broadcast  {"t":"DISCOVER", ...}
  <- unicast    {"t":"HELLO", "host": nombre, "port": 4456, "mini": bool}
  -> unicast    {"t":"PAIR", "key": clave, "host": nombre, "port": 4456}
  <- unicast    {"t":"PAIRED", "ok": true/false}

Sólo red local:pensado para WiFi/red de confianza (igual que la clave
impresa en consola). Todo con timeouts; nunca lanza.
"""
import json
import socket
import threading
import time

PUERTO_DISCOVERY = 4457
APP_ID = "ConsolaOBS-sync"
VERSION_PROTO = 1


def _nombre_equipo():
    try:
        return socket.gethostname() or "PC"
    except Exception:
        return "PC"


def _mensaje(tipo, extra=None):
    msg = {"t": tipo, "app": APP_ID, "v": VERSION_PROTO}
    if extra:
        msg.update(extra)
    return msg


def _es_nuestro(datos):
    try:
        return (isinstance(datos, dict) and datos.get("app") == APP_ID
                and int(datos.get("v", 0)) == VERSION_PROTO)
    except Exception:
        return False


def _socket_escucha(puerto=PUERTO_DISCOVERY, timeout=0.5):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    try:
        s.bind(("0.0.0.0", puerto))
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return None
    try:
        s.settimeout(timeout)
    except Exception:
        pass
    return s


def _socket_envio():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    except Exception:
        pass
    return s


def buscar_pcs(puerto_sync, timeout=3.0, puerto_disc=PUERTO_DISCOVERY):
    """Broadcast DISCOVER y junta los HELLO por `timeout` segundos.
    Devuelve [{"ip":..., "host":..., "port":..., "mini":...}] sin
    duplicados (por ip). Nunca lanza."""
    halladas = {}
    # Un solo socket para enviar Y recibir: las respuestas vuelven al
    # puerto origen del broadcast, que es este.
    s = _socket_envio()
    try:
        s.bind(("0.0.0.0", 0))
    except Exception:
        pass
    try:
        s.settimeout(0.5)
    except Exception:
        pass
    try:
        try:
            s.sendto(json.dumps(_mensaje("DISCOVER")).encode("utf-8"),
                     ("<broadcast>", puerto_disc))
        except Exception:
            pass
        fin = time.monotonic() + max(0.5, timeout)
        while time.monotonic() < fin:
            try:
                cuerpo, origen = s.recvfrom(2048)
            except Exception:
                continue
            try:
                datos = json.loads(cuerpo.decode("utf-8", "replace"))
            except Exception:
                continue
            if not _es_nuestro(datos) or datos.get("t") != "HELLO":
                continue
            try:
                ip = origen[0]
                if ip not in halladas:
                    halladas[ip] = {
                        "ip": ip,
                        "host": str(datos.get("host") or ip),
                        "port": int(datos.get("port") or puerto_sync),
                        "mini": bool(datos.get("mini", False)),
                    }
            except Exception:
                continue
    finally:
        try:
            s.close()
        except Exception:
            pass
    return list(halladas.values())


def pedir_vinculo(ip, clave, puerto_sync, timeout=8.0, puerto_disc=PUERTO_DISCOVERY):
    """Manda PAIR a `ip` y espera PAIRED. Devuelve (True, "") si la otra
    PC aceptó (adoptó nuestra clave), (False, motivo) si no. Nunca lanza."""
    s = _socket_envio()
    try:
        s.bind(("0.0.0.0", 0))
    except Exception:
        pass
    try:
        s.settimeout(0.5)
    except Exception:
        pass
    try:
        s.sendto(json.dumps(_mensaje("PAIR", {
            "key": clave, "host": _nombre_equipo(), "port": puerto_sync,
        })).encode("utf-8"), (ip, puerto_disc))
    except Exception as e:
        try:
            s.close()
        except Exception:
            pass
        return False, f"No se pudo mandar el pedido: {e}"
    fin = time.monotonic() + max(1.0, timeout)
    try:
        while time.monotonic() < fin:
            try:
                cuerpo, _origen = s.recvfrom(2048)
            except Exception:
                continue
            try:
                datos = json.loads(cuerpo.decode("utf-8", "replace"))
            except Exception:
                continue
            if _es_nuestro(datos) and datos.get("t") == "PAIRED":
                if datos.get("ok"):
                    return True, ""
                return False, str(datos.get("motivo") or "") or \
                    "La otra PC rechazó la vinculación."
    finally:
        try:
            s.close()
        except Exception:
            pass
    return False, "Sin respuesta (¿el programa está abierto allá? ¿misma red?)."


def responder_vinculo(ip, puerto_dest, puerto_disc=PUERTO_DISCOVERY):
    """Avisa PAIRED ok=True a `ip:puerto_dest` (el puerto origen del
    pedido; el fijo sólo de respaldo). Nunca lanza."""
    s = _socket_envio()
    try:
        s.sendto(json.dumps(_mensaje("PAIRED", {"ok": True})).encode("utf-8"),
                 (ip, puerto_dest or puerto_disc))
    except Exception:
        pass
    try:
        s.close()
    except Exception:
        pass


def rechazar_vinculo(ip, puerto_dest, puerto_disc=PUERTO_DISCOVERY):
    """Avisa PAIRED ok=False a `ip:puerto_dest`. Nunca lanza."""
    s = _socket_envio()
    try:
        s.sendto(json.dumps(_mensaje("PAIRED", {"ok": False})).encode("utf-8"),
                 (ip, puerto_dest or puerto_disc))
    except Exception:
        pass
    try:
        s.close()
    except Exception:
        pass


def iniciar_escucha(puerto_sync, es_mini, al_hola=None, al_par=None, log=None,
                    puerto_disc=PUERTO_DISCOVERY):
    """Hilo daemon que responde DISCOVER y deriva PAIR a `al_par`.
    al_hola(ip, msg) y al_par(ip, msg) corren en el hilo de red (la UI
    debe usar after). Devuelve True si quedó escuchando. Nunca lanza."""
    def _log(m):
        try:
            (log or print)(m)
        except Exception:
            pass

    s = _socket_escucha(puerto_disc, timeout=0.5)
    if s is None:
        _log("Discovery: puerto 4457 ocupado, sin escucha (el sync igual anda a mano).")
        return False

    def _correr():
        while True:
            try:
                cuerpo, origen = s.recvfrom(4096)
            except Exception:
                continue
            try:
                datos = json.loads(cuerpo.decode("utf-8", "replace"))
            except Exception:
                continue
            if not _es_nuestro(datos):
                continue
            try:
                ip, pto = origen[0], int(origen[1])
            except Exception:
                continue
            try:
                if datos.get("t") == "DISCOVER":
                    r = _socket_envio()
                    try:
                        r.sendto(json.dumps(_mensaje("HELLO", {
                            "host": _nombre_equipo(), "port": puerto_sync,
                            "mini": bool(es_mini),
                        })).encode("utf-8"), (ip, pto))
                    except Exception:
                        pass
                    try:
                        r.close()
                    except Exception:
                        pass
                    if al_hola:
                        al_hola(ip, datos)
                elif datos.get("t") == "PAIR" and al_par:
                    al_par(ip, datos, pto)
            except Exception:
                continue

    try:
        h = threading.Thread(target=_correr, daemon=True)
        h.start()
        return True
    except Exception as e:
        _log(f"Discovery: no se pudo iniciar ({e}).")
        try:
            s.close()
        except Exception:
            pass
        return False
