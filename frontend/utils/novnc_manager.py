import os
import subprocess
import logging
import urllib.parse
from flask import request
from urllib.parse import urlparse

TOKENS_FILE = "/opt/novnc/tokens"
BASE_LOCAL_PORT = 15000
OPENSTACK_TUNNEL_BASE = 16000
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
    Crea túnel SSH MULTISALTO para consolas OpenStack
    
    Flujo: app (localhost:16XXX) → SSH → gateway → SSH → controller:6080
    
    Args:
        slice_id: ID del slice
        instance_id: ID de la instancia
        console_url: URL de consola de OpenStack (ej: http://controller:6080/vnc_auto.html?path=...)
        gateway_ip: IP del gateway (opcional, se obtiene de variable de entorno si no se proporciona)
    
    Returns:
        URL accesible desde el navegador local
    """
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
        
        # 🟢 OBTENER CONFIGURACIÓN DE LA PUERTA DE ENLACE
        if gateway_ip is None:
            gateway_ip = os.getenv("GATEWAY_IP", "10.20.12.106")
        gateway_user = os.getenv("GATEWAY_USER", "ubuntu")
        gateway_ssh_key = os.getenv("GATEWAY_SSH_KEY", "/root/.ssh/id_rsa_novnc")  # 🟢 Usar id_rsa_novnc
        
        logger.info(f"   Gateway: {gateway_user}@{gateway_ip}")
        
        # Verificar si el túnel ya existe
        result = subprocess.run(["ss", "-tln"], capture_output=True, text=True)
        if f":{local_port} " in result.stdout:
            logger.info(f"🔁 Túnel ya activo en localhost:{local_port}")
            # Reconstruir URL de todas formas
            path_and_query = parsed.path
            if parsed.query:
                path_and_query += "?" + parsed.query
            
            new_console_url = f"http://127.0.0.1:{local_port}{path_and_query}"
            logger.info(f"✅ URL de consola (reutilizada): {new_console_url}")
            return new_console_url
        
        # 🟢 CREAR TÚNEL MULTISALTO
        # opción 1: Túnel simple si controller es accesible desde gateway
        # app:16007 → SSH(gateway) → controller:6080
        
        logger.info(f"   🔗 Creando túnel: localhost:{local_port} → {gateway_ip} → {controller_hostname}:{controller_port}")
        
        subprocess.run([
            "ssh",
            "-i", gateway_ssh_key,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ExitOnForwardFailure=yes",
            "-N", "-f",
            "-L", f"0.0.0.0:{local_port}:{controller_hostname}:{controller_port}",
            f"{gateway_user}@{gateway_ip}"
        ], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        
        logger.info(f"✅ Túnel SSH multisalto creado: localhost:{local_port} → {gateway_ip} → {controller_hostname}:{controller_port}")
        
        # 🟢 RECONSTRUIR LA URL APUNTANDO AL TÚNEL LOCAL
        path_and_query = parsed.path
        if parsed.query:
            path_and_query += "?" + parsed.query
        
        new_console_url = f"http://127.0.0.1:{local_port}{path_and_query}"
        
        logger.info(f"✅ Nueva URL de consola: {new_console_url}")
        
        return new_console_url
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error creando túnel OpenStack: {e}")
        logger.error(f"   stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        logger.error(f"   stdout: {e.stdout if hasattr(e, 'stdout') else 'N/A'}")
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