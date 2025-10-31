#Pronto con Kafka :'v
import os, json, time
from kafka import KafkaConsumer, KafkaProducer
from pydantic import BaseModel
from typing import List, Optional

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC     = os.getenv("KAFKA_TOPIC", "slice.driver.linux")
GROUP     = os.getenv("KAFKA_GROUP", "linux-driver-group")

time.sleep(3)

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=BOOTSTRAP,
    group_id=GROUP,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else None,
    key_deserializer=lambda k: k.decode("utf-8") if k else None
)

producer_events = KafkaProducer(
    bootstrap_servers=BOOTSTRAP,
    value_serializer=lambda v: v.encode("utf-8"),   # str -> bytes
    key_serializer=lambda k: k.encode("utf-8")
)


print(f"Linux Driver: escuchando {TOPIC} ...")
for msg in consumer:
    slice_id = msg.key or "no-key"
    print(f"[LINUX] key={msg.key} value={msg.value}")
    # Publicar un evento mínimo (solo para probar conectividad)
    producer_events.send("slice.events", key=slice_id, value="RECEIVED")
    producer_events.flush()

class DeleteVMRequest(BaseModel):
    nombre_vm: str
    worker_ip: str
    vm_id: int
    vnc_puerto: Optional[str] = None
    process_id: Optional[int] = None
    interfaces_tap: List[str] = []

def ejecutar_ssh(worker_ip: str, comando: str, timeout: int = 60):
    """
    Ejecuta un comando SSH en el worker remoto
    """
    import subprocess
    
    ssh_command = f"ssh -o StrictHostKeyChecking=no root@{worker_ip} '{comando}'"
    
    try:
        print(f"SSH a {worker_ip}: {comando[:100]}...")
        
        result = subprocess.run(
            ssh_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
        
    except subprocess.TimeoutExpired:
        print(f"Timeout ejecutando comando SSH en {worker_ip}")
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "Timeout",
            "success": False
        }
    except Exception as e:
        print(f"Error SSH en {worker_ip}: {e}")
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "success": False
        }

@app.post("/delete_vm")
def delete_vm(vm_data: DeleteVMRequest):
    """
    Elimina una VM del worker especificado
    Elimina: proceso QEMU, interfaces TAP, disco y archivos PID
    """
    print(f"Eliminando VM {vm_data.nombre_vm} en worker {vm_data.worker_ip}")
    
    try:
        errores = []
        warnings = []
        
        if vm_data.process_id:
            kill_cmd = f"kill -9 {vm_data.process_id} 2>/dev/null || true"
            result = ejecutar_ssh(vm_data.worker_ip, kill_cmd, timeout=10)
            
            if result["success"]:
                print(f"Proceso QEMU {vm_data.process_id} eliminado")
            else:
                warning_msg = f"No se pudo eliminar proceso {vm_data.process_id}"
                print(f"{warning_msg}")
                warnings.append(warning_msg)
        else:
            # Buscar proceso por nombre si no hay PID
            find_kill_cmd = f"""
                PID=$(pgrep -f "qemu.*{vm_data.nombre_vm}" | head -n 1)
                if [ -n "$PID" ]; then
                    kill -9 $PID && echo "Proceso $PID eliminado"
                else
                    echo "Proceso no encontrado"
                fi
            """
            result = ejecutar_ssh(vm_data.worker_ip, find_kill_cmd, timeout=10)
            print(f"Búsqueda de proceso: {result['stdout']}")
        
        taps_eliminadas = 0
        if vm_data.interfaces_tap:
            for tap_name in vm_data.interfaces_tap:
                tap_cmd = f"""
                    ovs-vsctl del-port ovs-br0 {tap_name} 2>/dev/null || true
                    ip link delete {tap_name} 2>/dev/null || true
                    echo "TAP {tap_name} eliminada"
                """
                result = ejecutar_ssh(vm_data.worker_ip, tap_cmd, timeout=10)
                
                if result["success"]:
                    print(f"Interfaz TAP {tap_name} eliminada")
                    taps_eliminadas += 1
                else:
                    warning_msg = f"Error eliminando TAP {tap_name}: {result['stderr']}"
                    print(f"{warning_msg}")
                    warnings.append(warning_msg)
        else:
            find_taps_cmd = f"""
                ip link show | grep "{vm_data.nombre_vm}-tap" | awk '{{print $2}}' | sed 's/:$//'
            """
            result = ejecutar_ssh(vm_data.worker_ip, find_taps_cmd, timeout=10)
            
            if result["stdout"]:
                tap_names = result["stdout"].strip().split('\n')
                for tap_name in tap_names:
                    if tap_name:
                        tap_cmd = f"""
                            ovs-vsctl del-port ovs-br0 {tap_name} 2>/dev/null || true
                            ip link delete {tap_name} 2>/dev/null || true
                        """
                        ejecutar_ssh(vm_data.worker_ip, tap_cmd, timeout=10)
                        taps_eliminadas += 1
                        print(f" TAP autodescubierta {tap_name} eliminada")
        
       
        disco_path = f"/var/lib/qemu-images/vms-disk/{vm_data.nombre_vm}.qcow2"
        delete_disk_cmd = f"rm -f {disco_path} && echo 'Disco eliminado' || echo 'Disco no encontrado'"
        
        result = ejecutar_ssh(vm_data.worker_ip, delete_disk_cmd, timeout=10)
        if "eliminado" in result["stdout"]:
            print(f" Disco {disco_path} eliminado")
        else:
            print(f"ℹ️ Disco no encontrado o ya eliminado")
        
        
        pid_file = f"/var/run/qemu-{vm_data.nombre_vm}.pid"
        clean_pid_cmd = f"rm -f {pid_file}"
        ejecutar_ssh(vm_data.worker_ip, clean_pid_cmd, timeout=5)
        
        
        verify_cmd = f"pgrep -f 'qemu.*{vm_data.nombre_vm}' || echo 'VM no encontrada'"
        result = ejecutar_ssh(vm_data.worker_ip, verify_cmd, timeout=10)
        
        vm_eliminada = "VM no encontrada" in result["stdout"] or result["returncode"] != 0
        
        
        if vm_eliminada:
            message = f"VM {vm_data.nombre_vm} eliminada completamente"
            if taps_eliminadas > 0:
                message += f" ({taps_eliminadas} interfaces TAP eliminadas)"
            
            response = {
                "success": True,
                "status": True,
                "mensaje": message,
                "message": message,
                "worker": vm_data.worker_ip,
                "details": {
                    "proceso_eliminado": bool(vm_data.process_id),
                    "taps_eliminadas": taps_eliminadas,
                    "disco_eliminado": True
                }
            }
            
            if warnings:
                response["warnings"] = warnings
            
            print(f" {message}")
            return response
        else:
            error_msg = f"La VM {vm_data.nombre_vm} todavía tiene procesos activos"
            print(f" {error_msg}")
            return {
                "success": False,
                "status": False,
                "error": error_msg,
                "mensaje": error_msg,
                "warnings": warnings
            }
        
    except Exception as e:
        error_msg = f"Error eliminando VM {vm_data.nombre_vm}: {str(e)}"
        print(f" {error_msg}")
        return {
            "success": False,
            "status": False,
            "error": error_msg,
            "mensaje": error_msg,
            "message": error_msg
        }

@app.get("/")
def root():
    return {
        "service": "Linux Driver",
        "version": "1.0",
        "status": "operational",
        "endpoints": {
            "create_vm": "/create_vm",
            "delete_vm": "/delete_vm",
            "health": "/health"
        }
    }

@app.get("/health")
def health():
    from datetime import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }