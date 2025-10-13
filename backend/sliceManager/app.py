from fastapi import FastAPI, Body
from datetime import datetime
from sqlalchemy import create_engine, text
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
MONITORING_URL = "http://10.0.10.1:5010/metrics"

# Mapeo estático de workers
WORKER_IPS = {
    "server2": "10.0.0.2",
    "server3": "10.0.0.3",
    "server4": "10.0.0.4"
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
        SELECT i.idinstancia, i.nombre, i.cpu, i.ram, i.storage, im.ruta AS imagen
        FROM instancia i
        JOIN imagen im ON i.imagen_idimagen = im.idimagen
        WHERE i.slice_idslice = :id_slice
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"id_slice": id_slice})
        return [dict(row._mapping) for row in result]


# ======================================
# FUNCIÓN: generar plan de despliegue
# ======================================
def generar_plan_deploy(metrics_json: dict, instancias: list):
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
    for vm in instancias:
        w = workers[idx]
        ram_value = float(str(vm["ram"]).replace("GB", "").strip())
        storage_value = float(str(vm["storage"]).replace("GB", "").strip())

        plan.append({
            "nombre_vm": vm["nombre"],
            "worker": w["ip"],
            "imagen": vm["imagen"],
            "ram_gb": ram_value,
            "cpus": int(vm["cpu"]),
            "disco_gb": storage_value
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

    resultado = generar_plan_deploy(metrics, instancias)
    print(json.dumps(resultado, indent=2))
    return resultado


# ======================================
# ENDPOINT raíz
# ======================================
@app.get("/")
def root():
    return {"status": "ok", "message": "Slice Manager operativo en el Headnode"}


# ======================================
# MAIN
# ======================================
if __name__ == "__main__":
    import uvicorn
    print("  Slice Manager escuchando en 0.0.0.0:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
