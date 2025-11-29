import os
import subprocess
import logging
import urllib.parse
from flask import request
from urllib.parse import urlparse

TOKENS_FILE = "/opt/novnc/tokens"
BASE_LOCAL_PORT = 15000
OPENSTACK_TUNNEL_BASE = 16000  # Rango separado para túneles OpenStack
SSH_KEY_PATH = "/root/.ssh/id_rsa_novnc"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_public_host():
    """Obtiene la IP pública (del gateway) desde el request"""
    return request.host.split(":")[0]


def ensure_tunnel_and_token(slice_id, instance_id, worker_ip, vnc_port):
    """Crea túnel SSH para consolas VNC en clúster LINUX"""
    token = f"slice{slice_id}-vm{instance_id}"
    local_port = BASE_LOCAL_PORT + int(instance_id)

    logger.info(f"🌀 Creando túnel para {token}")
    logger.info(f"   Worker IP: {worker_ip} | VNC port: {vnc_port} | Local port: {local_port}")

    try:
        # Chequear si ya hay un túnel abierto
        result = subprocess.run(["ss", "-tln"], capture_output=True, text=True)
        if f":{local_port} " in result.stdout:
            logger.info(f"🔁 Túnel ya activo en localhost:{local_port}, no se recrea")
        else:
            subprocess.run([
                "ssh",
                "-i", SSH_KEY_PATH,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ExitOnForwardFailure=yes",
                "-N", "-f",
                "-L", f"0.0.0.0:{local_port}:{worker_ip}:{vnc_port}",
                f"ubuntu@{worker_ip}"
            ], check=True)
            logger.info(f"✅ Túnel SSH creado: localhost:{local_port} → {worker_ip}:{vnc_port}")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error creando túnel SSH: {e}")
        raise
    except FileNotFoundError:
        logger.error("❌ Comando 'ssh' no encontrado")
        raise

    # Actualizar archivo de tokens
    try:
        lines = []
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, "r") as f:
                for line in f:
                    if not line.startswith(token + ":"):
                        lines.append(line.strip())

        lines = [line for line in lines if line.strip()]
        lines.append(f"{token}: web_app:{local_port}")

        os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)
        with open(TOKENS_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")

        logger.info(f"✅ Token registrado: {token} → 127.0.0.1:{local_port}")
    except Exception as e:
        logger.error(f"❌ Error escribiendo token: {e}")
        raise

    # Generar URL para el navegador
    public_ip = get_public_host()
    novnc_url = (
        f"http://{public_ip}:6080/vnc.html"
        f"?path=websockify?token={token}"
        f"&autoconnect=true&resize=scale&reconnect=true"
    )

    logger.info(f"🌐 URL generada: {novnc_url}")
    return novnc_url


def ensure_openstack_tunnel_and_token(slice_id, instance_id, console_url, gateway_ip=None):
    """
    Crea túnel SSH para consolas OpenStack
    
    Args:
        slice_id: ID del slice
        instance_id: ID de la instancia
        console_url: URL de consola de OpenStack (ej: http://controller:6080/vnc_auto.html?path=...)
        gateway_ip: IP del gateway (donde está el portforwarding). Default: se obtiene del request
    
    Returns:
        URL accesible desde el navegador local
    """
    if gateway_ip is None:
        gateway_ip = get_public_host()
    
    token = f"slice{slice_id}-vm{instance_id}-os"
    local_port = OPENSTACK_TUNNEL_BASE + int(instance_id)
    
    logger.info(f"🌀 [OpenStack] Procesando consola para {token}")
    logger.info(f"   Console URL original: {console_url}")
    
    try:
        # Parsear la URL de OpenStack
        parsed = urlparse(console_url)
        controller_hostname = parsed.netloc.split(":")[0]  # "controller"
        controller_port = parsed.port or 6080
        
        logger.info(f"   Controller: {controller_hostname}:{controller_port}")
        logger.info(f"   Local port: {local_port}")
        
        # 1️⃣ Crear túnel SSH desde app hacia OpenStack controller
        # La conexión será: app (localhost:local_port) → SSH → worker con acceso a controller
        # IMPORTANTE: necesitas un worker que tenga acceso SSH al controller de OpenStack
        
        # Opción A: Si el gateway tiene acceso directo a OpenStack
        tunnel_target = gateway_ip  # o el IP del worker con acceso a controller
        
        result = subprocess.run(["ss", "-tln"], capture_output=True, text=True)
        if f":{local_port} " in result.stdout:
            logger.info(f"🔁 Túnel ya activo en localhost:{local_port}")
        else:
            # Crear túnel: localhost:local_port → controller:controller_port (a través de SSH)
            subprocess.run([
                "ssh",
                "-i", SSH_KEY_PATH,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ExitOnForwardFailure=yes",
                "-N", "-f",
                "-L", f"0.0.0.0:{local_port}:{controller_hostname}:{controller_port}",
                f"ubuntu@{tunnel_target}"
            ], check=True)
            logger.info(f"✅ Túnel SSH creado: localhost:{local_port} → {controller_hostname}:{controller_port}")
        
        # 2️⃣ Reconstruir la URL apuntando al túnel local
        # URL original: http://controller:6080/vnc_auto.html?path=%3Ftoken%3Db0ed3813...
        # URL nueva: http://127.0.0.1:local_port/vnc_auto.html?path=%3Ftoken%3Db0ed3813...
        
        path_and_query = parsed.path
        if parsed.query:
            path_and_query += "?" + parsed.query
        
        new_console_url = f"http://127.0.0.1:{local_port}{path_and_query}"
        
        logger.info(f"✅ Nueva URL de consola: {new_console_url}")
        
        return new_console_url
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error creando túnel OpenStack: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Error procesando consola OpenStack: {e}")
        raise


def parse_openstack_console_url(console_url):
    """
    Analiza una URL de consola OpenStack y extrae componentes
    
    Returns:
        dict con 'controller_host', 'controller_port', 'path', 'query'
    """
    parsed = urlparse(console_url)
    
    host_parts = parsed.netloc.split(":")
    controller_host = host_parts[0]
    controller_port = int(host_parts[1]) if len(host_parts) > 1 else 6080
    
    return {
        'controller_host': controller_host,
        'controller_port': controller_port,
        'path': parsed.path,
        'query': parsed.query,
        'full_url': console_url
    }