from fastapi import FastAPI, Request
import subprocess
import json

app = FastAPI(
    title="Linux Driver",
    version="1.0.0",
    description="Orquestador local para creación de VMs en workers vía SSH"
)

# --- Configuración base ---
SSH_KEY = "/home/ubuntu/.ssh/id_rsa_orch"
USER = "ubuntu"
OVS_BRIDGE = "br-int"  # Bridge fijo

@app.post("/create_vm")
async def create_vm(request: Request):
    data = await request.json()

    # --- Parámetros desde JSON ---
    nombre_vm = data.get("nombre_vm")
    worker = data.get("worker")
    vlans = data.get("vlans", [])
    puerto_vnc = str(data.get("puerto_vnc"))
    imagen = data.get("imagen", "cirros-base.qcow2")
    ram = str(data.get("ram_mb", 512))
    cpus = str(data.get("cpus", 1))
    disco = str(data.get("disco_gb", 2))

    # Validaciones
    if not all([nombre_vm, worker, puerto_vnc]):
        return {"success": False, "error": "Faltan parámetros obligatorios"}
    if not vlans:
        return {"success": False, "error": "No se especificaron VLANs"}

    vlan_args = " ".join(vlans)

    # --- Comando remoto ejecutado en el worker ---
    cmd = (
        f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER}@{worker} "
        f"\"sudo /home/ubuntu/vm_create.sh {nombre_vm} {OVS_BRIDGE} {puerto_vnc} {imagen} {ram} {cpus} {disco} {vlan_args}\""
    )

    print(f"[DEBUG] Ejecutando comando remoto:\n{cmd}")

    # --- Ejecutar comando ---
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    pid = None

    # --- Analizar resultado ---
    if result.returncode == 0:
        # Buscar un número de PID en la salida (última línea del script)
        for line in result.stdout.splitlines():
            if line.strip().isdigit():
                pid = int(line.strip())
                break
        return {
            "status": True,
            "pid": pid,
            "message": f"VM {nombre_vm} desplegada correctamente en {worker}",
            "stdout": result.stdout.strip()
        }
    else:
        return {
            "status": False,
            "pid": pid,
            "message": "Falló el despliegue remoto",
            "stderr": result.stderr.strip(),
            "stdout": result.stdout.strip()
        }

@app.post("/delete_vm")
async def delete_vm(request: Request):
    data = await request.json()
    nombre_vm = data.get("nombre_vm")
    worker = data.get("worker")

    if not all([nombre_vm, worker]):
        return {"success": False, "error": "Faltan parámetros obligatorios"}

    cmd = (
        f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER}@{worker} "
        f"\"sudo /home/ubuntu/vm_delete.sh {nombre_vm}\""
    )

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        return {
            "status": True,
            "message": f"VM {nombre_vm} eliminada correctamente en {worker}",
            "stdout": result.stdout.strip()
        }
    else:
        return {
            "status": False,
            "message": f"Error al eliminar VM {nombre_vm} en {worker}",
            "stderr": result.stderr.strip(),
            "stdout": result.stdout.strip()
        }