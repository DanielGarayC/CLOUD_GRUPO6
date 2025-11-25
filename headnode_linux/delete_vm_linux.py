#!/usr/bin/env python3
import json
import sys
import subprocess
import time

# ===========================================================
# Cargar argumentos del Hybrid Driver
# ===========================================================
try:
    data = json.loads(sys.argv[1])
except Exception as e:
    print(json.dumps({"success": False, "error": f"JSON inválido: {e}"}))
    sys.exit(1)

nombre_vm = data.get("nombre_vm")
worker = data.get("worker")
process_id = data.get("process_id")
interfaces_tap = data.get("interfaces_tap", [])
delete_disk = data.get("delete_disk", False)

# ===========================================================
# Configuración interna del Headnode
# ===========================================================
# --- Configuración desde Variables de Entorno ---
SSH_KEY_WORKER = "/home/ubuntu/.ssh/id_rsa_orch"
USER_WORKER = "ubuntu"
OVS_BRIDGE = "br-int"

# ===========================================================
# Helper para ejecutar comandos en el worker
# ===========================================================
def run_worker(cmd):
    ssh_cmd = (
        f"ssh -i {SSH_KEY_WORKER} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER_WORKER}@{worker} \"{cmd}\""
    )
    result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

warnings = []
taps_eliminadas = 0
proceso_eliminado = False

# ===========================================================
# 1. Matar proceso QEMU
# ===========================================================
if process_id:
    kill_cmd = f"sudo kill -9 {process_id} 2>&1"
    _, stderr, rc = run_worker(kill_cmd)
    if rc == 0 or "No such process" in stderr:
        proceso_eliminado = True
    else:
        warnings.append(f"Error matando PID {process_id}: {stderr}")
else:
    find_kill = (
        f"sudo pkill -9 -f 'qemu.*{nombre_vm}' 2>&1; echo $? "
    )
    stdout, _, _ = run_worker(find_kill)
    exit_code = stdout.split("\n")[-1]
    if exit_code == "0":
        proceso_eliminado = True
    else:
        warnings.append(f"No se encontró proceso QEMU para {nombre_vm}")

if proceso_eliminado:
    time.sleep(1)

# ===========================================================
# 2. Eliminar TAPs
# ===========================================================
if interfaces_tap:
    # TAPs proporcionadas explícitamente
    for tap in interfaces_tap:
        delete_cmd = (
            f"sudo ovs-vsctl --if-exists del-port {OVS_BRIDGE} {tap}; "
            f"sudo ip link delete {tap} 2>/dev/null || true"
        )
        _, _, _ = run_worker(delete_cmd)
        taps_eliminadas += 1
else:
    # Búsqueda automática
    find_cmd = f"ip link show | grep -oP '{nombre_vm}-tap[0-9]+' || true"
    stdout, _, _ = run_worker(find_cmd)
    if stdout.strip():
        tap_list = stdout.strip().split("\n")
        for tap in tap_list:
            if tap:
                delete_cmd = (
                    f"sudo ovs-vsctl --if-exists del-port {OVS_BRIDGE} {tap}; "
                    f"sudo ip link delete {tap} 2>/dev/null || true"
                )
                run_worker(delete_cmd)
                taps_eliminadas += 1

# ===========================================================
# 3. Eliminar disco QCOW2 (opcional)
# ===========================================================
disco_eliminado = False
if delete_disk:
    disk_path = f"/var/lib/qemu-images/vms-disk/{nombre_vm}.qcow2"
    delete_cmd = f"sudo rm -f {disk_path} && echo OK || echo FAIL"
    stdout, _, _ = run_worker(delete_cmd)
    disco_eliminado = "OK" in stdout

# ===========================================================
# Respuesta final al driver
# ===========================================================
response = {
    "success": True,
    "mensaje": f"VM {nombre_vm} eliminada",
    "details": {
        "proceso_eliminado": proceso_eliminado,
        "taps_eliminadas": taps_eliminadas,
        "disco_eliminado": disco_eliminado
    }
}

if warnings:
    response["warnings"] = warnings

print(json.dumps(response))