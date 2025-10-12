from fastapi import FastAPI, Body
from datetime import datetime
import requests
import json

app = FastAPI()

# ====================================
# CONFIGURACIÓN
# ====================================
MONITORING_URL = "http://10.0.10.1:5000/metrics"  # Servicio de monitoreo remoto


# ====================================
# FUNCIÓN: Obtener métricas del servicio de monitoreo
# ====================================
def obtener_metricas_actuales():
    """
    Consume el endpoint /metrics del servicio de monitoreo.
    Devuelve el JSON con las métricas actuales de todos los workers.
    """
    try:
        response = requests.get(MONITORING_URL, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Error {response.status_code} al obtener métricas: {response.text}")
            return None
    except Exception as e:
        print(f"❌ No se pudo conectar con el servicio de monitoreo: {e}")
        return None


# ====================================
# FUNCIÓN: Verificar viabilidad del slice (Round Robin)
# ====================================
def verificar_viabilidad(metrics_json: dict, vms_list: list):
    """
    Evalúa si el slice puede desplegarse con los recursos actuales.
    Aplica una asignación round-robin teórica.
    """
    metrics = metrics_json.get("metrics", {})
    if not metrics:
        return {"can_deploy": False, "error": "No se encontraron métricas de workers."}

    # --- Calcular recursos disponibles por worker ---
    workers = []
    for host, data in metrics.items():
        cpu_total = data["cpu_count"]
        cpu_free = cpu_total * (1 - data["cpu_percent"] / 100)
        ram_free = data["ram_total_gb"] * (1 - data["ram_percent"] / 100)
        workers.append({
            "nombre": host,
            "cpu_free": round(cpu_free, 2),
            "ram_free": round(ram_free, 2)
        })

    # --- Ordenar workers y VMs ---
    workers.sort(key=lambda w: w["nombre"])
    vms_sorted = sorted(vms_list, key=lambda vm: vm["id"])

    # --- Asignación round robin ---
    idx = 0
    plan = []
    for vm in vms_sorted:
        worker = workers[idx]
        plan.append({"vm": vm["nombre"], "asignado_a": worker["nombre"]})

        worker["cpu_free"] -= vm["cpu"]
        worker["ram_free"] -= vm["ram_gb"]
        idx = (idx + 1) % len(workers)

    # --- Verificar si todos los workers tienen recursos suficientes ---
    puede = all(w["cpu_free"] >= 0 and w["ram_free"] >= 0 for w in workers)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "can_deploy": puede,
        "workers_status": workers,
        "placement_plan": plan
    }

# ====================================
# ENDPOINT: Evaluar slice
# ====================================
@app.post("/placement/verify")
def verificar_viabilidad_endpoint(vms: list = Body(...)):
    """
    Evalúa si el slice puede desplegarse con el estado actual de los workers.
    No despliega, solo simula.
    """
    print("🛰️ Evaluando slice..." )
    metrics = obtener_metricas_actuales()
    if not metrics:
        return {"can_deploy": False, "error": "No se pudo obtener métricas del servicio de monitoreo."}

    resultado = verificar_viabilidad(metrics, vms)
    print(json.dumps(resultado, indent=2))
    return resultado


# ====================================
# ENDPOINT: Estado del servicio
# ====================================
@app.get("/")
def root():
    return {"status": "ok", "message": "Slice Manager operativo en el Headnode"}


# ====================================
# EJECUTAR SLICE MANAGER
# ====================================
if __name__ == "__main__":
    import uvicorn
    print("  Slice Manager escuchando en 0.0.0.0:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
