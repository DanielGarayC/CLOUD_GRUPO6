#!/usr/bin/env python3
import json
import sys
import subprocess

# ===========================
# Cargar argumentos del driver
# ===========================
try:
    data = json.loads(sys.argv[1])
except Exception as e:
    print(json.dumps({"success": False, "error": f"JSON inválido: {e}"}))
    sys.exit(1)

nombre_vm = data.get("nombre_vm")
worker = data.get("worker")
vlans = data.get("vlans", [])
puerto_vnc = data.get("puerto_vnc")
imagen = data.get("imagen")
ram_mb = data.get("ram_mb")
cpus = data.get("cpus")
disco_gb = data.get("disco_gb")

# --- Configuración desde Variables de Entorno ---
SSH_KEY_WORKER = "/home/ubuntu/.ssh/id_rsa_orch"
USER_WORKER = "ubuntu"
OVS_BRIDGE = "br-int"

# ===========================
# Comando remoto vm_create.sh
# ===========================
vlan_args = " ".join(vlans)

remote_cmd = (
    f"sudo /home/ubuntu/vm_create.sh "
    f"{nombre_vm} {OVS_BRIDGE} {puerto_vnc} {imagen} "
    f"{ram_mb} {cpus} {disco_gb} {vlan_args}"
)

ssh_cmd = (
    f"ssh -i {SSH_KEY_WORKER} -o BatchMode=yes -o StrictHostKeyChecking=no "
    f"{USER_WORKER}@{worker} \"{remote_cmd}\""
)

# ===========================
# Ejecutar en worker
# ===========================
result = subprocess.run(
    ssh_cmd,
    shell=True,
    capture_output=True,
    text=True
)

stdout = result.stdout.strip()
stderr = result.stderr.strip()

# ===========================
# Error SSH
# ===========================
if result.returncode != 0:
    print(json.dumps({
        "success": False,
        "error": f"Error ejecutando en worker {worker}: {stderr or stdout}"
    }))
    sys.exit(0)

# ===========================
# Extraer PID
# ===========================
pid = None
for line in stdout.splitlines():
    if line.strip().isdigit():
        pid = int(line.strip())
        break

# ===========================
# Respuesta JSON final
# ===========================
print(json.dumps({
    "success": True,
    "pid": pid,
    "worker": worker,
    "stdout": stdout
}))