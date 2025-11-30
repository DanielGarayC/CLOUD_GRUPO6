from fastapi import FastAPI, Body
from datetime import datetime
from sqlalchemy import create_engine, text
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, json, os
from rabbitmq_utils import rpc_call_network
from rabbitmq_utils import rpc_call_vm_placement


app = FastAPI(title="Slice Manager Hybrid", version="4.0")

# ======================================
# CONFIGURACIÓN BASE DE DATOS Y MONITOREO
# ======================================
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "root")
DB_HOST = os.getenv("DB_HOST", "slice_db")
DB_NAME = os.getenv("DB_NAME", "mydb")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

MONITORING_URL = "http://monitoring_service:5010/metrics"
NETWORK_BASE = "http://network_manager:8100"
LINUX_DRIVER_URL = os.getenv("LINUX_DRIVER_URL", "http://linux-driver:9100")

# Mapeo estático de workers
WORKER_IPS = {
    "server2": "192.168.201.2",
    "server3": "192.168.201.3",
    "server4": "192.168.201.4",
    "worker1": "192.168.202.2",
    "worker2": "192.168.202.3",
    "worker3": "192.168.202.4",
}

# ======================================
# FUNCIONES AUXILIARES - BASE DE DATOS
# ======================================

def obtener_instancias_por_slice(id_slice: int):
    """Obtiene instancias con información completa incluyendo OpenStack IDs"""
    query = text("""
        SELECT 
            i.idinstancia, i.nombre, i.cpu, i.ram, i.storage, 
            i.salidainternet, 
            im.ruta AS imagen,
            im.nombre AS imagen_nombre,
            im.id_openstack AS imagen_id_openstack
        FROM instancia i
        JOIN imagen im ON i.imagen_idimagen = im.idimagen
        WHERE i.slice_idslice = :id_slice
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"id_slice": id_slice})
        return [dict(row._mapping) for row in result]

def obtener_enlaces_por_slice(id_slice: int):
    """Obtiene enlaces del slice"""
    query = text("""
        SELECT 
            e.idenlace, 
            e.vm1, 
            e.vm2, 
            e.vlan_idvlan, 
            e.vlan,
            v.numero
        FROM enlace e
        LEFT JOIN vlan v ON e.vlan_idvlan = v.idvlan
        WHERE e.slice_idslice = :id_slice
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"id_slice": id_slice})
        return [dict(row._mapping) for row in result]

def obtener_metricas_actuales():
    """Obtiene métricas de workers (solo para Linux)"""
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
# FUNCIONES - NETWORK MANAGER
# ======================================

def solicitar_vlan():
    """Solicita una VLAN vía RabbitMQ RPC (solo para Linux)"""
    try:
        resp = rpc_call_network({"action": "ASIGNAR_VLAN"})
        if "idvlan" in resp and "numero" in resp:
            return resp
        else:
            print(f"⚠️ Error en respuesta RPC VLAN: {resp}")
            return None
    except Exception as e:
        print(f"❌ Error RPC solicitando VLAN: {e}")
        return None

def solicitar_vlan_internet():
    """Solicita una VLAN para salida a internet (solo para Linux)"""
    try:
        resp = requests.get(f"{NETWORK_BASE}/vlans/internet", timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"⚠️ Error al solicitar VLAN de Internet: {resp.status_code}")
            return None
    except Exception as e:
        print(f"❌ No se pudo conectar con Network Manager: {e}")
        return None

def solicitar_vnc():
    """Solicita puerto VNC vía RabbitMQ RPC (solo para Linux)"""
    try:
        resp = rpc_call_network({"action": "ASIGNAR_VNC"})
        if resp and "puerto" in resp:
            return resp
        print("⚠️ Error RPC asignando VNC", resp)
        return None
    except Exception as e:
        print("❌ Error RPC solicitando VNC:", e)
        return None

# ======================================
# ASIGNACIÓN DE VLANs (SOLO PARA LINUX)
# ======================================

def asignar_vlans_a_enlaces_linux(id_slice: int):
    """
    Asigna VLANs a enlaces SOLO para plataforma Linux.
    En OpenStack, las VLANs se gestionan como redes virtuales.
    """
    enlaces = obtener_enlaces_por_slice(id_slice)
    print(f"📊 Enlaces encontrados: {len(enlaces)}")
    
    for e in enlaces:
        print(f"🔗 Enlace {e['idenlace']}: VM{e['vm1']} ↔ VM{e['vm2']} | VLAN: {e['vlan_idvlan']}")
        
        if e["vlan_idvlan"] is None:
            vlan_info = solicitar_vlan()
            if vlan_info and vlan_info.get("idvlan"):
                idvlan = vlan_info["idvlan"]
                numero_vlan = vlan_info.get("numero", str(idvlan))
                
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
                
                e["vlan_idvlan"] = idvlan
                e["numero"] = numero_vlan
                print(f"✅ Enlace {e['idenlace']} → VLAN {numero_vlan} (ID:{idvlan}) asignada")
            else:
                print(f"⚠️ No se pudo asignar VLAN al enlace {e['idenlace']}")
    
    return enlaces

# ======================================
# GENERACIÓN DE TOPOLOGÍA PARA OPENSTACK
# ======================================

def generar_topologia_redes_openstack(id_slice: int, instancias: list):
    """
    Genera la estructura de redes necesaria para OpenStack basada en los enlaces.
    """
    enlaces = obtener_enlaces_por_slice(id_slice)
    
    if not enlaces:
        print("ℹ️ No hay enlaces definidos, se creará una red por defecto")
        # Red por defecto para slices sin topología
        return {
            "redes": [{
                "enlace_id": "default",
                "vms": [inst["nombre"] for inst in instancias],  # ✅ USAR NOMBRES
                "cidr": "10.0.1.0/24",
                "nombre": f"net_slice_{id_slice}_default"
            }],
            "vm_networks": {
                inst["nombre"]: ["default"]  # ✅ USAR NOMBRES
                for inst in instancias
            }
        }
    
    # 🔍 CREAR MAPA DE ID → NOMBRE DE VMs
    id_to_nombre = {
        inst["idinstancia"]: inst["nombre"]
        for inst in instancias
    }
    
    print(f"🔍 Mapa ID → Nombre: {id_to_nombre}")
    
    # 🟢 CREAR MAPA DE REDES BASADO EN ENLACES
    redes = []
    vm_networks = {}  # {vm_nombre: [red_ids]}
    
    for idx, enlace in enumerate(enlaces):
        vm1_id = enlace["vm1"]
        vm2_id = enlace["vm2"]
        enlace_id = str(enlace["idenlace"])
        
        # 🔥 CONVERTIR IDs A NOMBRES
        vm1_nombre = id_to_nombre.get(vm1_id)
        vm2_nombre = id_to_nombre.get(vm2_id)
        
        if not vm1_nombre or not vm2_nombre:
            print(f"⚠️ Enlace {enlace_id}: No se encontraron nombres para VMs {vm1_id}/{vm2_id}")
            continue
        
        print(f"🔗 Enlace {enlace_id}: {vm1_nombre} ({vm1_id}) ↔ {vm2_nombre} ({vm2_id})")
        
        # Crear red para este enlace (CON NOMBRES)
        red = {
            "enlace_id": enlace_id,
            "vms": [vm1_nombre, vm2_nombre],  # ✅ USAR NOMBRES, NO IDs
            "cidr": f"10.0.{100 + idx}.0/24",
            "nombre": f"net_slice_{id_slice}_link_{enlace_id}",
            "vlan_ref": enlace.get("numero")
        }
        redes.append(red)
        
        # Asignar red a cada VM del enlace (CON NOMBRES)
        if vm1_nombre not in vm_networks:
            vm_networks[vm1_nombre] = []
        if vm2_nombre not in vm_networks:
            vm_networks[vm2_nombre] = []
        
        vm_networks[vm1_nombre].append(enlace_id)
        vm_networks[vm2_nombre].append(enlace_id)
    
    print(f"🌐 Topología OpenStack generada:")
    print(f"   • {len(redes)} redes a crear")
    print(f"   • {len(vm_networks)} VMs con conectividad")
    
    return {
        "redes": redes,
        "vm_networks": vm_networks
    }

