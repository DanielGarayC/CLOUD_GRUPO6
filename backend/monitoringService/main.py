from fastapi import FastAPI, Request
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import asyncio

app = FastAPI()

# ===========================
# ESTRUCTURA EN MEMORIA
# ===========================
# Diccionario con la última métrica recibida por cada worker
latest_metrics = {}

# ===========================
# ENDPOINT: recibir métricas de cada worker
# ===========================
@app.post("/metrics")
async def receive_metrics(request: Request):
    data = await request.json()
    hostname = data.get("hostname", "unknown")
    data["received_at"] = datetime.now(ZoneInfo("America/Lima")).isoformat()
    latest_metrics[hostname] = data   # almacena la última métrica de este worker

    print(f"📡 Métricas recibidas de {hostname}: CPU={data.get('cpu_percent')}%, RAM={data.get('ram_percent')}%")
    return {"status": "ok", "worker": hostname}

# ===========================
# ENDPOINT: devolver métricas actuales de todos los workers
# ===========================
@app.get("/metrics")
def get_latest_metrics():
    """
    Devuelve la última métrica conocida de cada worker.
    Ejemplo:
    curl http://192.168.201.1:5010/metrics
    """
    if not latest_metrics:
        return {"status": "no_data", "message": "Aún no se han recibido métricas."}

    now = datetime.utcnow().isoformat()
    return {
        "timestamp": now,
        "workers_count": len(latest_metrics),
        "metrics": latest_metrics
    }

# ===========================
# EJECUTAR HEADNODE
# ===========================
if __name__ == "__main__":
    import uvicorn
    print("🟢 Headnode escuchando en 0.0.0.0:5010...")
    uvicorn.run(app, host="0.0.0.0", port=5010)

