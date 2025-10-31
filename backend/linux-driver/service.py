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
    worker = data.get("worker")  # IP del worker
    vlans = data.get("vlans", [])
    puerto_vnc = str(data.get("puerto_vnc"))
    imagen = data.get("imagen", "cirros-base.qcow2")
    ram_mb = str(data.get("ram_mb", 512))
    cpus = str(data.get("cpus", 1))
    disco_gb = str(data.get("disco_gb", 2))

    # Validaciones mejoradas
    if not all([nombre_vm, worker, puerto_vnc]):
        return {"success": False, "error": "Faltan parámetros obligatorios: nombre_vm, worker, puerto_vnc"}
    
    if not vlans:
        return {"success": False, "error": "No se especificaron VLANs"}

    vlan_args = " ".join(vlans)

    # --- Comando remoto ejecutado en el worker ---
    cmd = (
        f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER}@{worker} "
        f"\"sudo /home/ubuntu/vm_create.sh {nombre_vm} {OVS_BRIDGE} {puerto_vnc} {imagen} {ram_mb} {cpus} {disco_gb} {vlan_args}\""
    )

    print(f"[DEBUG] Ejecutando comando SSH:")
    print(f"[DEBUG] {cmd}")

    # --- Ejecutar comando ---
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    pid = None

    print(f"[DEBUG] Return code: {result.returncode}")
    print(f"[DEBUG] STDOUT: {result.stdout}")
    print(f"[DEBUG] STDERR: {result.stderr}")

    # --- Analizar resultado ---
    if result.returncode == 0:
        # Buscar PID en la salida
        for line in result.stdout.splitlines():
            if line.strip().isdigit():
                pid = int(line.strip())
                break
        
        return {
            "success": True,
            "status": True,
            "pid": pid,
            "message": f"VM {nombre_vm} desplegada correctamente en {worker}",
            "stdout": result.stdout.strip(),
            "comando_ejecutado": cmd
        }
    else:
        return {
            "success": False,
            "status": False,
            "pid": pid,
            "message": f"Falló el despliegue de {nombre_vm} en {worker}",
            "error": result.stderr.strip(),
            "stdout": result.stdout.strip(),
            "comando_ejecutado": cmd
        }

