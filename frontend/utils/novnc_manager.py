import os
import subprocess
import logging

TOKENS_FILE = "/opt/novnc/tokens"
BASE_LOCAL_PORT = 15000
SSH_KEY_PATH = "/root/.ssh/id_rsa_orch"

# Logging básico
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def ensure_tunnel_and_token(slice_id, instance_id, worker_ip, vnc_port):
    token = f"slice{slice_id}-vm{instance_id}"
    local_port = BASE_LOCAL_PORT + int(instance_id)

    logger.info(f"🌀 Creando túnel para {token}")
    logger.info(f"   Worker IP: {worker_ip} | VNC port: {vnc_port} | Local port: {local_port}")

    # 1️⃣ Crear o reutilizar el túnel SSH
    try:
        # Chequear si ya hay un túnel abierto para ese puerto
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
        logger.error("❌ Comando 'ssh' no encontrado — instala openssh-client en la imagen de Flask.")
        raise

    # 2️⃣ Actualizar archivo de tokens (para noVNC)
    try:
        lines = []
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, "r") as f:
                for line in f:
                    if not line.startswith(token + " "):
                        lines.append(line.strip())

        lines = [line for line in lines if not line.startswith(token + ":")]
        lines.append(f"{token}: web_app:{local_port}")

        os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)
        with open(TOKENS_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")

        logger.info(f"✅ Token registrado en {TOKENS_FILE}: {token} → 127.0.0.1:{local_port}")
    except Exception as e:
        logger.error(f"❌ Error escribiendo token: {e}")
        raise

    # 3️⃣ Generar URL para el navegador
    headnode_ip = "127.0.0.1"
    novnc_url = (
        f"http://{headnode_ip}:6080/vnc.html"
        f"?path=websockify?token={token}"
        f"&autoconnect=true&resize=scale&reconnect=true"
    )

    logger.info(f"🌐 URL generada: {novnc_url}")
    return novnc_url
