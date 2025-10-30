from fastapi import FastAPI, Body
from datetime import datetime
from sqlalchemy import create_engine, text
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, json, os

app = FastAPI(title="Slice Manager", version="3.0")

# ======================================
# CONFIGURACIÓN BASE DE DATOS Y MONITOREO
# ======================================
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "root")
DB_HOST = os.getenv("DB_HOST", "slice_db")
DB_NAME = os.getenv("DB_NAME", "mydb")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

# Servicio de monitoreo en el headnode
MONITORING_URL = "http://monitoring_service:5010/metrics"
NETWORK_BASE = "http://network_manager:8100"

# Mapeo estático de workers
WORKER_IPS = {
    "server2": "192.168.201.2",
    "server3": "192.168.201.3",
    "server4": "192.168.201.4"
}


# ======================================
# FUNCIÓN: obtener métricas del monitoreo
# ======================================
def obtener_metricas_actuales():
    try:
        resp = requests.get(MONITORING_URL, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"⚠️ Error {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        print(f"❌ No se pudo conectar con el servicio de monitoreo: {e}")
        return None


# ======================================
# FUNCIÓN: obtener instancias de la BD
# ======================================
def obtener_instancias_por_slice(id_slice: int):
    query = text("""
        SELECT i.idinstancia, i.nombre, i.cpu, i.ram, i.storage, i.salidainternet, im.ruta AS imagen
        FROM instancia i
        JOIN imagen im ON i.imagen_idimagen = im.idimagen
        WHERE i.slice_idslice = :id_slice
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"id_slice": id_slice})
        return [dict(row._mapping) for row in result]

# Leer enlaces
def obtener_enlaces_por_slice(id_slice: int):
    query = text("""
        SELECT 
            e.idenlace, 
            e.vm1, 
            e.vm2, 
            e.vlan_idvlan, 
            e.vlan,
            v.numero
        FROM 
            enlace e
        LEFT JOIN 
            vlan v ON e.vlan_idvlan = v.idvlan
        WHERE 
            e.slice_idslice = :id_slice
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"id_slice": id_slice})
        return [dict(row._mapping) for row in result]