#Obtener zona de disp. :D
def obtener_zona_disponibilidad(id_slice: int):
    """
    Devuelve la zona de disponibilidad del slice (por ejemplo: 'HP', 'STD', etc.).
    Ajusta el nombre de la columna según tu tabla.
    """
    query = text("""
        SELECT zonadisponibilidad
        FROM slice
        WHERE idslice = :sid
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"sid": id_slice})
        row = result.fetchone()
        if not row:
            return None
        return row[0]

# ======================================
# PLANES DE DESPLIEGUE POR PLATAFORMA
# ======================================

def generar_plan_deploy_linux(id_slice: int, instancias: list,placement_plan_vm: list | None = None):
    """
    Plan de despliegue para plataforma LINUX (código original adaptado)
    """
    print("[LINUX] Generando plan de despliegue...")
    
    if not placement_plan_vm:
            return {
                "can_deploy": False,
                "error": "placement_plan_vm vacío. Debes ejecutar /placement/verify primero."
            }
    
    vm_to_worker_name = {}

    for entry in placement_plan_vm:
        vm_name = entry.get("nombre_vm")
        worker_name = entry.get("worker")
        if vm_name and worker_name:
            vm_to_worker_name[vm_name] = worker_name

    # 🔹 2) Validar que todas las instancias tengan entrada en placement_plan
    nombres_instancias = {inst["nombre"] for inst in instancias}
    nombres_en_plan = set(vm_to_worker_name.keys())

    faltantes = nombres_instancias - nombres_en_plan
    if faltantes:
        return {
            "can_deploy": False,
            "error": f"Las VMs {', '.join(faltantes)} no tienen asignación en placement_plan."
        }

    # 🔹 3) Mapa worker_name → IP (ya NO usamos métricas)
    workers_by_name = {
        name: {"ip": ip}
        for name, ip in WORKER_IPS.items()
    }
    # 🟢 ASIGNAR VLANs A ENLACES (solo para Linux)
    print(f"🔍 Obteniendo enlaces para slice {id_slice}...")
    enlaces = asignar_vlans_a_enlaces_linux(id_slice)
    
    # 🟢 CREAR MAPA DE VLANS POR VM
    vlans_por_vm = {}
    for enlace in enlaces:
        vm1 = str(enlace["vm1"])
        vm2 = str(enlace["vm2"])
        vlan_numero = enlace.get("numero")
        
        if vlan_numero:
            if vm1 not in vlans_por_vm:
                vlans_por_vm[vm1] = []
            if vm2 not in vlans_por_vm:
                vlans_por_vm[vm2] = []
            
            vlans_por_vm[vm1].append(vlan_numero)
            vlans_por_vm[vm2].append(vlan_numero)
    
    print(f"📋 Mapa de VLANs por VM: {vlans_por_vm}")
    
    #Construcción del plan a partir del placement_plan de VM Placement
    plan = []
    
    for vm in instancias:
        vm_name = vm["nombre"]
        worker_name = vm_to_worker_name.get(vm_name)
        worker_info = workers_by_name.get(worker_name)

        if not worker_info:
            return {
                "can_deploy": False,
                "error": f"El worker '{worker_name}' (desde VM Placement) no existe en WORKER_IPS."
            }

        worker_ip = worker_info["ip"]

        ram_value = parse_ram_to_gb(vm["ram"])
        storage_value = float(str(vm["storage"]).replace("GB", "").strip())
        vm_id = str(vm["idinstancia"])
        vlans_vm = list(set(vlans_por_vm.get(vm_id, [])))

        # Salida a internet
        if vm.get("salidainternet"):
            vlan_int = solicitar_vlan_internet()
            if vlan_int and vlan_int.get("numero"):
                vlan_internet_num = vlan_int["numero"]
                vlans_vm = [vlan_internet_num] + [
                    v for v in vlans_vm if v != vlan_internet_num
                ]

        # Solicitar VNC
        vnc_info = solicitar_vnc()
        puerto_vnc = vnc_info.get("puerto") if vnc_info else None

        plan.append({
            "nombre_vm": vm_name,
            "worker": worker_ip,           # 👉 IP real para el driver
            "vlans": vlans_vm,
            "puerto_vnc": puerto_vnc,
            "imagen": vm["imagen"],        # Ruta de imagen para Linux
            "ram_gb": ram_value,
            "cpus": int(vm["cpu"]),
            "disco_gb": storage_value,
            "vm_id": vm_id
        })

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "can_deploy": True,
        "platform": "linux",
        "placement_plan": plan,
        "workers_status": workers_by_name
    }

def generar_plan_deploy_openstack(id_slice: int, instancias: list, placement_plan_vm: list | None = None):
    print("☁️ [OPENSTACK] Generando plan de despliegue con placement físico...")

    if not placement_plan_vm:
        return {
            "can_deploy": False,
            "error": "placement_plan_vm vacío. Debes ejecutar /placement/verify primero."
        }

    # Mapeo: nombre_vm -> worker físico (hostname)
    vm_to_worker = {
        e["nombre_vm"]: e["worker"]
        for e in placement_plan_vm
        if e.get("nombre_vm") and e.get("worker")
    }

    # Validar que todas las VMs tengan placement
    nombres_instancias = {inst["nombre"] for inst in instancias}
    faltantes = nombres_instancias - vm_to_worker.keys()
    if faltantes:
        return {
            "can_deploy": False,
            "error": f"Las VMs {', '.join(faltantes)} no tienen asignación en placement_plan."
        }

    # Generar topología de redes (para OpenStack)
    topologia = generar_topologia_redes_openstack(id_slice, instancias)

    print("=" * 60)
    print("🔍 DEBUG: TOPOLOGÍA GENERADA")
    print(f"📊 Total de redes: {len(topologia['redes'])}")
    print(f"📋 Detalle de redes:")
    for idx, red in enumerate(topologia['redes'], 1):
        print(f"   Red {idx}:")
        print(f"      • Nombre: {red.get('nombre', 'N/A')}")
        print(f"      • CIDR: {red.get('cidr', 'N/A')}")
        print(f"      • VMs: {red.get('vms', [])}")
        print(f"      • Enlace ID: {red.get('enlace_id', 'N/A')}")
    print("=" * 60)

    # Construir plan final
    plan = []
    flavors_necesarios = {}
    for vm in instancias:
        vm_name = vm["nombre"]
        worker_host = vm_to_worker[vm_name]  # Ej: "server2"
        worker_ip = WORKER_IPS.get(worker_host, "0.0.0.0")  # IP física real donde OpenStack la lanzará

        vm_id = str(vm["idinstancia"])
        ram_gb = parse_ram_to_gb(vm["ram"])
        storage_gb = float(str(vm["storage"]).replace("GB", "").strip())
        cpus = int(vm["cpu"])

        redes_de_vm = [
            r for r in topologia["redes"]
            if vm_name in r["vms"]
        ]
        
        print(f"🔍 VM '{vm_name}' conectada a {len(redes_de_vm)} red(es):")
        for red in redes_de_vm:
            print(f"   └─ {red.get('nombre')} ({red.get('cidr')})")

        # 🟢 VERIFICAR QUE TENGA ID DE OPENSTACK
        imagen_id_openstack = vm.get("imagen_id_openstack")
        if not imagen_id_openstack:
            print(f"⚠️ VM {vm['nombre']} no tiene imagen OpenStack asignada, usando imagen por defecto")
            # Aquí podrías tener una imagen por defecto o marcar como error
            imagen_id_openstack = "default-image-id"

        # 🟢 IDENTIFICAR FLAVOR (o crearlo dinámicamente)
        flavor_key = f"{cpus}cpu_{int(ram_gb)}ram_{int(storage_gb)}disk"
        
        if flavor_key not in flavors_necesarios:
            # Este flavor será creado/buscado por el driver
            flavors_necesarios[flavor_key] = {
                "cpus": cpus,
                "ram_gb": ram_gb,
                "disk_gb": storage_gb,
                "nombre": f"custom_{flavor_key}"
            }

        plan.append({
            "nombre_vm": vm_name,
            "worker": worker_ip,  # 👈 Aquí se define el equivalente físico
            "vm_id": vm["idinstancia"],
            "imagen_id": vm.get("imagen_id_openstack", "default-image-id"),
            "flavor_spec": flavors_necesarios[flavor_key],
            "redes": [
                r for r in topologia["redes"]
                if vm_name in r["vms"]
            ],
            "ram_gb": ram_gb,
            "cpus": cpus,
            "disco_gb": storage_gb,
            "salidainternet": vm.get("salidainternet", False)
        })

    print("=" * 60)
    print("PLAN COMPLETO GENERADO")
    print(f"Total VMs en plan: {len(plan)}")
    for vm_plan in plan:
        print(f"   • {vm_plan['nombre_vm']}: {len(vm_plan['redes'])} red(es)")
    print("=" * 60)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "can_deploy": True,
        "platform": "openstack",
        "placement_plan": plan,  # 👈 Este es el que usa deploy_slice_openstack
        "topologia_redes": topologia["redes"],
        "flavors_necesarios": topologia.get("flavors", [])
    }


# Construcción del plan de VM Placement :D
def construir_payload_vm_placement(id_slice: int, zonadisponibilidad: str, instancias: list):
    """
    Construye el JSON que se envía al servicio de VM Placement.
    Este formato debe coincidir con lo que espera tu VM Placement.
    """
    return {
        "id_slice": id_slice,
        "zonadisponibilidad": zonadisponibilidad,
        "instancias": [
            {
                "nombre": inst["nombre"],
                "cpu": int(inst["cpu"]),
                "ram": str(inst["ram"]),
                "storage": str(inst["storage"])
            }
            for inst in instancias
        ]
    }

# ======================================
# ENDPOINT: VERIFICAR VIABILIDAD
# ======================================

@app.post("/placement/verify")
def verificar_viabilidad_endpoint(data: dict = Body(...)):
    """
    Verifica si el slice puede desplegarse.
    Para Linux: verifica recursos de workers.
    Para OpenStack: verifica quotas y disponibilidad de imágenes.
    """
    id_slice = data.get("id_slice")
    platform = data.get("platform", "linux").lower()
    zonadisponibilidad = data.get("zonadisponibilidad", "HP")

    if not id_slice:
        return {"error": "Falta el parámetro 'id_slice'"}

    print(f"🛰️ Evaluando slice {id_slice} para plataforma {platform.upper()}...")
    if not zonadisponibilidad:
        zonadisponibilidad = obtener_zona_disponibilidad(id_slice) or "HP"
    print(f"   Zona de disponibilidad: {zonadisponibilidad}")

    instancias = obtener_instancias_por_slice(id_slice)
    
    if not instancias:
        return {"can_deploy": False, 
                "platform": platform,
                "error": "No se encontraron instancias para el slice."}

    payload = construir_payload_vm_placement(
        id_slice=id_slice,
        zonadisponibilidad=zonadisponibilidad,
        instancias=instancias
    )
    print(f"📤 Enviando request a VM Placement por RabbitMQ: {payload}")

    # 2) Llamar al servicio de VM Placement vía RPC
    try:
        resp_vm = rpc_call_vm_placement(payload, timeout=15)
        print(f"📥 Respuesta de VM Placement: {resp_vm}")
    except Exception as e:
        print(f"Error CONEXIÓN con VM Placement: {e}")
        return {
            "can_deploy": False,
            "platform": platform,
            "error": f"Error comunicando con VM Placement: {str(e)}"
        }

    # 3) Validar respuesta
    if not isinstance(resp_vm, dict):
        return {
            "can_deploy": False,
            "platform": platform,
            "error": "Respuesta inválida desde VM Placement (no es JSON dict)",
            "vm_placement_raw": str(resp_vm)
        }

    if not resp_vm.get("can_deploy", False):
        # VM Placement rechazó el slice
        return {
            "can_deploy": False,
            "platform": platform,
            "error": resp_vm.get("error", "VM Placement rechazó el slice"),
            "vm_placement_raw": resp_vm
        }

    # 4) Si todo OK, devolver el plan
    return {
        "can_deploy": True,
        "platform": platform,
        "placement_plan": resp_vm.get("placement_plan", []),
        "modo": resp_vm.get("modo", "unknown"),
    }
    
def parse_ram_to_gb(ram_str):
    """Convierte RAM en MB o GB a float en GB"""
    ram_str = str(ram_str).strip().upper()
    if "MB" in ram_str:
        return float(ram_str.replace("MB", "")) / 1024
    elif "GB" in ram_str:
        return float(ram_str.replace("GB", ""))
    return 1.0

def generar_plan_verify_linux(id_slice: int, metrics_json: dict, instancias: list):
    """Verificación para Linux (código original)"""
    print("🐧 [LINUX] Verificación de recursos...")
    
    metrics = metrics_json.get("metrics", {})
    workers = []

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
    plan = []
    idx = 0

    for vm in instancias:
        w = workers[idx]
        ram_value = parse_ram_to_gb(vm["ram"])
        cpu_value = int(vm["cpu"])

        w["cpu_free"] = round(w["cpu_free"] - cpu_value, 2)
        w["ram_free"] = round(w["ram_free"] - ram_value, 2)

        plan.append({
            "nombre_vm": vm["nombre"],
            "worker": w["ip"],
            "ram_gb": ram_value,
            "cpus": cpu_value
        })

        idx = (idx + 1) % len(workers)

    puede = all(w["cpu_free"] >= 0 and w["ram_free"] >= 0 for w in workers)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "can_deploy": puede,
        "platform": "linux",
        "placement_plan": plan,
        "workers_status": workers
    }

def generar_plan_verify_openstack(id_slice: int, instancias: list):
    """Verificación para OpenStack"""
    print("☁️ [OPENSTACK] Verificación de disponibilidad...")
    
    # Verificar que todas las imágenes tengan ID de OpenStack
    imagenes_faltantes = []
    for vm in instancias:
        if not vm.get("imagen_id_openstack"):
            imagenes_faltantes.append(vm["imagen_nombre"])
    
    if imagenes_faltantes:
        return {
            "can_deploy": False,
            "platform": "openstack",
            "error": f"Imágenes sin ID de OpenStack: {', '.join(imagenes_faltantes)}",
            "accion_requerida": "Registrar imágenes en OpenStack primero"
        }
    
    # En OpenStack no hay límite estricto de workers, depende de quotas del proyecto
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "can_deploy": True,
        "platform": "openstack",
        "message": "Slice puede desplegarse en OpenStack",
        "instancias": len(instancias),
        "verificacion": "Quotas de OpenStack se verificarán durante el despliegue"
    }

# ======================================
# ENDPOINT: DEPLOY
# ======================================

@app.post("/placement/deploy")
def deploy_slice(data: dict = Body(...)):
    """
    Despliega un slice en la plataforma especificada.
    Soporta: 'linux' y 'openstack'
    """
    id_slice = data.get("id_slice")
    platform = data.get("platform", "linux").lower()
    placement_plan = data.get("placement_plan") 
    modo = data.get("modo", "unknown") 
    
    if not id_slice:
        return {"error": "Falta el parámetro 'id_slice'"}

    if not placement_plan:
        return {
            "success": False,
            "error": "Falta 'placement_plan' en el body. Debes llamar a /placement/verify antes de /placement/deploy.",
            "detalle": "VM Placement es la única fuente de asignación de workers."
        }

    print(f"Iniciando despliegue del slice {id_slice} en {platform.upper()}...")
    print(f"Modo VM Placement: {modo}")
    print(f"   Entradas en placement_plan: {len(placement_plan)}")

    

    # Estado inicial
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE slice 
            SET estado = 'DEPLOYING'
            WHERE idslice = :sid
        """), {"sid": id_slice})

    try:
        instancias = obtener_instancias_por_slice(id_slice)
        if not instancias:
            return {"error": "No se encontraron instancias"}
        
        if platform == "linux":
            return deploy_slice_linux(id_slice, instancias, placement_plan)
        elif platform == "openstack":
            return deploy_slice_openstack(id_slice, instancias, placement_plan)
        else:
            return {"error": f"Plataforma no soportada: {platform}"}
            
    except Exception as e:
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

def limpiar_estado_runtime_slice(id_slice: int):
    """
    Limpia solo el estado de ejecución del slice (para rollback):
    - Borra interfaces_tap asociadas
    - Pone en NULL vnc_idvnc, worker_idworker, process_id, ip
    - Devuelve instancias a estado 'PENDING' (o el que uses como base)
    NO borra instancias, enlaces ni slice.
    """
    try:
        with engine.begin() as conn:
            # Borrar TAPs
            conn.execute(text("""
                DELETE it FROM interfaces_tap it
                JOIN instancia i ON it.instancia_idinstancia = i.idinstancia
                WHERE i.slice_idslice = :sid
            """), {"sid": id_slice})

            # Resetear estado runtime de instancias
            conn.execute(text("""
                UPDATE instancia
                SET vnc_idvnc = NULL,
                    worker_idworker = NULL,
                    process_id = NULL,
                    ip = NULL,
                    estado = 'PENDING'
                WHERE slice_idslice = :sid
            """), {"sid": id_slice})

    except Exception as e:
        print(f"⚠️ Error limpiando estado runtime del slice {id_slice}: {e}")

def deploy_slice_linux(id_slice: int, instancias: list, placement_plan_vm: list | None = None):
    """Despliegue en plataforma Linux"""
    print("[LINUX] Iniciando despliegue...")
    


    plan = generar_plan_deploy_linux(id_slice, instancias, placement_plan_vm)
    
    if not plan.get("can_deploy"):
        return plan

    resultados = []
    fallos = 0
    vms_exitosas = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {}

        for vm in plan["placement_plan"]:
            vm_req = {
                "platform": "linux",
                "nombre_vm": vm["nombre_vm"],
                "worker": vm["worker"],
                "vlans": [str(v) for v in vm["vlans"]],
                "puerto_vnc": str(vm["puerto_vnc"]),
                "imagen": vm["imagen"],
                "ram_gb": float(vm["ram_gb"]),
                "cpus": int(vm["cpus"]),
                "disco_gb": float(vm["disco_gb"])
            }
            
            future = executor.submit(desplegar_vm_en_driver, vm_req)
            future_map[future] = vm

        # 🟢 PROCESAR RESULTADOS COMPLETO (del documento 16)
        for future in as_completed(future_map):
            vm = future_map[future]
            vm_name = vm["nombre_vm"]
            
            try:
                result = future.result()
                print("Resultado del driver:")
                try:
                    print(json.dumps(result, indent=2))
                except:
                    print(result)
                    print("adios")
                if result.get("status") or result.get("success"):
                    print(f"✅ VM {vm_name}: PID {result.get('pid', 'N/A')}")
                    
                    with engine.begin() as conn:
                        # Obtener VNC ID
                        vnc_id = None
                        if vm.get("puerto_vnc"):
                            vnc_query = conn.execute(text("""
                                SELECT idvnc FROM vnc WHERE puerto = :puerto
                            """), {"puerto": vm["puerto_vnc"]})
                            vnc_row = vnc_query.fetchone()
                            vnc_id = vnc_row[0] if vnc_row else None
                        
                        # Obtener Worker ID
                        worker_id = None
                        if vm.get("worker"):
                            worker_query = conn.execute(text("""
                                SELECT idworker FROM worker WHERE ip = :worker_ip
                            """), {"worker_ip": vm["worker"]})
                            worker_row = worker_query.fetchone()
                            worker_id = worker_row[0] if worker_row else None
                            
                            if not worker_id:
                                insert_result = conn.execute(text("""
                                    INSERT INTO worker (nombre, ip, cpu, ram, storage)
                                    VALUES (:nombre, :ip, '4', '8GB', '100GB')
                                """), {
                                    "nombre": next((k for k, v in WORKER_IPS.items() if v == vm['worker']), f"worker_{vm['worker']}"),
                                    "ip": vm['worker']
                                })
                                worker_id = insert_result.lastrowid
                        
                        # Actualizar instancia
                        conn.execute(text("""
                            UPDATE instancia
                            SET estado = 'RUNNING',
                                ip = :ip,
                                vnc_idvnc = :vnc_id,
                                worker_idworker = :worker_id,
                                process_id = :pid,
                                platform = 'linux',
                                console_url = 'no hay'
                            WHERE nombre = :vm_name AND slice_idslice = :sid
                        """), {
                            "ip": vm.get("ip_asignada"),
                            "vnc_id": vnc_id,
                            "worker_id": worker_id,
                            "pid": result.get("pid"),
                            "vm_name": vm_name,
                            "sid": id_slice
                        })
                        
                        # Actualizar VNC
                        if vnc_id:
                            conn.execute(text("""
                                UPDATE vnc SET estado = 'ocupada' WHERE idvnc = :vnc_id
                            """), {"vnc_id": vnc_id})
                        
                        # Marcar VLANs ocupadas
                        for vlan_numero in vm["vlans"]:
                            conn.execute(text("""
                                UPDATE vlan SET estado = 'ocupada' WHERE numero = :vlan_numero
                            """), {"vlan_numero": str(vlan_numero)})
                    
                    # Guardar interfaces TAP
                    stdout = result.get("raw", {}).get("stdout", "") or result.get("stdout", "")
                    interfaces_tap = extraer_interfaces_tap(stdout, vm_name)
                    
                    if interfaces_tap:
                        guardar_interfaces_tap(vm_name, interfaces_tap, id_slice)
                    
                    vms_exitosas.append(vm_name)
                    resultados.append({
                        "vm": vm_name,
                        "worker": vm["worker"],
                        "success": True,
                        "pid": result.get("pid"),
                        "status": "RUNNING"
                    })
                else:
                    fallos += 1
                    with engine.begin() as conn:
                        conn.execute(text("""
                            UPDATE instancia SET estado = 'FAILED'
                            WHERE nombre = :vm_name AND slice_idslice = :sid
                        """), {"vm_name": vm_name, "sid": id_slice})
                    
                    resultados.append({
                        "vm": vm_name,
                        "success": False,
                        "message": result.get("message", "Error desconocido")
                    })
                    
            except Exception as e:
                fallos += 1
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE instancia SET estado = 'FAILED'
                        WHERE nombre = :vm_name AND slice_idslice = :sid
                    """), {"vm_name": vm_name, "sid": id_slice})
                
                resultados.append({
                    "vm": vm_name,
                    "success": False,
                    "message": str(e)
                })

    # Estado final
    estado_final = "RUNNING" if fallos == 0 else ("PARTIAL" if len(vms_exitosas) > 0 else "FAILED")
    
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE slice SET estado = :e WHERE idslice = :sid
        """), {"e": estado_final, "sid": id_slice})
    
    # ================================
    # 🔥 ROLLBACK SI ALGUNA VM FALLA
    # ================================
    if fallos > 0:
        print("🔥 Error detectado: iniciando rollback del slice...")

        # Releer datos completos del slice para tener worker_ip, vnc, etc.
        slice_data = obtener_datos_completos_slice(id_slice)
        instancias_completas = slice_data["instancias"] if slice_data else []

        # Solo eliminar las VMs que sí se desplegaron
        instancias_exitosas = [
            inst for inst in instancias_completas
            if inst["nombre"] in vms_exitosas
        ]

        print(f"🧹 Eliminando {len(instancias_exitosas)} VMs exitosas (rollback)...")

        vm_results = eliminar_vms_paralelo(instancias_exitosas)

        print("🧹 Liberando recursos de red (VLAN/VNC)...")
        network_results = liberar_recursos_red(id_slice)

        print("🧹 Limpiando estado runtime en BD (sin borrar slice)...")
        limpiar_estado_runtime_slice(id_slice)

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE slice SET estado='DRAW'
                WHERE idslice=:sid
            """), {"sid": id_slice})

        return {
            "success": False,
            "slice_id": id_slice,
            "platform": "linux",
            "estado_final": "DRAW",
            "error": "Una o más VMs fallaron, se ejecutó rollback completo.",
            "rollback": {
                "vms_eliminadas": vm_results,
                "recursos_red": network_results
            }
        }

    return {
        "success": fallos == 0,
        "timestamp": datetime.utcnow().isoformat(),
        "slice_id": id_slice,
        "platform": "linux",
        "estado_final": estado_final,
        "resumen": {
            "total_vms": len(plan["placement_plan"]),
            "exitosas": len(vms_exitosas),
            "fallidas": fallos
        },
        "vms_exitosas": vms_exitosas,
        "detalle_completo": resultados
    }

def deploy_slice_openstack(id_slice: int, instancias: list, placement_plan_vm: list | None = None):
    print("☁️ [OPENSTACK] Iniciando despliegue híbrido...")

    if not placement_plan_vm:
        return {
            "success": False,
            "slice_id": id_slice,
            "platform": "openstack",
            "error": "Falta placement_plan. Llama a /placement/verify primero."
        }

    # 1) Generar plan final usando placement físico
    plan = generar_plan_deploy_openstack(id_slice, instancias, placement_plan_vm)

    if not plan.get("can_deploy"):
        return plan

    # 2) Desplegar cada VM en paralelo
    resultados = []
    vms_exitosas = []
    fallos = 0

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(desplegar_vm_en_driver, {
                "platform": "openstack",
                "slice_id": id_slice,
                "nombre_vm": vm["nombre_vm"],
                "vm_id": vm["vm_id"],  # 🔹 AGREGAR vm_id
                "imagen_id": vm["imagen_id"],
                "flavor_spec": vm["flavor_spec"],
                "redes": vm["redes"],
                "salidainternet": vm["salidainternet"]
            }): vm
            for vm in plan["placement_plan"]
        }

        for future in as_completed(future_map):
            vm = future_map[future]
            vm_name = vm["nombre_vm"]
            
            try:
                result = future.result()
                
                if result.get("success"):
                    print(f"✅ VM {vm_name} desplegada en OpenStack")
                    
                    # 🟢 ACTUALIZAR BD CON DATOS DE OPENSTACK
                    with engine.begin() as conn:
                        conn.execute(text("""
                            UPDATE instancia
                            SET estado = 'RUNNING',
                                instance_id = :instance_id,
                                platform = 'openstack',
                                console_url = :console_url
                            WHERE nombre = :vm_name AND slice_idslice = :sid
                        """), {
                            "instance_id": result.get("instance_id"),
                            "console_url": result.get("console_url"),
                            "vm_name": vm_name,
                            "sid": id_slice
                        })
                    
                    vms_exitosas.append(vm_name)
                    resultados.append({
                        "vm": vm_name,
                        "success": True,
                        "instance_id": result.get("instance_id"),
                        "console_url": result.get("console_url"),
                        "networks": result.get("networks", [])
                    })
                else:
                    fallos += 1
                    print(f"❌ VM {vm_name} falló: {result.get('message')}")
                    
                    # 🟢 MARCAR INSTANCIA COMO FAILED
                    with engine.begin() as conn:
                        conn.execute(text("""
                            UPDATE instancia
                            SET estado = 'FAILED'
                            WHERE nombre = :vm_name AND slice_idslice = :sid
                        """), {"vm_name": vm_name, "sid": id_slice})
                    
                    resultados.append({
                        "vm": vm_name,
                        "success": False,
                        "error": result.get("message")
                    })
                    
            except Exception as e:
                fallos += 1
                print(f"❌ Excepción desplegando {vm_name}: {e}")
                
                # 🟢 MARCAR INSTANCIA COMO FAILED
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE instancia
                        SET estado = 'FAILED'
                        WHERE nombre = :vm_name AND slice_idslice = :sid
                    """), {"vm_name": vm_name, "sid": id_slice})
                
                resultados.append({
                    "vm": vm_name,
                    "success": False,
                    "error": str(e)
                })

    # 3) Actualizar estado del slice en BD
    estado_final = "RUNNING" if fallos == 0 else ("PARTIAL" if vms_exitosas else "FAILED")

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE slice 
            SET estado = :e, platform = 'openstack'
            WHERE idslice = :sid
        """), {"e": estado_final, "sid": id_slice})

    return {
        "success": fallos == 0,
        "timestamp": datetime.utcnow().isoformat(),
        "slice_id": id_slice,
        "platform": "openstack",
        "estado_final": estado_final,
        "resumen": {
            "total_vms": len(plan["placement_plan"]),
            "exitosas": len(vms_exitosas),
            "fallidas": fallos,
            "porcentaje_exito": round((len(vms_exitosas) / len(plan["placement_plan"])) * 100, 2)
        },
        "vms_exitosas": vms_exitosas,
        "topologia_redes": plan["topologia_redes"],
        "flavors_creados": plan.get("flavors_necesarios", []),
        "detalle_completo": resultados,
        "message": f"Despliegue {'completo' if fallos == 0 else 'parcial' if len(vms_exitosas) > 0 else 'fallido'} del slice {id_slice} en OpenStack"
    }


def desplegar_vm_en_driver(vm_data: dict):
    """
    Envía petición al Driver Híbrido (Linux o OpenStack según platform)
    """
    platform = vm_data.get("platform", "linux")
    url = f"{LINUX_DRIVER_URL}/create_vm"
    
    try:
        print(f"[HTTP] → POST {url} (Platform: {platform.upper()})")
        print(f"[HTTP] VM: {vm_data.get('nombre_vm')}")
        
        resp = requests.post(url, json=vm_data, timeout=300)  # Timeout mayor para OpenStack
        raw = resp.text
        
        print(f"[HTTP] ← {resp.status_code}")
        
        if resp.status_code != 200:
            return {
                "success": False, 
                "message": f"HTTP {resp.status_code}: {raw[:200]}"
            }
        
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return {
                "success": False, 
                "message": f"Respuesta no es JSON: {raw[:200]}"
            }
        
        success = bool(data.get("success", data.get("status", False)))
        
        return data
        
    except requests.exceptions.Timeout:
        return {"success": False, "message": f"Timeout desplegando VM (platform: {platform})"}
    except Exception as e:
        return {"success": False, "message": f"Error de conexión: {str(e)}"}

# ======================================
# ENDPOINT: DELETE (Híbrido)
# ======================================

@app.post("/placement/delete")
def delete_slice(data: dict = Body(...)):
    """
    Elimina un slice de cualquier plataforma
    """
    id_slice = data.get("id_slice")
    if not id_slice:
        return {"error": "Falta el parámetro 'id_slice'"}

    print(f"🗑️ Iniciando eliminación del slice {id_slice}...")

    # Verificar plataforma del slice
    with engine.connect() as conn:
        platform_query = text("""
            SELECT DISTINCT i.platform 
            FROM instancia i 
            WHERE i.slice_idslice = :sid 
            LIMIT 1
        """)
        result = conn.execute(platform_query, {"sid": id_slice})
        row = result.fetchone()
        platform = row[0] if row and row[0] else "linux"
    
    print(f"📊 Plataforma detectada: {platform.upper()}")

    # Estado inicial
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE slice 
            SET estado = 'DELETING'
            WHERE idslice = :sid
        """), {"sid": id_slice})

    try:
        slice_data = obtener_datos_completos_slice(id_slice)
        
        if not slice_data:
            return {"error": "No se pudieron obtener los datos del slice"}
        
        if platform == "linux":
            return delete_slice_linux(id_slice, slice_data)
        elif platform == "openstack":
            return delete_slice_openstack(id_slice, slice_data)
        else:
            return {"error": f"Plataforma desconocida: {platform}"}
            
    except Exception as e:
        print(f"❌ Error durante eliminación: {e}")
        return {
            "success": False,
            "error": str(e),
            "slice_id": id_slice
        }

def delete_slice_linux(id_slice: int, slice_data: dict):
    """Eliminación en plataforma Linux (código original)"""
    print("🐧 [LINUX] Eliminando slice...")
    
    # Código original de eliminación
    vm_results = eliminar_vms_paralelo(slice_data["instancias"])
    network_results = liberar_recursos_red(id_slice)
    db_results = limpiar_registros_bd(id_slice)
    
    return generar_reporte_eliminacion(
        id_slice, vm_results, network_results, db_results, "linux"
    )

def delete_slice_openstack(id_slice: int, slice_data: dict):
    """
    Eliminación en plataforma OpenStack mediante eliminación del proyecto completo.
    
    En OpenStack, un slice corresponde a un proyecto, por lo que eliminando
    el proyecto se eliminan automáticamente todas las VMs, redes, puertos,
    routers y demás recursos asociados.
    """
    print("[OPENSTACK] Eliminando slice completo...")
    
    # Obtener nombre del slice para construir el nombre del proyecto
    slice_info = slice_data.get("slice_info", {})
    slice_nombre = slice_info.get("nombre", f"slice_{id_slice}")
    project_name = f"slice_{id_slice}"  # Formato usado en deploy
    
    print(f"Proyecto a eliminar: {project_name}")
    print(f"VMs asociadas: {len(slice_data.get('instancias', []))}")
    
    # Preparar argumentos para el script de eliminación
    delete_args = {
        "action": "delete_project",
        "project_name": project_name,
        "slice_id": id_slice
    }
    
    # Ejecutar script de eliminación en headnode
    try:
        # Usar el helper del driver para ejecutar el script bash
        url = f"{LINUX_DRIVER_URL}/delete_project_openstack"
        
        resp = requests.post(url, json=delete_args, timeout=180)
        
        if resp.status_code != 200:
            print(f"Error HTTP {resp.status_code}: {resp.text}")
            return {
                "success": False,
                "slice_id": id_slice,
                "platform": "openstack",
                "error": f"Error al comunicar con driver: HTTP {resp.status_code}",
                "message": "Fallo en comunicación con OpenStack headnode"
            }
        
        result = resp.json()
        
        if result.get("success"):
            print(f"Proyecto {project_name} eliminado exitosamente")
            
            # Limpiar registros de base de datos
            db_results = limpiar_registros_bd(id_slice)
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "slice_id": id_slice,
                "platform": "openstack",
                "project_name": project_name,
                "resumen": {
                    "proyecto_eliminado": True,
                    "vms_eliminadas": len(slice_data.get("instancias", [])),
                    "recursos_liberados": "Todos los recursos del proyecto eliminados automáticamente"
                },
                "base_datos": db_results,
                "details": result.get("details", {}),
                "message": f"Slice {id_slice} ({project_name}) eliminado completamente de OpenStack"
            }
        else:
            error_msg = result.get("error", "Error desconocido")
            print(f"Fallo al eliminar proyecto: {error_msg}")
            
            return {
                "success": False,
                "slice_id": id_slice,
                "platform": "openstack",
                "project_name": project_name,
                "error": error_msg,
                "message": f"No se pudo eliminar el proyecto {project_name}",
                "details": result.get("details", {})
            }
            
    except requests.exceptions.Timeout:
        print(f"Timeout eliminando proyecto {project_name}")
        return {
            "success": False,
            "slice_id": id_slice,
            "platform": "openstack",
            "error": "Timeout al eliminar proyecto (>180s)",
            "message": "La operación tardó demasiado, verifique manualmente"
        }
    except Exception as e:
        print(f"Excepción inesperada: {e}")
        return {
            "success": False,
            "slice_id": id_slice,
            "platform": "openstack",
            "error": str(e),
            "message": "Error crítico durante eliminación"
        }


