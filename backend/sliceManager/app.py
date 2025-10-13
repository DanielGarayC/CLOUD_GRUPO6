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
    "server2": "10.0.10.2",
    "server3": "10.0.10.3",
    "server4": "10.0.10.4"
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
        SELECT idenlace, vm1, vm2, vlan_idvlan
        FROM enlace
        WHERE slice_idslice = :id_slice
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"id_slice": id_slice})
        return [dict(row._mapping) for row in result]

def asignar_vlans_a_enlaces(id_slice: int):
    """
    Revisa los enlaces del slice y asigna VLANs nuevas si no tienen ninguna.
    Devuelve la lista de enlaces actualizada.
    """
    enlaces = obtener_enlaces_por_slice(id_slice)
    for e in enlaces:
        if e["vlan_idvlan"] is None:
            vlan_info = solicitar_vlan()
            if vlan_info and vlan_info.get("idvlan"):
                idvlan = vlan_info["idvlan"]
                # Guardar en BD
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE enlace
                        SET vlan_idvlan = :idvlan
                        WHERE idenlace = :idenlace
                    """), {"idvlan": idvlan, "idenlace": e["idenlace"]})
                # Actualizar en memoria
                e["vlan_idvlan"] = idvlan
                print(f"🔗 Enlace {e['idenlace']} → VLAN asignada {idvlan}")
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

    # Asignación Round-Robin
    plan = []
    idx = 0
    enlaces = asignar_vlans_a_enlaces(id_slice)

    for vm in instancias:
        w = workers[idx]
        ram_value = float(str(vm["ram"]).replace("GB", "").strip())
        storage_value = float(str(vm["storage"]).replace("GB", "").strip())

        # Parte NETWORK MANAGER

        vlans_vm = [e["vlan_idvlan"] for e in enlaces if vm["idinstancia"] in (e["vm1"], e["vm2"])]

        # Si la VM tiene salida a internet, agregar VLAN de internet
        if vm.get("salidainternet"):
            vlan_int = solicitar_vlan_internet()
            if vlan_int:
                vlans_vm.append(vlan_int.get("idvlan"))

        # Solicitar VNC
        vnc_info = solicitar_vnc()
        id_vnc = vnc_info.get("idvnc") if vnc_info else None
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
    """Envía la petición al Linux Driver y devuelve JSON normalizado."""
    LINUX_DRIVER_URL = os.getenv("LINUX_DRIVER_URL", "http://linux-driver:9100")
    url = f"{LINUX_DRIVER_URL}/create_vm"

    try:
        print(f"[HTTP] → POST {url}")
        print(f"[HTTP] Payload: {json.dumps(vm_data)[:500]}")

        resp = requests.post(url, json=vm_data, timeout=200)
        raw = resp.text
        print(f"[HTTP] ← {resp.status_code}: {raw[:500]}")

        if resp.status_code != 200:
            return {"status": False, "message": f"HTTP {resp.status_code}", "raw": raw}

        try:
            data = resp.json()
        except json.JSONDecodeError:
            return {"status": False, "message": "Respuesta no es JSON", "raw": raw}

        ok = bool(data.get("success", data.get("status", False)))
        msg = data.get("mensaje") or data.get("message") or data.get("stdout") or "Sin mensaje"
        pid = data.get("pid")
        return {"status": ok, "message": msg, "pid": pid, "raw": data}

    except Exception as e:
        return {"status": False, "message": f"❌ Error de conexión con Linux Driver: {e}"}




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
    # 🟡 Estado inicial del slice
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE slice 
            SET estado = 'DEPLOYING'
            WHERE idslice = :sid
        """), {"sid": id_slice})



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
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {}

        # Enviar cada VM al Linux Driver
        for vm in plan["placement_plan"]:
            vm_req = {
                "nombre_vm": vm["nombre_vm"],
                "worker": vm["worker"],
                "vlans": [str(v) for v in vm["vlans"]],
                "puerto_vnc": vm["puerto_vnc"],
                "imagen": vm["imagen"],
                "ram_mb": int(vm["ram_gb"] * 1024),
                "cpus": vm["cpus"],
                "disco_gb": vm["disco_gb"]
            }
            fut = executor.submit(desplegar_vm_en_worker, vm_req)
            future_map[fut] = vm

        # Procesar resultados conforme terminan
        for fut in as_completed(future_map):
            vm = future_map[fut]
            try:
                resp = fut.result()
            except Exception as e:
                resp = {"status": False, "message": f"Error interno: {e}"}

            ok = resp.get("status", False)
            msg = resp.get("message", "Sin mensaje")
            pid = resp.get("pid")

            if ok:
                print(f"✅ VM {vm['nombre_vm']} desplegada correctamente en {vm['worker']}")
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE instancia
                        SET estado = 'RUNNING',
                            cpu = :cpu,
                            ram = :ram,
                            storage = :storage,
                            vnc_idvnc = (SELECT idvnc FROM vnc WHERE puerto = :p LIMIT 1),
                            worker_idworker = (SELECT idworker FROM worker WHERE ip = :ip LIMIT 1)
                        WHERE nombre = :vm AND slice_idslice = :sid
                    """), {
                        "cpu": str(vm["cpus"]),
                        "ram": f"{vm['ram_gb']} GB",
                        "storage": f"{vm['disco_gb']} GB",
                        "p": vm["puerto_vnc"],
                        "ip": vm["worker"],
                        "vm": vm["nombre_vm"],
                        "sid": id_slice
                    })

                    # Marcar VLANs usadas por esta VM como ocupadas
                    for vlan_id in vm["vlans"]:
                        conn.execute(text("""
                            UPDATE vlan
                            SET estado = 'ocupada'
                            WHERE idvlan = :vlan_id
                        """), {"vlan_id": vlan_id})
            else:
                # ❌ Fallo → rollback de VM y marcar como FAILED
                print("fashó")
                fallos += 1
                #try:
                    #requests.post("http://linux-driver:9100/delete_vm", json={
                        #nombre_vm": vm["nombre_vm"],
                        #"worker": vm["worker"]
                    #}, timeout=10)
                #except Exception as e:
                    #print(f"⚠️ Error al eliminar VM fallida: {e}")

                #with engine.begin() as conn:
                    #conn.execute(text("""
                        #UPDATE instancia
                        #SET estado = 'FAILED'
                        #WHERE nombre = :vm AND slice_idslice = :sid
                    #"""), {"vm": vm["nombre_vm"], "sid": id_slice})

            resultados.append({
                "vm": vm["nombre_vm"],
                "worker": vm["worker"],
                "vlans": vm["vlans"],
                "puerto_vnc": vm["puerto_vnc"],
                "pid": pid,
                "status": ok,
                "mensaje": msg
            })

    # Estado final del slice
    estado_final = "RUNNING" if fallos == 0 else "ERROR"
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE slice 
            SET estado = :e 
            WHERE idslice = :sid
        """), {"e": estado_final, "sid": id_slice})

    # 5️⃣ Respuesta final
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "slice": id_slice,
        "estado_final": estado_final,
        "total_vms": len(plan["placement_plan"]),
        "exitosas": len(plan["placement_plan"]) - fallos,
        "fallidas": fallos,
        "detalle": resultados
    }


# ======================================
# MAIN
# ======================================
if __name__ == "__main__":
    import uvicorn
    print("  Slice Manager escuchando en 0.0.0.0:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
