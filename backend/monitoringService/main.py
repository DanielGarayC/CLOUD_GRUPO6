from fastapi import FastAPI, Request
from typing import Dict
import time

app = FastAPI()

# Estructura en memoria para las métricas de los workers
workers_metrics: Dict[str, dict] = {}

@app.post("/metrics")
async def receive_metrics(request: Request):
    """
    Recibe las métricas enviadas por el daemon de cada Worker.
    """
    data = await request.json()
    hostname = data.get("hostname", f"worker_{len(workers_metrics)+1}")

    workers_metrics[hostname] = {
        "cpu": data.get("cpu"),
        "ram": data.get("ram"),
        "disk": data.get("disk"),
        "load": data.get("load"),
        "timestamp": time.time()
    }

    return {"message": f"Métricas recibidas de {hostname}"}

@app.get("/metrics")
def list_metrics():
    """
    Devuelve las métricas actuales de todos los workers.
    El placement_service consultará este endpoint.
    """
    return workers_metrics