@app.post("/delete_vm")
async def delete_vm(request: Request):
    """
    Elimina una VM del worker especificado
    Parámetros esperados:
    - nombre_vm: nombre de la VM
    - worker_ip: IP del worker donde está la VM
    - process_id: PID del proceso QEMU (opcional)
    - interfaces_tap: lista de interfaces TAP a eliminar (opcional)
    - delete_disk: si eliminar el disco o no (opcional, default: False)
    """
    data = await request.json()
    
    nombre_vm = data.get("nombre_vm")
    worker_ip = data.get("worker_ip") or data.get("worker")  # Acepta ambos nombres
    process_id = data.get("process_id")
    interfaces_tap = data.get("interfaces_tap", [])
    delete_disk = data.get("delete_disk", False)
    
    # Validación
    if not all([nombre_vm, worker_ip]):
        return {
            "success": False,
            "status": False,
            "error": "Faltan parámetros obligatorios: nombre_vm, worker_ip"
        }
    
    print(f"🗑️ Eliminando VM {nombre_vm} en worker {worker_ip}")
    print(f"   PID: {process_id}, TAPs: {interfaces_tap}, Delete disk: {delete_disk}")
    
    errores = []
    warnings = []
    
    # 1️⃣ MATAR PROCESO QEMU
    if process_id:
        kill_cmd = f"sudo kill -9 {process_id} 2>/dev/null || echo 'Proceso no encontrado'"
        cmd_ssh = (
            f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER}@{worker_ip} \"{kill_cmd}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Proceso QEMU {process_id} eliminado")
        else:
            warning = f"No se pudo eliminar proceso {process_id}"
            print(f"⚠️ {warning}")
            warnings.append(warning)
    else:
        # Buscar proceso por nombre
        find_kill = f"sudo pkill -9 -f 'qemu.*{nombre_vm}' || echo 'Proceso no encontrado'"
        cmd_ssh = (
            f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER}@{worker_ip} \"{find_kill}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        print(f"🔍 Búsqueda de proceso: {result.stdout}")
    
    # 2️⃣ ELIMINAR INTERFACES TAP
    taps_eliminadas = 0
    if interfaces_tap:
        for tap_name in interfaces_tap:
            tap_cmd = (
                f"sudo ovs-vsctl del-port {OVS_BRIDGE} {tap_name} 2>/dev/null || true; "
                f"sudo ip link delete {tap_name} 2>/dev/null || true; "
                f"echo 'TAP {tap_name} eliminada'"
            )
            cmd_ssh = (
                f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
                f"{USER}@{worker_ip} \"{tap_cmd}\""
            )
            result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
            
            if "eliminada" in result.stdout or result.returncode == 0:
                print(f"✅ Interfaz TAP {tap_name} eliminada")
                taps_eliminadas += 1
            else:
                warning = f"Error eliminando TAP {tap_name}: {result.stderr}"
                print(f"⚠️ {warning}")
                warnings.append(warning)
    else:
        # Buscar TAPs por nombre de VM
        find_taps = f"ip link show | grep '{nombre_vm}-tap' | awk '{{print $2}}' | sed 's/:$//'"
        cmd_ssh = (
            f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER}@{worker_ip} \"{find_taps}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        
        if result.stdout.strip():
            tap_names = result.stdout.strip().split('\n')
            for tap_name in tap_names:
                if tap_name:
                    tap_cmd = (
                        f"sudo ovs-vsctl del-port {OVS_BRIDGE} {tap_name} 2>/dev/null || true; "
                        f"sudo ip link delete {tap_name} 2>/dev/null || true"
                    )
                    cmd_ssh = (
                        f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
                        f"{USER}@{worker_ip} \"{tap_cmd}\""
                    )
                    subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
                    taps_eliminadas += 1
                    print(f"✅ TAP autodescubierta {tap_name} eliminada")
    
    # 3️⃣ ELIMINAR DISCO (OPCIONAL)
    disco_eliminado = False
    disco_path = f"/var/lib/libvirt/images/{nombre_vm}.qcow2"
    
    if delete_disk:
        print(f"🗑️ Eliminando disco {disco_path}...")
        delete_disk_cmd = f"sudo rm -f {disco_path} && echo 'Disco eliminado' || echo 'Disco no encontrado'"
        cmd_ssh = (
            f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER}@{worker_ip} \"{delete_disk_cmd}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        
        if "eliminado" in result.stdout:
            print(f"✅ Disco {disco_path} eliminado")
            disco_eliminado = True
        else:
            print(f"ℹ️ Disco no encontrado")
    else:
        print(f"💾 Disco preservado en {disco_path}")
    
    # 4️⃣ LIMPIAR ARCHIVO PID
    pid_file = f"/var/run/qemu-{nombre_vm}.pid"
    clean_pid_cmd = f"sudo rm -f {pid_file}"
    cmd_ssh = (
        f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER}@{worker_ip} \"{clean_pid_cmd}\""
    )
    subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
    
    # 5️⃣ VERIFICAR ELIMINACIÓN
    verify_cmd = f"pgrep -f 'qemu.*{nombre_vm}' || echo 'VM no encontrada'"
    cmd_ssh = (
        f"ssh -i {SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER}@{worker_ip} \"{verify_cmd}\""
    )
    result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
    
    vm_eliminada = "VM no encontrada" in result.stdout or result.returncode != 0
    
    # 6️⃣ CONSTRUIR RESPUESTA
    if vm_eliminada:
        message = f"VM {nombre_vm} eliminada completamente"
        if taps_eliminadas > 0:
            message += f" ({taps_eliminadas} interfaces TAP eliminadas)"
        if disco_eliminado:
            message += " [disco eliminado]"
        else:
            message += " [disco preservado]"
        
        response = {
            "success": True,
            "status": True,
            "mensaje": message,
            "message": message,
            "worker": worker_ip,
            "details": {
                "proceso_eliminado": bool(process_id),
                "taps_eliminadas": taps_eliminadas,
                "disco_eliminado": disco_eliminado,
                "disco_path": disco_path if not disco_eliminado else None
            }
        }
        
        if warnings:
            response["warnings"] = warnings
        
        print(f"✅ {message}")
        return response
    else:
        error_msg = f"La VM {nombre_vm} todavía tiene procesos activos"
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "status": False,
            "error": error_msg,
            "mensaje": error_msg,
            "warnings": warnings
        }

@app.get("/")
def root():
    return {
        "service": "Linux Driver",
        "version": "1.0",
        "status": "operational",
        "endpoints": {
            "create_vm": "/create_vm",
            "delete_vm": "/delete_vm"
        }
    }

@app.get("/health")
def health():
    from datetime import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }