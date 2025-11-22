from fastapi import FastAPI, Request
import subprocess
import json
import os

app = FastAPI(
    title="Hybrid Driver (Linux + OpenStack)",
    version="2.0.0",
    description="Orquestador para VMs en Linux Cluster y OpenStack"
)

# --- Configuración desde Variables de Entorno ---
SSH_KEY_LINUX = os.getenv("SSH_KEY_LINUX", "/home/ubuntu/.ssh/id_rsa_orch")
USER_LINUX = os.getenv("USER_LINUX", "ubuntu")
OVS_BRIDGE = os.getenv("OVS_BRIDGE", "br-int")

# --- Configuración OpenStack ---
SSH_KEY_OPENSTACK = os.getenv("SSH_KEY_OPENSTACK", "/home/ubuntu/.ssh/id_rsa_openstack")
USER_OPENSTACK = os.getenv("USER_OPENSTACK", "ubuntu")
OPENSTACK_HEADNODE = os.getenv("OPENSTACK_HEADNODE", "10.20.12.106")
OPENSTACK_PORT = os.getenv("OPENSTACK_PORT", "5821")
OPENSTACK_SCRIPTS_PATH = os.getenv("OPENSTACK_SCRIPTS_PATH", "/home/ubuntu/openstack-scripts")

# --- Helpers OpenStack ---
def execute_on_openstack_headnode(script_name, args_dict):
    """
    Ejecuta un script Python en el headnode de OpenStack vía SSH
    
    Args:
        script_name: Nombre del script (ej: 'deploy_vm.py')
        args_dict: Diccionario con argumentos JSON
    
    Returns:
        dict: Resultado con success, data/error
    """
    # Serializar argumentos como JSON
    args_json = json.dumps(args_dict).replace('"', '\\"')
    
    # Comando SSH para ejecutar script remoto
    cmd = (
        f"ssh -i {SSH_KEY_OPENSTACK} "
        f"-o BatchMode=yes -o StrictHostKeyChecking=no "
        f"-p {OPENSTACK_PORT} "
        f"{USER_OPENSTACK}@{OPENSTACK_HEADNODE} "
        f"\"cd {OPENSTACK_SCRIPTS_PATH} && python3 {script_name} '{args_json}'\""
    )
    
    print(f"[OPENSTACK] Ejecutando: {script_name}")
    print(f"[OPENSTACK] Comando: {cmd}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    
    print(f"[OPENSTACK] Return code: {result.returncode}")
    print(f"[OPENSTACK] STDOUT: {result.stdout}")
    print(f"[OPENSTACK] STDERR: {result.stderr}")
    
    if result.returncode == 0:
        try:
            # Intentar parsear JSON del stdout
            response_data = json.loads(result.stdout.strip().split('\n')[-1])
            return {"success": True, "data": response_data}
        except json.JSONDecodeError:
            return {
                "success": True,
                "data": {"raw_output": result.stdout.strip()}
            }
    else:
        return {
            "success": False,
            "error": result.stderr.strip() or result.stdout.strip(),
            "returncode": result.returncode
        }

# --- Endpoint Principal: Crear VM ---
@app.post("/create_vm")
async def create_vm(request: Request):
    """
    Crea una VM en Linux Cluster o OpenStack según el parámetro 'platform'
    """
    data = await request.json()
    platform = data.get("platform", "linux").lower()
    
    if platform == "openstack":
        return await create_vm_openstack(data)
    elif platform == "linux":
        return await create_vm_linux(data)
    else:
        return {
            "success": False,
            "error": f"Plataforma no soportada: {platform}. Use 'linux' o 'openstack'"
        }

# --- Implementación Linux (código original) ---
async def create_vm_linux(data):
    """Despliegue en Linux Cluster (sin cambios)"""
    nombre_vm = data.get("nombre_vm")
    worker = data.get("worker")
    vlans = data.get("vlans", [])
    puerto_vnc = str(data.get("puerto_vnc"))
    imagen = data.get("imagen", "cirros-base.qcow2")
    ram_gb = float(data.get("ram_gb", 1))
    ram_mb = str(int(ram_gb * 1024))  # GB → MB
    cpus = str(int(data.get("cpus", 1)))
    disco_gb = str(int(data.get("disco_gb", 10)))

    if not all([nombre_vm, worker, puerto_vnc]):
        return {"success": False, "error": "Faltan parámetros: nombre_vm, worker, puerto_vnc"}
    
    if not vlans:
        return {"success": False, "error": "No se especificaron VLANs"}

    vlan_args = " ".join(vlans)
    cmd = (
        f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER_LINUX}@{worker} "
        f"\"sudo /home/ubuntu/vm_create.sh {nombre_vm} {OVS_BRIDGE} {puerto_vnc} "
        f"{imagen} {ram_mb} {cpus} {disco_gb} {vlan_args}\""
    )

    print(f"[LINUX] Ejecutando: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    pid = None

    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.strip().isdigit():
                pid = int(line.strip())
                break
        
        return {
            "success": True,
            "status": True,
            "platform": "linux",
            "pid": pid,
            "message": f"VM {nombre_vm} desplegada en Linux worker {worker}",
            "stdout": result.stdout.strip()
        }
    else:
        return {
            "success": False,
            "status": False,
            "platform": "linux",
            "message": f"Falló despliegue Linux de {nombre_vm}",
            "error": result.stderr.strip()
        }

# --- Implementación OpenStack ---
async def create_vm_openstack(data):
    """
    Despliegue en OpenStack Cloud (Versión actualizada)
    
    Workflow:
    1. Recibe flavor_spec (en lugar de flavor_id fijo)
    2. Recibe redes[] (topología de red del slice)
    3. Recibe imagen_id (UUID de OpenStack)
    4. Ejecuta deploy_vm_workflow.py en headnode
    """
    nombre_vm = data.get("nombre_vm")
    vm_id = data.get("vm_id")  
    slice_id = data.get("slice_id")
    imagen_id = data.get("imagen_id")  
    flavor_spec = data.get("flavor_spec")  
    redes = data.get("redes", [])  
    salida_internet = data.get("salidainternet", False)
    
    # Validaciones
    if not all([nombre_vm, slice_id, imagen_id, flavor_spec]):
        return {
            "success": False, 
            "error": "Faltan parámetros: nombre_vm, slice_id, imagen_id, flavor_spec"
        }
    
    # Preparar argumentos para el script remoto
    deploy_args = {
        "slice_id": slice_id,
        "vm_name": nombre_vm,
        "vm_id": vm_id,
        "imagen_id": imagen_id,  #UUID de Glance
        "flavor_spec": flavor_spec,  # {cpus, ram_gb, disk_gb, nombre}
        "redes": redes,  #Lista de redes a crear
        "salidainternet": salida_internet
    }
    
    print(f"[OPENSTACK] Desplegando VM {nombre_vm}...")
    print(f"[OPENSTACK]   Imagen: {imagen_id}")
    print(f"[OPENSTACK]   Flavor: {flavor_spec.get('nombre', 'custom')}")
    print(f"[OPENSTACK]   Redes: {len(redes)}")
    
    # Ejecutar script de despliegue en headnode
    result = execute_on_openstack_headnode("deploy_vm_workflow.py", deploy_args)
    
    if result["success"]:
        vm_info = result["data"]
        
        #VERIFICAR QUE EL DESPLIEGUE FUE EXITOSO
        if not vm_info.get("success"):
            return {
                "success": False,
                "status": False,
                "platform": "openstack",
                "message": f"Falló despliegue OpenStack de {nombre_vm}",
                "error": vm_info.get("error", "Error desconocido")
            }
        
        return {
            "success": True,
            "status": True,
            "platform": "openstack",
            "message": f"VM {nombre_vm} desplegada en OpenStack",
            "instance_id": vm_info.get("instance_id"),
            "console_url": vm_info.get("console_url"),
            "networks": vm_info.get("networks", []),
            "ports": vm_info.get("ports", []),
            "flavor_id": vm_info.get("flavor_id"),
            "flavor_created": vm_info.get("flavor_created", False)
        }
    else:
        return {
            "success": False,
            "status": False,
            "platform": "openstack",
            "message": f"Falló comunicación con headnode para {nombre_vm}",
            "error": result["error"]
        }

# --- Endpoint: Eliminar VM ---
@app.post("/delete_vm")
async def delete_vm(request: Request):
    """Elimina VM de Linux Cluster o OpenStack"""
    data = await request.json()
    platform = data.get("platform", "linux").lower()
    
    if platform == "openstack":
        return await delete_vm_openstack(data)
    elif platform == "linux":
        return await delete_vm_linux(data)
    else:
        return {"success": False, "error": f"Plataforma no soportada: {platform}"}

async def delete_vm_linux(data):
    """Eliminación en Linux (código corregido con búsqueda automática de TAPs)"""
    nombre_vm = data.get("nombre_vm")
    worker_ip = data.get("worker_ip") or data.get("worker")
    process_id = data.get("process_id")
    interfaces_tap = data.get("interfaces_tap", [])
    delete_disk = data.get("delete_disk", False)
    
    if not all([nombre_vm, worker_ip]):
        return {
            "success": False,
            "error": "Faltan parámetros: nombre_vm, worker_ip"
        }
    
    print(f"[LINUX] Eliminando VM {nombre_vm} en {worker_ip}")
    warnings = []
    proceso_eliminado = False
    
    # 1. Matar proceso QEMU
    if process_id:
        kill_cmd = f"sudo kill -9 {process_id} 2>&1"
        cmd_ssh = (
            f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER_LINUX}@{worker_ip} \"{kill_cmd}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0 or "No such process" in result.stderr:
            proceso_eliminado = True
        else:
            warnings.append(f"Error matando PID {process_id}: {result.stderr}")
    else:
        find_kill = f"sudo pkill -9 -f 'qemu.*{nombre_vm}' 2>&1; echo $?"
        cmd_ssh = (
            f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER_LINUX}@{worker_ip} \"{find_kill}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        exit_code = result.stdout.strip().split('\n')[-1]
        
        if exit_code == "0":
            proceso_eliminado = True
        else:
            warnings.append(f"No se encontró proceso QEMU para {nombre_vm}")
    
    # Esperar a que el proceso termine
    if proceso_eliminado:
        import time
        time.sleep(1)
    
    # 2. Eliminar interfaces TAP (CORREGIDO)
    taps_eliminadas = 0
    
    if interfaces_tap:
        # Si se proporcionaron TAPs específicas, eliminarlas
        print(f"[LINUX] Eliminando {len(interfaces_tap)} interfaces TAP proporcionadas...")
        for tap_name in interfaces_tap:
            tap_cmd = (
                f"sudo ovs-vsctl --if-exists del-port {OVS_BRIDGE} {tap_name}; "
                f"sudo ip link delete {tap_name} 2>/dev/null || true; "
                f"echo 'OK'"
            )
            cmd_ssh = (
                f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
                f"{USER_LINUX}@{worker_ip} \"{tap_cmd}\""
            )
            result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"[LINUX] Interfaz TAP {tap_name} eliminada")
                taps_eliminadas += 1
            else:
                warning = f"Error eliminando TAP {tap_name}: {result.stderr}"
                warnings.append(warning)
    else:
        # Si no se proporcionaron TAPs, buscarlas automáticamente
        print(f"[LINUX] Buscando interfaces TAP automáticamente para '{nombre_vm}'...")
        find_taps = f"ip link show | grep -oP '{nombre_vm}-tap[0-9]+' || true"
        cmd_ssh = (
            f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER_LINUX}@{worker_ip} \"{find_taps}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        
        if result.stdout.strip():
            tap_names = result.stdout.strip().split('\n')
            print(f"[LINUX] TAPs encontradas: {tap_names}")
            
            for tap_name in tap_names:
                if tap_name:
                    tap_cmd = (
                        f"sudo ovs-vsctl --if-exists del-port {OVS_BRIDGE} {tap_name}; "
                        f"sudo ip link delete {tap_name} 2>/dev/null || true"
                    )
                    cmd_ssh = (
                        f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
                        f"{USER_LINUX}@{worker_ip} \"{tap_cmd}\""
                    )
                    subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
                    taps_eliminadas += 1
                    print(f"[LINUX] TAP autodescubierta {tap_name} eliminada")
        else:
            print(f"[LINUX] No se encontraron TAPs para {nombre_vm}")
    
    # 3. Eliminar disco
    disco_eliminado = False
    disco_path = f"/var/lib/qemu-images/vms-disk/{nombre_vm}.qcow2"
    if delete_disk or 1==1:
        delete_disk_cmd = f"sudo rm -f {disco_path} && echo 'OK' || echo 'FAIL'"
        cmd_ssh = (
            f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
            f"{USER_LINUX}@{worker_ip} \"{delete_disk_cmd}\""
        )
        result = subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
        disco_eliminado = "OK" in result.stdout
    
    # 4. Limpiar archivo PID
    pid_file = f"/var/run/{nombre_vm}.pid"
    clean_pid_cmd = f"sudo rm -f {pid_file}"
    cmd_ssh = (
        f"ssh -i {SSH_KEY_LINUX} -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{USER_LINUX}@{worker_ip} \"{clean_pid_cmd}\""
    )
    subprocess.run(cmd_ssh, shell=True, capture_output=True, text=True)
    
    # Preparar mensaje de respuesta
    message = f"VM {nombre_vm} eliminada de Linux worker"
    if taps_eliminadas > 0:
        message += f" ({taps_eliminadas} interfaces TAP eliminadas)"
    if disco_eliminado:
        message += " [disco eliminado]"
    
    return {
        "success": True,
        "status": True,
        "platform": "linux",
        "mensaje": message,
        "details": {
            "proceso_eliminado": proceso_eliminado,
            "taps_eliminadas": taps_eliminadas,
            "disco_eliminado": disco_eliminado
        },
        "warnings": warnings if warnings else None
    }