def obtener_datos_completos_slice(id_slice: int):
    """Obtiene todos los datos del slice (código original)"""
    try:
        with engine.connect() as conn:
            slice_query = text("""
                SELECT s.idslice, s.nombre, s.estado, s.topologia
                FROM slice s
                WHERE s.idslice = :id_slice
            """)
            slice_result = conn.execute(slice_query, {"id_slice": id_slice})
            slice_info = slice_result.fetchone()
            
            if not slice_info:
                return None
            
            instancias_query = text("""
                SELECT 
                    i.idinstancia, i.nombre, i.estado, i.cpu, i.ram, i.storage,
                    i.salidainternet, i.ip, i.worker_idworker, i.process_id,
                    i.platform, i.instance_id,
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
        print(f"❌ Error obteniendo datos: {e}")
        return None

def eliminar_vms_paralelo(instancias: list):
    """Elimina VMs de Linux (código original)"""
    results = []
    
    if not instancias:
        return {"vms_eliminadas": 0, "errores": 0, "detalles": []}
    
    print(f"🔧 Eliminando {len(instancias)} VMs de Linux...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_vm = {}
        
        for instancia in instancias:
            if instancia.get("worker_ip"):
                future = executor.submit(eliminar_vm_individual_linux, instancia)
                future_to_vm[future] = instancia
        
        vms_eliminadas = 0
        errores = 0
        
        for future in as_completed(future_to_vm):
            instancia = future_to_vm[future]
            try:
                result = future.result()
                results.append({
                    "vm_nombre": instancia["nombre"],
                    "worker": instancia["worker_ip"],
                    "success": result["success"],
                    "message": result["message"]
                })
                
                if result["success"]:
                    vms_eliminadas += 1
                else:
                    errores += 1
                    
            except Exception as e:
                errores += 1
                results.append({
                    "vm_nombre": instancia["nombre"],
                    "success": False,
                    "message": str(e)
                })
    
    return {
        "vms_eliminadas": vms_eliminadas,
        "errores": errores,
        "total": len(instancias),
        "detalles": results
    }

def eliminar_vm_individual_linux(instancia: dict):
    """Elimina VM de Linux (código original)"""
    url = f"{LINUX_DRIVER_URL}/delete_vm"
    
    interfaces_tap = []
    try:
        with engine.connect() as conn:
            tap_query = text("""
                SELECT nombre_interfaz 
                FROM interfaces_tap 
                WHERE instancia_idinstancia = :inst_id
            """)
            result = conn.execute(tap_query, {"inst_id": instancia["idinstancia"]})
            interfaces_tap = [row[0] for row in result]
    except Exception as e:
        print(f"⚠️ Error obteniendo TAPs: {e}")
    
    vm_data = {
        "platform": "linux",
        "nombre_vm": instancia["nombre"],
        "worker_ip": instancia["worker_ip"],
        "vm_id": instancia["idinstancia"],
        "vnc_puerto": instancia.get("vnc_puerto"),
        "process_id": instancia.get("process_id"),
        "interfaces_tap": interfaces_tap,
        "delete_disk": True 
    }
    
    try:
        resp = requests.post(url, json=vm_data, timeout=60)
        
        if resp.status_code != 200:
            return {"success": False, "message": f"HTTP {resp.status_code}"}
        
        data = resp.json()
        success = bool(data.get("success", data.get("status", False)))
        message = data.get("mensaje") or data.get("message") or "VM eliminada"
        
        return {"success": success, "message": message}
        
    except Exception as e:
        return {"success": False, "message": str(e)}

def liberar_recursos_red(id_slice: int):
    """Libera VLANs y VNCs (solo Linux)"""
    results = {
        "vlans_liberadas": 0,
        "vncs_liberados": 0,
        "errores": []
    }
    
    try:
        with engine.begin() as conn:
            # Liberar VLANs
            vlans_result = conn.execute(text("""
                UPDATE vlan v
                JOIN enlace e ON v.idvlan = e.vlan_idvlan
                SET v.estado = 'disponible'
                WHERE e.slice_idslice = :sid
            """), {"sid": id_slice})
            results["vlans_liberadas"] = vlans_result.rowcount
            
            # Liberar VNCs
            vnc_result = conn.execute(text("""
                UPDATE vnc v
                JOIN instancia i ON v.idvnc = i.vnc_idvnc
                SET v.estado = 'disponible'
                WHERE i.slice_idslice = :sid
            """), {"sid": id_slice})
            results["vncs_liberados"] = vnc_result.rowcount
        
        return results
    except Exception as e:
        results["errores"].append(str(e))
        return results

def limpiar_registros_bd(id_slice: int):
    """Limpia registros de BD (común para ambas plataformas)"""
    results = {
        "enlaces_eliminados": 0,
        "interfaces_tap_eliminadas": 0,
        "instancias_eliminadas": 0,
        "relaciones_eliminadas": 0,
        "slice_eliminado": False,
        "errores": []
    }
    
    try:
        with engine.begin() as conn:
            # Enlaces
            enlaces_result = conn.execute(text("""
                DELETE FROM enlace WHERE slice_idslice = :sid
            """), {"sid": id_slice})
            results["enlaces_eliminados"] = enlaces_result.rowcount
            
            # Interfaces TAP
            tap_result = conn.execute(text("""
                DELETE it FROM interfaces_tap it
                JOIN instancia i ON it.instancia_idinstancia = i.idinstancia
                WHERE i.slice_idslice = :sid
            """), {"sid": id_slice})
            results["interfaces_tap_eliminadas"] = tap_result.rowcount
            
            # Limpiar FKs de instancias
            conn.execute(text("""
                UPDATE instancia 
                SET vnc_idvnc = NULL, worker_idworker = NULL 
                WHERE slice_idslice = :sid
            """), {"sid": id_slice})
            
            # Instancias
            inst_result = conn.execute(text("""
                DELETE FROM instancia WHERE slice_idslice = :sid
            """), {"sid": id_slice})
            results["instancias_eliminadas"] = inst_result.rowcount
            
            # Relaciones usuario-slice
            rel_result = conn.execute(text("""
                DELETE FROM usuario_has_slice WHERE slice_idslice = :sid
            """), {"sid": id_slice})
            results["relaciones_eliminadas"] = rel_result.rowcount
            
            # Slice
            slice_result = conn.execute(text("""
                DELETE FROM slice WHERE idslice = :sid
            """), {"sid": id_slice})
            results["slice_eliminado"] = slice_result.rowcount > 0
            
        return results
    except Exception as e:
        results["errores"].append(str(e))
        return results

def generar_reporte_eliminacion(id_slice: int, vm_results: dict, 
                                 network_results: dict, db_results: dict, 
                                 platform: str):
    """Genera reporte de eliminación"""
    total_ops = (
        vm_results["vms_eliminadas"] + 
        network_results.get("vlans_liberadas", 0) +
        network_results.get("vncs_liberados", 0) +
        db_results["enlaces_eliminados"] +
        db_results["interfaces_tap_eliminadas"] +
        db_results["instancias_eliminadas"]
    )
    
    total_errores = vm_results["errores"] + len(db_results["errores"])
    success = total_errores == 0 and db_results["slice_eliminado"]
    
    return {
        "success": success,
        "slice_id": id_slice,
        "platform": platform,
        "timestamp": datetime.utcnow().isoformat(),
        "resumen": {
            "total_operaciones": total_ops,
            "errores": total_errores,
            "slice_eliminado": success
        },
        "vms": vm_results,
        "recursos_red": network_results,
        "base_datos": db_results,
        "message": f"Slice {id_slice} ({'completamente eliminado' if success else 'eliminado con errores'}) de {platform.upper()}"
    }

# Funciones auxiliares adicionales del código original
def extraer_interfaces_tap(stdout: str, nombre_vm: str):
    """Extrae interfaces TAP del stdout"""
    interfaces = []
    if not stdout:
        return interfaces
    
    lineas = stdout.split('\n')
    for linea in lineas:
        if 'Interfaz TAP' in linea and 'creada' in linea:
            partes = linea.split()
            for i, parte in enumerate(partes):
                if parte == 'TAP' and i + 1 < len(partes):
                    interfaces.append(partes[i + 1])
                    break
    
    return interfaces

def guardar_interfaces_tap(nombre_vm: str, interfaces: list, id_slice: int):
    """Guarda interfaces TAP en BD"""
    try:
        with engine.begin() as conn:
            inst_query = text("""
                SELECT idinstancia, worker_idworker
                FROM instancia 
                WHERE nombre = :vm_name AND slice_idslice = :sid
            """)
            result = conn.execute(inst_query, {"vm_name": nombre_vm, "sid": id_slice})
            row = result.fetchone()
            
            if not row or not row[1]:
                return 0
            
            inst_id, worker_id = row[0], row[1]
            
            count = 0
            for nombre_interfaz in interfaces:
                conn.execute(text("""
                    INSERT INTO interfaces_tap (nombre_interfaz, instancia_idinstancia, worker_idworker)
                    VALUES (:nombre, :inst_id, :worker_id)
                """), {
                    "nombre": nombre_interfaz,
                    "inst_id": inst_id,
                    "worker_id": worker_id
                })
                count += 1
            
            return count
    except Exception as e:
        print(f"❌ Error guardando TAPs: {e}")
        return 0

# ======================================
# ENDPOINT RAÍZ
# ======================================

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Slice Manager Hybrid v4.0",
        "supported_platforms": ["linux", "openstack"],
        "endpoints": {
            "/placement/verify": "POST - Verificar viabilidad",
            "/placement/deploy": "POST - Desplegar slice",
            "/placement/delete": "POST - Eliminar slice"
        }
    }

# ======================================
# MAIN
# ======================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Slice Manager Hybrid escuchando en 0.0.0.0:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)