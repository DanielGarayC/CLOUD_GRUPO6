import os
import subprocess
import logging

TOKENS_FILE = "/opt/novnc/tokens"
BASE_LOCAL_PORT = 15000

# Configura logging básico si no lo tienes
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def ensure_tunnel_and_token(slice_id, instance_id, worker_ip, vnc_port):
    token = f"slice{slice_id}-vm{instance_id}"
    local_port = BASE_LOCAL_PORT + int(instance_id)

    logger.info(f"🌀 Creando túnel para {token}")
    logger.info(f"   Worker IP: {worker_ip} | VNC port: {vnc_port} | Local port: {local_port}")

    # 1️⃣ Crear el túnel SSH
    try:
        subprocess.run([
            "ssh", "-f", "-N",
            "-L", f"{local_port}:127.0.0.1:{vnc_port}",
            f"ubuntu@{worker_ip}"
        ], check=True)
        logger.info(f"✅ Túnel SSH creado: localhost:{local_port} → {worker_ip}:{vnc_port}")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error creando túnel SSH: {e}")
        raise

    # 2️⃣ Actualizar archivo de tokens
    try:
        lines = []
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, "r") as f:
                for line in f:
                    if not line.startswith(token + " "):
                        lines.append(line.strip())

        lines.append(f"{token} 127.0.0.1:{local_port}")

        os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)
        with open(TOKENS_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")

        logger.info(f"✅ Token registrado en {TOKENS_FILE}: {token} → 127.0.0.1:{local_port}")
    except Exception as e:
        logger.error(f"❌ Error escribiendo token: {e}")
        raise

    # 3️⃣ Generar URL final
    headnode_ip = "192.168.201.1"  # tu headnode
    novnc_url = (
        f"http://{headnode_ip}:6080/vnc.html"
        f"?path=websockify?token={token}"
        f"&autoconnect=true&resize=scale&reconnect=true"
    )
    logger.info(f"🌐 URL generada: {novnc_url}")
    return novnc_url