async def delete_vm_openstack(data):
    """Eliminación en OpenStack"""
    nombre_vm = data.get("nombre_vm")
    instance_id = data.get("instance_id")
    slice_id = data.get("slice_id")
    
    if not instance_id:
        return {"success": False, "error": "Falta parámetro: instance_id"}
    
    delete_args = {
        "action": "delete_vm",
        "instance_id": instance_id,
        "slice_id": slice_id
    }
    
    result = execute_on_openstack_headnode("delete_vm_workflow.py", delete_args)
    
    if result["success"]:
        return {
            "success": True,
            "status": True,
            "platform": "openstack",
            "mensaje": f"VM {nombre_vm} eliminada de OpenStack",
            "details": result["data"]
        }
    else:
        return {
            "success": False,
            "platform": "openstack",
            "error": result["error"]
        }

# --- Endpoints informativos ---
@app.get("/")
def root():
    return {
        "service": "Hybrid Driver (Linux + OpenStack)",
        "version": "2.0",
        "status": "operational",
        "supported_platforms": ["linux", "openstack"],
        "endpoints": {
            "create_vm": "/create_vm",
            "delete_vm": "/delete_vm",
            "health": "/health"
        },
        "openstack_config": {
            "headnode": f"{OPENSTACK_HEADNODE}:{OPENSTACK_PORT}",
            "scripts_path": OPENSTACK_SCRIPTS_PATH
        }
    }

@app.get("/health")
def health():
    """Health check con conectividad OpenStack"""
    from datetime import datetime
    
    # Verificar conectividad con OpenStack headnode
    openstack_reachable = False
    try:
        test_cmd = (
            f"ssh -i {SSH_KEY_OPENSTACK} "
            f"-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 "
            f"-p {OPENSTACK_PORT} "
            f"{USER_OPENSTACK}@{OPENSTACK_HEADNODE} 'echo OK'"
        )
        result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True, timeout=10)
        openstack_reachable = result.returncode == 0 and "OK" in result.stdout
    except Exception as e:
        print(f"[HEALTH] Error verificando OpenStack: {e}")
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "platforms": {
            "linux": "operational",
            "openstack": "operational" if openstack_reachable else "unreachable"
        }
    }