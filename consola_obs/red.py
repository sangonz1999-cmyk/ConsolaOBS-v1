"""Red local + firewall para OBS-WebSocket.

WinError 10061 = la PC destino rechazo la conexion: no hay nada
escuchando en esa IP:puerto. Casi siempre es:
  - OBS cerrado o WebSocket apagado en la PC destino, o
  - Host mal puesto (localhost cuando el OBS esta en otra PC),
y NO un firewall (el firewall suele dar timeout 10060, no rechazo).

Este modulo:
  - detecta la IP LAN de ESTA pc (para mostrarla y copiarla en la
    otra PC),
  - asegura la regla de firewall entrante TCP para el puerto
    (4455 por defecto) de forma automatica (pide admin si falta),
  - arma un mensaje de error amigable segun el caso.
"""
import socket
import subprocess
import sys

_ES_WINDOWS = sys.platform.startswith("win")


def obtener_todas_ips_locales():
    """Todas las IPv4 locales utiles (sin loopback ni link-local)."""
    ips = []
    # 1) La IP de la interfaz que saldria a internet (no manda nada,
    # solo pregunta al SO que interfaz usaria).
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            ips.append(ip)
    except Exception:
        pass
    # 2) Las que informa el hostname (puede traer varias).
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def obtener_ip_local():
    """La mejor candidata a 'mi IP en la red local' o '' si no hay."""
    ips = obtener_todas_ips_locales()
    if not ips:
        return ""
    # Prefiere privadas tipicas 192.168/10/172.16 antes que otras.
    def _prioridad(ip):
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            try:
                n = int(ip.split(".")[1])
                if 16 <= n <= 31:
                    return 2
            except Exception:
                pass
        return 3
    return sorted(ips, key=_prioridad)[0]


def es_admin():
    """True si el proceso ya corre elevado (solo Windows)."""
    if not _ES_WINDOWS:
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _nombre_regla(puerto):
    return f"ConsolaOBS OBS WebSocket {puerto}"


def regla_firewall_existe(puerto):
    """True si ya hay regla inbound para ese puerto TCP."""
    if not _ES_WINDOWS:
        return False
    nombre = _nombre_regla(puerto)
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={nombre}"],
            capture_output=True, text=True, timeout=10,
        )
        salida = (r.stdout or "") + (r.stderr or "")
        # Cuando no existe dice "No rules match / No hay reglas".
        if r.returncode == 0 and str(puerto) in salida and (
            "Allow" in salida or "Permitir" in salida or "Sí" in salida or "Si" in salida
        ):
            return True
        return False
    except Exception:
        return False


def asegurar_regla_firewall(puerto):
    """Crea la regla inbound TCP si falta.

    Devuelve (ok, necesita_admin, mensaje). No lanza excepciones:
    esta pensado para llamarse antes de conectar, en silencio.
    Requiere permisos de administrador en Windows: sin ellos
    devuelve necesita_admin=True para que la UI avise.
    """
    try:
        puerto = int(puerto)
    except Exception:
        return (False, False, "Puerto inválido.")
    if not _ES_WINDOWS:
        return (False, False, "El firewall automático solo está soportado en Windows.")
    if regla_firewall_existe(puerto):
        return (True, False, f"La regla para el puerto {puerto} ya existe.")
    nombre = _nombre_regla(puerto)
    try:
        r = subprocess.run(
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={nombre}", "dir=in", "action=allow",
                "protocol=TCP", f"localport={puerto}",
                "profile=private,domain", "description=Permitir ConsolaOBS a OBS WebSocket",
            ],
            capture_output=True, text=True, timeout=15,
        )
        salida = ((r.stdout or "") + " " + (r.stderr or "")).strip()
        if r.returncode == 0:
            return (True, False, f"Regla creada: se permite TCP {puerto} entrante (red privada/dominio).")
        baja = salida.lower()
        if "deneg" in baja or "access denied" in baja or "elevation" in baja or "administrator" in baja or "administrador" in baja:
            return (False, True, "Hace falta ejecutar como administrador para crear la regla de firewall.")
        return (False, False, f"No se pudo crear la regla: {salida or 'error desconocido'}")
    except Exception as e:
        return (False, False, f"No se pudo tocar el firewall: {e}")


def es_localhost(host):
    return (host or "").strip().lower() in ("", "localhost", "127.0.0.1", "::1")


def mensaje_error_conexion(exc, host, puerto):
    """Texto amigable para el messagebox segun el error real."""
    detalle = str(exc).strip() or repr(exc)
    baja = detalle.lower()
    ip_local = obtener_ip_local() or "(no detectada)"
    base_obs = (
        "En la PC donde está OBS:\n"
        "1. Abrí OBS → Herramientas → Configuración del servidor WebSocket.\n"
        "2. Tildá 'Habilitar servidor WebSocket' y que el puerto sea "
        f"{puerto}.\n"
        "3. Dejá OBS abierto mientras conectás."
    )
    if "10061" in detalle or "actively refused" in baja or "deneg" in baja and "expresamente" in baja:
        if es_localhost(host):
            return (
                "OBS rechazó la conexión (WinError 10061: nada escucha en "
                f"{host or 'localhost'}:{puerto}).\n\n"
                f"{base_obs}\n\n"
                "Si OBS ya está abierto y sigue fallando, revisá que la "
                "contraseña coincida."
            )
        return (
            "La otra PC rechazó la conexión (WinError 10061: llegaste a la "
            f"PC {host} pero ahí no hay ningún OBS escuchando en el puerto "
            f"{puerto}).\n\n"
            f"{base_obs} (¡en LA OTRA pc, no en esta!)\n\n"
            f"En ESTA pc el Host debe ser la IP de LA OTRA pc.\n"
            f"La IP de ESTA pc es {ip_local} (esa se pone en la OTRA pc, "
                "no acá).\n"
                "Para ver la IP de la otra pc: abrí ConsolaOBS ahí y mirá "
                "el cartel 'IP de esta PC', o ejecutá 'ipconfig'."
            )
    if "10060" in detalle or "timed out" in baja or "tiempo de espera" in baja:
        return (
            f"No hubo respuesta de {host}:{puerto} (timeout).\n"
            "Eso suele ser firewall o red, no OBS apagado.\n\n"
            "1. Ping desde esta PC: ping "
            f"{host}.\n"
            "2. Misma WiFi/red (ojo con red de invitados o aislamiento AP).\n"
            f"3. En la PC del OBS, botón '🛡 Firewall' (como admin) para abrir el puerto {puerto}.\n"
            f"4. Probar: Test-NetConnection -ComputerName {host} -Port {puerto}."
        )
    if "401" in baja or "auth" in baja or "password" in baja or "contrase" in baja:
        return (
            "OBS respondió pero rechazó la contraseña (auth).\n\n"
            "Copiá la contraseña exacta de OBS → Herramientas → "
            "Configuración del servidor WebSocket."
        )
    return (
        f"No se pudo conectar a OBS en {host}:{puerto}.\n\n{detalle}\n\n"
        f"{base_obs}\n"
        f"Tu IP local es {ip_local}."
    )