def asignar_vlans_a_enlaces(id_slice: int):
    """
    Revisa los enlaces del slice y asigna VLANs nuevas si no tienen ninguna.
    Devuelve la lista de enlaces actualizada.
    """
    # 🟢 USAR LA FUNCIÓN CORREGIDA
    enlaces = obtener_enlaces_por_slice(id_slice)
    print(f"📊 Enlaces encontrados: {len(enlaces)}")
    
    for e in enlaces:
        print(f"🔗 Enlace {e['idenlace']}: VM{e['vm1']} ↔ VM{e['vm2']} | VLAN: {e['vlan_idvlan']}")
        
        if e["vlan_idvlan"] is None:
            vlan_info = solicitar_vlan()
            if vlan_info and vlan_info.get("idvlan"):
                idvlan = vlan_info["idvlan"]
                numero_vlan = vlan_info.get("numero", str(idvlan))
                
                # 🟢 ACTUALIZAR TANTO vlan_idvlan COMO vlan
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE enlace
                        SET vlan_idvlan = :idvlan, vlan = :numero_vlan
                        WHERE idenlace = :idenlace
                    """), {
                        "idvlan": idvlan, 
                        "numero_vlan": numero_vlan,
                        "idenlace": e["idenlace"]
                    })
                
                # Actualizar en memoria
                e["vlan_idvlan"] = idvlan
                e["numero"] = numero_vlan
                print(f"✅ Enlace {e['idenlace']} → VLAN {numero_vlan} (ID:{idvlan}) asignada")
            else:
                print(f"⚠️ No se pudo asignar VLAN al enlace {e['idenlace']}")
    
    return enlaces

# ======================================
# FUNCIÓN: generar plan de despliegue
# ======================================
def generar_plan_deploy(id_slice: int,metrics_json: dict, instancias: list):
    metrics = metrics_json.get("metrics", {})
    workers = []

    # Obtener recursos libres por worker
    for host, data in metrics.items():
        cpu_total = data.get("cpu_count", 1)
        ram_total = data.get("ram_total_gb", 1)
        cpu_free = cpu_total * (1 - data.get("cpu_percent", 0) / 100)
        ram_free = ram_total * (1 - data.get("ram_percent", 0) / 100)
        workers.append({
            "nombre": host,
            "ip": WORKER_IPS.get(host, "0.0.0.0"),
            "cpu_free": round(cpu_free, 2),
            "ram_free": round(ram_free, 2)
        })

    if not workers:
        return {"can_deploy": False, "error": "No hay workers válidos."}

    workers.sort(key=lambda w: w["nombre"])

 
    # 🟢 OBTENER ENLACES Y ASIGNAR VLANS
    print(f"🔍 Obteniendo enlaces para slice {id_slice}...")
    enlaces = asignar_vlans_a_enlaces(id_slice)
    
    # 🟢 CREAR MAPA DE VLANS POR VM
    vlans_por_vm = {}
    for enlace in enlaces:
        vm1 = str(enlace["vm1"])  # Convertir a string para comparación
        vm2 = str(enlace["vm2"])
        vlan_numero = enlace.get("numero")
        
        if vlan_numero:  # Solo si tiene VLAN asignada
            if vm1 not in vlans_por_vm:
                vlans_por_vm[vm1] = []
            if vm2 not in vlans_por_vm:
                vlans_por_vm[vm2] = []
            
            vlans_por_vm[vm1].append(vlan_numero)
            vlans_por_vm[vm2].append(vlan_numero)
    
    print(f"📋 Mapa de VLANs por VM: {vlans_por_vm}")
    
    # Asignación Round-Robin
    plan = []
    idx = 0
    
    for vm in instancias:
        w = workers[idx]
        ram_value = float(str(vm["ram"]).replace("GB", "").strip())
        storage_value = float(str(vm["storage"]).replace("GB", "").strip())
        
        # 🟢 OBTENER VLANS DE ESTA VM
        vm_id = str(vm["idinstancia"])
        vlans_vm = list(set(vlans_por_vm.get(vm_id, [])))  # Eliminar duplicados
        
        # Si la VM tiene salida a internet, agregar VLAN de internet
        if vm.get("salidainternet"):
            vlan_int = solicitar_vlan_internet()
            if vlan_int and vlan_int.get("numero"):
                vlan_internet_num = vlan_int["numero"]
                # Ponerla al inicio para que quede como eth0
                vlans_vm = [vlan_internet_num] + [v for v in vlans_vm if v != vlan_internet_num]
        
        # Solicitar VNC
        vnc_info = solicitar_vnc()
        puerto_vnc = vnc_info.get("puerto") if vnc_info else None
        
        plan.append({
            "nombre_vm": vm["nombre"],
            "worker": w["ip"],
            "vlans": vlans_vm,  
            "puerto_vnc": puerto_vnc,
            "imagen": vm["imagen"],
            "ram_gb": ram_value,
            "cpus": int(vm["cpu"]),
            "disco_gb": storage_value,
        })
        
        # Descontar recursos simulados
        w["cpu_free"] -= int(vm["cpu"])
        w["ram_free"] -= ram_value
        idx = (idx + 1) % len(workers)
    
    puede = all(w["cpu_free"] >= 0 and w["ram_free"] >= 0 for w in workers)
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "can_deploy": puede,
        "placement_plan": plan,
        "workers_status": workers
    }

#Funciones para conexiones con Network Manager
def solicitar_vlan():
    """Solicita una VLAN normal"""
    try:
        resp = requests.post(f"{NETWORK_BASE}/vlans/asignar", timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"⚠️ Error al asignar VLAN: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"❌ No se pudo conectar con Network Manager: {e}")
        return None


def solicitar_vlan_internet():
    """Solicita una VLAN para salida a internet"""
    try:
        resp = requests.get(f"{NETWORK_BASE}/vlans/internet", timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"⚠️ Error al solicitar VLAN de Internet: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"❌ No se pudo conectar con Network Manager: {e}")
        return None


def solicitar_vnc():
    """Solicita un puerto VNC"""
    try:
        resp = requests.post(f"{NETWORK_BASE}/vncs/asignar", timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"⚠️ Error al asignar VNC: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"❌ No se pudo conectar con Network Manager: {e}")
        return None


#Despliegue :D
def desplegar_vm_en_worker(vm_data: dict):
    """Envía la petición al Linux Driver con formato correcto y logs detallados."""
    LINUX_DRIVER_URL = os.getenv("LINUX_DRIVER_URL", "http://linux-driver:9100")
    url = f"{LINUX_DRIVER_URL}/create_vm"

    try:
        print(f"[HTTP] → POST {url}")
        print(f"[HTTP] VM: {vm_data['nombre_vm']} → Worker: {vm_data['worker']}")

        # 🟢 TRANSFORMAR DATOS AL FORMATO CORRECTO
        transformed_payload = {
            "nombre_vm": vm_data["nombre_vm"],
            "worker": vm_data["worker"],
            "vlans": [str(v) for v in vm_data["vlans"]],
            "puerto_vnc": str(vm_data["puerto_vnc"]),
            "imagen": vm_data["imagen"],
            "ram_mb": int(vm_data["ram_gb"] * 1024),  # GB → MB
            "cpus": int(vm_data["cpus"]),
            "disco_gb": int(vm_data["disco_gb"])
        }
        
        print(f"[HTTP] Payload: RAM={transformed_payload['ram_mb']}MB, CPUs={transformed_payload['cpus']}, VLANs={transformed_payload['vlans']}")

        resp = requests.post(url, json=transformed_payload, timeout=200)
        raw = resp.text
        
        print(f"[HTTP] ← {resp.status_code}")
        print(f"[HTTP] Response: {raw[:300]}...")

        if resp.status_code != 200:
            return {
                "status": False, 
                "message": f"HTTP {resp.status_code}: {raw[:200]}", 
                "raw": raw
            }

        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            return {
                "status": False, 
                "message": f"Respuesta no es JSON válido: {raw[:200]}", 
                "raw": raw
            }

        # 🟢 VERIFICAR AMBOS CAMPOS DE SUCCESS
        success = bool(data.get("success", data.get("status", False)))
        message = data.get("message") or data.get("mensaje") or data.get("stdout") or "VM procesada"
        pid = data.get("pid")
        
        if success:
            print(f"[SUCCESS] VM {vm_data['nombre_vm']} desplegada - PID: {pid}")
        else:
            print(f"[FAILED] VM {vm_data['nombre_vm']} falló: {message}")
            print(f"[ERROR] STDERR: {data.get('stderr', 'N/A')}")
        
        return {
            "status": success,
            "message": message,
            "pid": pid,
            "raw": data,
            "comando_ssh": data.get("comando_ejecutado", "N/A")  # Para debug
        }

    except requests.exceptions.Timeout:
        error_msg = f"Timeout desplegando VM {vm_data['nombre_vm']} en {vm_data['worker']}"
        print(f"[TIMEOUT] {error_msg}")
        return {"status": False, "message": error_msg}
        
    except Exception as e:
        error_msg = f"Error de conexión con Linux Driver: {e}"
        print(f"[ERROR] {error_msg}")
        return {"status": False, "message": error_msg}


# ======================================
# ENDPOINT: verificar viabilidad
# ======================================
@app.post("/placement/verify")
def verificar_viabilidad_endpoint(data: dict = Body(...)):
    id_slice = data.get("id_slice")
    if not id_slice:
        return {"error": "Falta el parámetro 'id_slice'"}

    print(f"🛰️ Evaluando slice {id_slice}...")

    instancias = obtener_instancias_por_slice(id_slice)
    if not instancias:
        return {"can_deploy": False, "error": "No se encontraron instancias para el slice."}

    metrics = obtener_metricas_actuales()
    if not metrics:
        return {"can_deploy": False, "error": "No se pudo obtener métricas de los workers."}

    resultado = generar_plan_deploy(id_slice, metrics, instancias)
    print(json.dumps(resultado, indent=2))
    return resultado

# ======================================
# ENDPOINT raíz
# ======================================
@app.get("/")
def root():
    return {"status": "ok", "message": "Slice Manager operativo en el Headnode"}


#ga
@app.post("/placement/deploy")
def deploy_slice(data: dict = Body(...)):
    id_slice = data.get("id_slice")
    if not id_slice:
        return {"error": "Falta el parámetro 'id_slice'"}

    print(f"🚀 Iniciando despliegue real del slice {id_slice}...")

    # 🟡 Estado inicial del slice
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE slice 
            SET estado = 'DEPLOYING'
            WHERE idslice = :sid
        """), {"sid": id_slice})

    try:
        # 1️⃣ Obtener instancias y métricas
        instancias = obtener_instancias_por_slice(id_slice)
        if not instancias:
            return {"error": "No se encontraron instancias"}
        
        metrics = obtener_metricas_actuales()
        if not metrics:
            return {"error": "No se pudo obtener métricas"}

        # 2️⃣ Generar plan de despliegue
        plan = generar_plan_deploy(id_slice, metrics, instancias)
        if not plan.get("can_deploy"):
            return {"can_deploy": False, "error": "Recursos insuficientes"}

        # 3️⃣ Desplegar VMs en paralelo
        resultados = []
        fallos = 0
        vms_exitosas = []
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_map = {}

            # Enviar cada VM al Linux Driver
            for vm in plan["placement_plan"]:
                # 🟢 PAYLOAD CORREGIDO
                vm_req = {
                    "nombre_vm": vm["nombre_vm"],
                    "worker": vm["worker"],
                    "vlans": [str(v) for v in vm["vlans"]],
                    "puerto_vnc": str(vm["puerto_vnc"]),
                    "imagen": vm["imagen"],
                    "ram_gb": float(vm["ram_gb"]),
                    "cpus": int(vm["cpus"]),
                    "disco_gb": float(vm["disco_gb"])
                }
                
                print(f"🖥️ Enviando VM {vm['nombre_vm']} a worker {vm['worker']}")
                print(f"   VLANs: {vm_req['vlans']}, RAM: {vm_req['ram_gb']}GB, CPU: {vm_req['cpus']}")
                
                future = executor.submit(desplegar_vm_en_worker, vm_req)
                future_map[future] = vm  # 🟢 Guardar objeto VM completo

            # 4️⃣ Procesar resultados conforme terminan
            for future in as_completed(future_map):
                vm = future_map[future]
                vm_name = vm["nombre_vm"]
                
                try:
                    result = future.result()
                    
                    if result["status"]:
                        # ✅ VM DESPLEGADA EXITOSAMENTE
                        print(f"✅ VM {vm_name}: PID {result.get('pid', 'N/A')}")
                        
                        # 🟢 ACTUALIZAR BASE DE DATOS
                        with engine.begin() as conn:
                            # 1️⃣ Obtener ID del VNC desde la tabla vnc
                            vnc_id = None
                            if vm.get("puerto_vnc"):
                                vnc_query = conn.execute(text("""
                                    SELECT idvnc FROM vnc WHERE puerto = :puerto
                                """), {"puerto": vm["puerto_vnc"]})
                                vnc_row = vnc_query.fetchone()
                                vnc_id = vnc_row[0] if vnc_row else None
                                print(f"   VNC: puerto={vm['puerto_vnc']} → ID={vnc_id}")
                            
                            # 2️⃣ Obtener ID del worker desde la tabla worker
                            worker_id = None
                            if vm.get("worker"):
                                worker_query = conn.execute(text("""
                                    SELECT idworker FROM worker WHERE ip = :worker_ip
                                """), {"worker_ip": vm["worker"]})
                                worker_row = worker_query.fetchone()
                                worker_id = worker_row[0] if worker_row else None
                                
                                # Si no existe el worker, agregarlo automáticamente
                                if not worker_id:
                                    print(f"⚠️ Worker {vm['worker']} no encontrado, creándolo...")
                                    insert_result = conn.execute(text("""
                                        INSERT INTO worker (nombre, ip, cpu, ram, storage)
                                        VALUES (:nombre, :ip, '4', '8GB', '100GB')
                                    """), {
                                        "nombre": next((k for k, v in WORKER_IPS.items() if v == vm['worker']), f"worker_{vm['worker']}"),
                                        "ip": vm['worker']
                                    })
                                    worker_id = insert_result.lastrowid
                                    print(f"✅ Worker creado con ID={worker_id}")
                                else:
                                    print(f"   Worker: IP={vm['worker']} → ID={worker_id}")
                            
                            # 3️⃣ Actualizar instancia con TODOS los campos necesarios
                            conn.execute(text("""
                                UPDATE instancia
                                SET estado = 'RUNNING',
                                    ip = :ip,
                                    vnc_idvnc = :vnc_id,
                                    worker_idworker = :worker_id
                                WHERE nombre = :vm_name AND slice_idslice = :sid
                            """), {
                                "ip": vm.get("ip_asignada"),
                                "vnc_id": vnc_id,
                                "worker_id": worker_id,
                                "vm_name": vm_name,
                                "sid": id_slice
                            })
                            
                            # 4️⃣ Actualizar VNC como ocupado
                            if vnc_id:
                                conn.execute(text("""
                                    UPDATE vnc 
                                    SET estado = 'ocupada'
                                    WHERE idvnc = :vnc_id
                                """), {"vnc_id": vnc_id})
                            
                            # 5️⃣ MARCAR VLANs COMO OCUPADAS
                            for vlan_numero in vm["vlans"]:
                                conn.execute(text("""
                                    UPDATE vlan
                                    SET estado = 'ocupada'
                                    WHERE numero = :vlan_numero
                                """), {"vlan_numero": str(vlan_numero)})
                        
                        vms_exitosas.append(vm_name)
                        
                        resultados.append({
                            "vm": vm_name,
                            "worker": vm["worker"],
                            "vlans": vm["vlans"],
                            "puerto_vnc": vm["puerto_vnc"],
                            "success": True,
                            "message": result["message"],
                            "pid": result.get("pid"),
                            "status": "RUNNING"
                        })
                        
                    else:
                        # ❌ VM FALLÓ AL DESPLEGARSE
                        fallos += 1
                        print(f"❌ VM {vm_name}: {result['message']}")
                        
                        # 🟢 MARCAR INSTANCIA COMO FAILED
                        with engine.begin() as conn:
                            conn.execute(text("""
                                UPDATE instancia
                                SET estado = 'FAILED'
                                WHERE nombre = :vm_name AND slice_idslice = :sid
                            """), {"vm_name": vm_name, "sid": id_slice})
                        
                        resultados.append({
                            "vm": vm_name,
                            "worker": vm["worker"],
                            "vlans": vm.get("vlans", []),
                            "success": False,
                            "message": result["message"],
                            "pid": None,
                            "status": "FAILED"
                        })
                        
                except Exception as e:
                    fallos += 1
                    error_msg = f"Excepción desplegando VM {vm_name}: {str(e)}"
                    print(f"❌ {error_msg}")
                    
                    # Marcar como failed en BD
                    with engine.begin() as conn:
                        conn.execute(text("""
                            UPDATE instancia
                            SET estado = 'FAILED'
                            WHERE nombre = :vm_name AND slice_idslice = :sid
                        """), {"vm_name": vm_name, "sid": id_slice})
                    
                    resultados.append({
                        "vm": vm_name,
                        "worker": vm.get("worker", "N/A"),
                        "success": False,
                        "message": error_msg,
                        "pid": None,
                        "status": "EXCEPTION"
                    })

        # 5️⃣ Estado final del slice
        estado_final = "RUNNING" if fallos == 0 else ("PARTIAL" if len(vms_exitosas) > 0 else "FAILED")
        
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE slice 
                SET estado = :e 
                WHERE idslice = :sid
            """), {"e": estado_final, "sid": id_slice})

        # 6️⃣ Respuesta final detallada
        return {
            "success": fallos == 0,
            "timestamp": datetime.utcnow().isoformat(),
            "slice_id": id_slice,
            "estado_final": estado_final,
            "resumen": {
                "total_vms": len(plan["placement_plan"]),
                "exitosas": len(vms_exitosas),
                "fallidas": fallos,
                "porcentaje_exito": round((len(vms_exitosas) / len(plan["placement_plan"])) * 100, 2)
            },
            "vms_exitosas": vms_exitosas,
            "deployment_plan": plan["placement_plan"],
            "workers_utilizados": list(set([vm["worker"] for vm in plan["placement_plan"]])),
            "vlans_asignadas": list(set([str(v) for vm in plan["placement_plan"] for v in vm["vlans"]])),
            "detalle_completo": resultados,
            "message": f"Despliegue {'completo' if fallos == 0 else 'parcial' if len(vms_exitosas) > 0 else 'fallido'} del slice {id_slice}"
        }
        
    except Exception as e:
        # 🟢 ROLLBACK EN CASO DE ERROR CRÍTICO
        print(f"❌ Error crítico en despliegue del slice {id_slice}: {e}")
        
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE slice 
                SET estado = 'FAILED' 
                WHERE idslice = :sid
            """), {"sid": id_slice})
        
        return {
            "success": False,
            "error": f"Error crítico durante despliegue: {str(e)}",
            "slice_id": id_slice,
            "timestamp": datetime.utcnow().isoformat(),
            "estado_final": "FAILED"
        }


#prueba de borrado
@app.post("/placement/delete")
def delete_slice(data: dict = Body(...)):
    id_slice = data.get("id_slice")
    if not id_slice:
        return {"error": "Falta el parámetro 'id_slice'"}

    print(f"🗑️ Iniciando eliminación completa del slice {id_slice}...")

    # 🟡 Estado inicial del slice
    with engine.begin() as conn:
        # Verificar que el slice existe y obtener estado actual
        slice_result = conn.execute(text("""
            SELECT estado FROM slice WHERE idslice = :sid
        """), {"sid": id_slice})
        slice_row = slice_result.fetchone()
        
        if not slice_row:
            return {"error": f"Slice {id_slice} no encontrado"}
        
        current_state = slice_row[0]
        print(f"📊 Estado actual del slice: {current_state}")
        
        # Actualizar estado a DELETING
        conn.execute(text("""
            UPDATE slice 
            SET estado = 'DELETING'
            WHERE idslice = :sid
        """), {"sid": id_slice})

    try:
        # 1️⃣ OBTENER DATOS COMPLETOS DEL SLICE
        print("📋 Obteniendo datos del slice para eliminación...")
        slice_data = obtener_datos_completos_slice(id_slice)
        
        if not slice_data:
            return {"error": "No se pudieron obtener los datos del slice"}
        
        # 2️⃣ ELIMINAR VMs EN PARALELO
        print("🖥️ Eliminando máquinas virtuales...")
        vm_results = eliminar_vms_paralelo(slice_data["instancias"])
        
        # 3️⃣ LIBERAR RECURSOS DE RED
        print("🌐 Liberando recursos de red...")
        network_results = liberar_recursos_red(id_slice)
        
        # 4️⃣ LIMPIAR BASE DE DATOS
        print("🗄️ Limpiando registros de base de datos...")
        db_results = limpiar_registros_bd(id_slice)
        
        # 5️⃣ GENERAR REPORTE DE ELIMINACIÓN
        deletion_report = generar_reporte_eliminacion(
            id_slice, vm_results, network_results, db_results
        )
        
        print(f"✅ Slice {id_slice} eliminado completamente")
        return deletion_report
        
    except Exception as e:
        print(f"❌ Error durante eliminación del slice {id_slice}: {e}")
        
        # Revertir estado en caso de error
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE slice 
                SET estado = :prev_state
                WHERE idslice = :sid
            """), {"prev_state": current_state, "sid": id_slice})
        
        return {
            "success": False,
            "error": f"Error durante eliminación: {str(e)}",
            "slice_id": id_slice,
            "timestamp": datetime.utcnow().isoformat()
        }



def obtener_datos_completos_slice(id_slice: int):
    """
    Obtiene todos los datos necesarios para eliminar un slice
    """
    try:
        with engine.connect() as conn:
            # Obtener información del slice
            slice_query = text("""
                SELECT s.idslice, s.nombre, s.estado, s.topologia
                FROM slice s
                WHERE s.idslice = :id_slice
            """)
            slice_result = conn.execute(slice_query, {"id_slice": id_slice})
            slice_info = slice_result.fetchone()
            
            if not slice_info:
                return None
            
            # Obtener instancias con todos sus recursos asignados
            instancias_query = text("""
                SELECT 
                    i.idinstancia, i.nombre, i.estado, i.cpu, i.ram, i.storage,
                    i.salidainternet, i.ip, i.worker_idworker,
                    v.puerto as vnc_puerto, v.idvnc,
                    w.nombre as worker_nombre, w.ip as worker_ip,
                    im.ruta AS imagen
                FROM instancia i
                LEFT JOIN vnc v ON i.vnc_idvnc = v.idvnc
                LEFT JOIN worker w ON i.worker_idworker = w.idworker
                LEFT JOIN imagen im ON i.imagen_idimagen = im.idimagen
                WHERE i.slice_idslice = :id_slice
            """)
            instancias_result = conn.execute(instancias_query, {"id_slice": id_slice})
            instancias = [dict(row._mapping) for row in instancias_result]
            
            # Obtener enlaces y VLANs
            enlaces_query = text("""
                SELECT 
                    e.idenlace, e.vm1, e.vm2, e.vlan_idvlan,
                    v.numero as vlan_numero, v.idvlan
                FROM enlace e
                LEFT JOIN vlan v ON e.vlan_idvlan = v.idvlan
                WHERE e.slice_idslice = :id_slice
            """)
            enlaces_result = conn.execute(enlaces_query, {"id_slice": id_slice})
            enlaces = [dict(row._mapping) for row in enlaces_result]
            
            return {
                "slice_info": dict(slice_info._mapping),
                "instancias": instancias,
                "enlaces": enlaces
            }
            
    except Exception as e:
        print(f"❌ Error obteniendo datos del slice {id_slice}: {e}")
        return None


def eliminar_vms_paralelo(instancias: list):
    """
    Elimina todas las VMs del slice en paralelo usando ThreadPoolExecutor
    """
    results = []
    
    if not instancias:
        return {"vms_eliminadas": 0, "errores": 0, "detalles": []}
    
    print(f"🔧 Eliminando {len(instancias)} VMs en paralelo...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Crear tareas para cada VM
        future_to_vm = {}
        for instancia in instancias:
            if instancia["worker_ip"]:  # Solo si tiene worker asignado
                future = executor.submit(eliminar_vm_individual, instancia)
                future_to_vm[future] = instancia
        
        # Recoger resultados
        vms_eliminadas = 0
        errores = 0
        
        for future in as_completed(future_to_vm):
            instancia = future_to_vm[future]
            try:
                result = future.result()
                results.append({
                    "vm_nombre": instancia["nombre"],
                    "vm_id": instancia["idinstancia"],
                    "worker": instancia["worker_ip"],
                    "success": result["success"],
                    "message": result["message"]
                })
                
                if result["success"]:
                    vms_eliminadas += 1
                    print(f"✅ VM {instancia['nombre']} eliminada correctamente")
                else:
                    errores += 1
                    print(f"❌ Error eliminando VM {instancia['nombre']}: {result['message']}")
                    
            except Exception as e:
                errores += 1
                error_msg = f"Excepción eliminando VM {instancia['nombre']}: {str(e)}"
                print(f"❌ {error_msg}")
                results.append({
                    "vm_nombre": instancia["nombre"],
                    "vm_id": instancia["idinstancia"],
                    "worker": instancia.get("worker_ip", "N/A"),
                    "success": False,
                    "message": error_msg
                })
    
    return {
        "vms_eliminadas": vms_eliminadas,
        "errores": errores,
        "total": len(instancias),
        "detalles": results
    }

def eliminar_vm_individual(instancia: dict):
    """
    Elimina una VM individual enviando petición al Linux Driver
    """
    LINUX_DRIVER_URL = os.getenv("LINUX_DRIVER_URL", "http://linux-driver:9100")
    url = f"{LINUX_DRIVER_URL}/delete_vm"
    
    # Preparar payload para eliminación
    vm_data = {
        "nombre_vm": instancia["nombre"],
        "worker_ip": instancia["worker_ip"],
        "vm_id": instancia["idinstancia"],
        "vnc_puerto": instancia.get("vnc_puerto"),
        "pid": None  # Se puede obtener de una tabla de procesos si se mantiene
    }
    
    try:
        print(f"[HTTP] → POST {url} (Eliminar {instancia['nombre']})")
        
        resp = requests.post(url, json=vm_data, timeout=60)
        raw = resp.text
        print(f"[HTTP] ← {resp.status_code}: {raw[:200]}")
        
        if resp.status_code != 200:
            return {"success": False, "message": f"HTTP {resp.status_code}: {raw}"}
        
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return {"success": False, "message": "Respuesta no es JSON válido"}
        
        success = bool(data.get("success", data.get("status", False)))
        message = data.get("mensaje") or data.get("message") or "VM eliminada"
        
        return {"success": success, "message": message, "raw": data}
        
    except requests.exceptions.Timeout:
        return {"success": False, "message": "Timeout eliminando VM"}
    except Exception as e:
        return {"success": False, "message": f"Error de conexión: {str(e)}"}

def eliminar_vms_paralelo(instancias: list):
    """
    Elimina todas las VMs del slice en paralelo usando ThreadPoolExecutor
    """
    results = []
    
    if not instancias:
        return {"vms_eliminadas": 0, "errores": 0, "detalles": []}
    
    print(f"🔧 Eliminando {len(instancias)} VMs en paralelo...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Crear tareas para cada VM
        future_to_vm = {}
        for instancia in instancias:
            if instancia["worker_ip"]:  # Solo si tiene worker asignado
                future = executor.submit(eliminar_vm_individual, instancia)
                future_to_vm[future] = instancia
        
        # Recoger resultados
        vms_eliminadas = 0
        errores = 0
        
        for future in as_completed(future_to_vm):
            instancia = future_to_vm[future]
            try:
                result = future.result()
                results.append({
                    "vm_nombre": instancia["nombre"],
                    "vm_id": instancia["idinstancia"],
                    "worker": instancia["worker_ip"],
                    "success": result["success"],
                    "message": result["message"]
                })
                
                if result["success"]:
                    vms_eliminadas += 1
                    print(f"✅ VM {instancia['nombre']} eliminada correctamente")
                else:
                    errores += 1
                    print(f"❌ Error eliminando VM {instancia['nombre']}: {result['message']}")
                    
            except Exception as e:
                errores += 1
                error_msg = f"Excepción eliminando VM {instancia['nombre']}: {str(e)}"
                print(f"❌ {error_msg}")
                results.append({
                    "vm_nombre": instancia["nombre"],
                    "vm_id": instancia["idinstancia"],
                    "worker": instancia.get("worker_ip", "N/A"),
                    "success": False,
                    "message": error_msg
                })
    
    return {
        "vms_eliminadas": vms_eliminadas,
        "errores": errores,
        "total": len(instancias),
        "detalles": results
    }

def eliminar_vm_individual(instancia: dict):
    """
    Elimina una VM individual enviando petición al Linux Driver
    """
    LINUX_DRIVER_URL = os.getenv("LINUX_DRIVER_URL", "http://linux-driver:9100")
    url = f"{LINUX_DRIVER_URL}/delete_vm"
    
    # Preparar payload para eliminación
    vm_data = {
        "nombre_vm": instancia["nombre"],
        "worker_ip": instancia["worker_ip"],
        "vm_id": instancia["idinstancia"],
        "vnc_puerto": instancia.get("vnc_puerto"),
        "pid": None  # Se puede obtener de una tabla de procesos si se mantiene
    }
    
    try:
        print(f"[HTTP] → POST {url} (Eliminar {instancia['nombre']})")
        
        resp = requests.post(url, json=vm_data, timeout=60)
        raw = resp.text
        print(f"[HTTP] ← {resp.status_code}: {raw[:200]}")
        
        if resp.status_code != 200:
            return {"success": False, "message": f"HTTP {resp.status_code}: {raw}"}
        
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return {"success": False, "message": "Respuesta no es JSON válido"}
        
        success = bool(data.get("success", data.get("status", False)))
        message = data.get("mensaje") or data.get("message") or "VM eliminada"
        
        return {"success": success, "message": message, "raw": data}
        
    except requests.exceptions.Timeout:
        return {"success": False, "message": "Timeout eliminando VM"}
    except Exception as e:
        return {"success": False, "message": f"Error de conexión: {str(e)}"}
    

def liberar_recursos_red(id_slice: int):
    """
    Libera VLANs y puertos VNC asignados al slice
    """
    results = {
        "vlans_liberadas": 0,
        "vncs_liberados": 0,
        "errores": [],
        "detalles": []
    }
    
    try:
        # 1️⃣ LIBERAR VLANs
        print("🔓 Liberando VLANs...")
        vlans_result = liberar_vlans_slice(id_slice)
        results["vlans_liberadas"] = vlans_result["liberadas"]
        results["detalles"].extend(vlans_result["detalles"])
        
        # 2️⃣ LIBERAR PUERTOS VNC
        print("🔓 Liberando puertos VNC...")
        vnc_result = liberar_vncs_slice(id_slice)
        results["vncs_liberados"] = vnc_result["liberados"]
        results["detalles"].extend(vnc_result["detalles"])
        
        return results
        
    except Exception as e:
        error_msg = f"Error liberando recursos de red: {str(e)}"
        print(f"❌ {error_msg}")
        results["errores"].append(error_msg)
        return results

def liberar_vlans_slice(id_slice: int):
    """
    Libera todas las VLANs asignadas a un slice
    """
    try:
        # Via Network Manager (si está disponible)
        vlans_liberadas_nm = 0
        try:
            response = requests.post(
                f"{NETWORK_BASE}/vlans/liberar_slice",
                json={"slice_id": id_slice},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                vlans_liberadas_nm = data.get("vlans_liberadas", 0)
                print(f"✅ Network Manager liberó {vlans_liberadas_nm} VLANs")
        except Exception as e:
            print(f"⚠️ Network Manager no disponible, liberando VLANs directamente: {e}")
        
        # Liberar VLANs directamente en BD
        with engine.begin() as conn:
            # Obtener VLANs del slice
            vlans_query = text("""
                SELECT DISTINCT vlan_idvlan, vlan
                FROM enlace 
                WHERE slice_idslice = :slice_id 
                AND vlan_idvlan IS NOT NULL
            """)
            vlans_result = conn.execute(vlans_query, {"slice_id": id_slice})
            vlans_slice = vlans_result.fetchall()
            
            vlans_liberadas_bd = 0
            detalles = []
            
            for vlan_row in vlans_slice:
                vlan_id = vlan_row[0]
                vlan_numero = vlan_row[1]
                
                # Marcar VLAN como disponible
                conn.execute(text("""
                    UPDATE vlan 
                    SET estado = 'disponible' 
                    WHERE idvlan = :vlan_id
                """), {"vlan_id": vlan_id})
                
                vlans_liberadas_bd += 1
                detalles.append(f"VLAN {vlan_numero} (ID:{vlan_id}) liberada")
                print(f"🔓 VLAN {vlan_numero} liberada")
        
        total_liberadas = max(vlans_liberadas_nm, vlans_liberadas_bd)
        return {"liberadas": total_liberadas, "detalles": detalles}
        
    except Exception as e:
        return {"liberadas": 0, "detalles": [f"Error liberando VLANs: {str(e)}"]}

def liberar_vncs_slice(id_slice: int):
    """
    Libera puertos VNC asignados a instancias del slice
    """
    try:
        # Via Network Manager (si está disponible)
        vncs_liberados_nm = 0
        try:
            response = requests.post(
                f"{NETWORK_BASE}/vncs/liberar_slice",
                json={"slice_id": id_slice},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                vncs_liberados_nm = data.get("vncs_liberados", 0)
                print(f"✅ Network Manager liberó {vncs_liberados_nm} puertos VNC")
        except Exception as e:
            print(f"⚠️ Network Manager no disponible, liberando VNCs directamente: {e}")
        
        # Liberar VNCs directamente en BD
        with engine.begin() as conn:
            # Obtener VNCs del slice
            vncs_query = text("""
                SELECT DISTINCT v.idvnc, v.puerto
                FROM instancia i
                JOIN vnc v ON i.vnc_idvnc = v.idvnc
                WHERE i.slice_idslice = :slice_id
            """)
            vncs_result = conn.execute(vncs_query, {"slice_id": id_slice})
            vncs_slice = vncs_result.fetchall()
            
            vncs_liberados_bd = 0
            detalles = []
            
            for vnc_row in vncs_slice:
                vnc_id = vnc_row[0]
                puerto = vnc_row[1]
                
                # Marcar VNC como disponible
                conn.execute(text("""
                    UPDATE vnc 
                    SET estado = 'disponible' 
                    WHERE idvnc = :vnc_id
                """), {"vnc_id": vnc_id})
                
                vncs_liberados_bd += 1
                detalles.append(f"Puerto VNC {puerto} (ID:{vnc_id}) liberado")
                print(f"🔓 Puerto VNC {puerto} liberado")
        
        total_liberados = max(vncs_liberados_nm, vncs_liberados_bd)
        return {"liberados": total_liberados, "detalles": detalles}
        
    except Exception as e:
        return {"liberados": 0, "detalles": [f"Error liberando VNCs: {str(e)}"]}

def limpiar_registros_bd(id_slice: int):
    """
    Elimina todos los registros relacionados con el slice de la BD
    """
    results = {
        "enlaces_eliminados": 0,
        "instancias_eliminadas": 0,
        "relaciones_eliminadas": 0,
        "slice_eliminado": False,
        "errores": []
    }
    
    try:
        with engine.begin() as conn:
            # 1️⃣ LIMPIAR ENLACES
            enlaces_result = conn.execute(text("""
                DELETE FROM enlace WHERE slice_idslice = :slice_id
            """), {"slice_id": id_slice})
            results["enlaces_eliminados"] = enlaces_result.rowcount
            print(f"🗑️ {results['enlaces_eliminados']} enlaces eliminados")
            
            # 2️⃣ LIMPIAR INSTANCIAS
            # Primero desasignar VNCs y Workers para no perder la referencia
            conn.execute(text("""
                UPDATE instancia 
                SET vnc_idvnc = NULL, worker_idworker = NULL 
                WHERE slice_idslice = :slice_id
            """), {"slice_id": id_slice})
            
            # Eliminar instancias
            instancias_result = conn.execute(text("""
                DELETE FROM instancia WHERE slice_idslice = :slice_id
            """), {"slice_id": id_slice})
            results["instancias_eliminadas"] = instancias_result.rowcount
            print(f"🗑️ {results['instancias_eliminadas']} instancias eliminadas")
            
            # 3️⃣ LIMPIAR RELACIONES USUARIO-SLICE
            relaciones_result = conn.execute(text("""
                DELETE FROM usuario_has_slice WHERE slice_idslice = :slice_id
            """), {"slice_id": id_slice})
            results["relaciones_eliminadas"] = relaciones_result.rowcount
            print(f"🗑️ {results['relaciones_eliminadas']} relaciones usuario-slice eliminadas")
            
            # 4️⃣ ELIMINAR SLICE
            slice_result = conn.execute(text("""
                DELETE FROM slice WHERE idslice = :slice_id
            """), {"slice_id": id_slice})
            results["slice_eliminado"] = slice_result.rowcount > 0
            print(f"🗑️ Slice {id_slice} {'eliminado' if results['slice_eliminado'] else 'no eliminado'}")
            
        return results
        
    except Exception as e:
        error_msg = f"Error limpiando BD: {str(e)}"
        print(f"❌ {error_msg}")
        results["errores"].append(error_msg)
        return results

def generar_reporte_eliminacion(id_slice: int, vm_results: dict, network_results: dict, db_results: dict):
    """
    Genera reporte completo de la eliminación del slice
    """
    total_operaciones = (
        vm_results["vms_eliminadas"] + 
        network_results["vlans_liberadas"] + 
        network_results["vncs_liberados"] +
        db_results["enlaces_eliminados"] +
        db_results["instancias_eliminadas"]
    )
    
    total_errores = (
        vm_results["errores"] + 
        len(network_results["errores"]) +
        len(db_results["errores"])
    )
    
    success = total_errores == 0 and db_results["slice_eliminado"]
    
    return {
        "success": success,
        "slice_id": id_slice,
        "timestamp": datetime.utcnow().isoformat(),
        "resumen": {
            "total_operaciones": total_operaciones,
            "operaciones_exitosas": total_operaciones - total_errores,
            "errores": total_errores,
            "slice_completamente_eliminado": success
        },
        "vms": {
            "eliminadas": vm_results["vms_eliminadas"],
            "errores": vm_results["errores"],
            "detalles": vm_results["detalles"]
        },
        "recursos_red": {
            "vlans_liberadas": network_results["vlans_liberadas"],
            "vncs_liberados": network_results["vncs_liberados"],
            "errores": network_results["errores"]
        },
        "base_datos": {
            "enlaces_eliminados": db_results["enlaces_eliminados"],
            "instancias_eliminadas": db_results["instancias_eliminadas"],
            "relaciones_eliminadas": db_results["relaciones_eliminadas"],
            "slice_eliminado": db_results["slice_eliminado"],
            "errores": db_results["errores"]
        },
        "message": f"Slice {id_slice} {'eliminado completamente' if success else 'eliminado con errores'}"
    }


# ======================================
# MAIN
# ======================================
if __name__ == "__main__":
    import uvicorn
    print("  Slice Manager escuchando en 0.0.0.0:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
