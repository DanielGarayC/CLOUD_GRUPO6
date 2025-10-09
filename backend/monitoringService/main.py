from fastapi import FastAPI, Request
import json
import os
from datetime import datetime

app = FastAPI()

LOG_DIR = "logs_metrics"
os.makedirs(LOG_DIR, exist_ok=True)

current_day = datetime.utcnow().strftime("%Y-%m-%d")
log_file_path = os.path.join(LOG_DIR, f"metrics_{current_day}.txt")

@app.post("/metrics")
async def receive_metrics(request: Request):
    global current_day, log_file_path
    
    data = await request.json()
    timestamp = datetime.utcnow().isoformat()
    data["received_at"] = timestamp  # por si quieres diferenciar envío y recepción

    # Verificar cambio de día
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if today != current_day:
        current_day = today
        log_file_path = os.path.join(LOG_DIR, f"metrics_{current_day}.txt")
        # Reinicia el archivo (nueva jornada)
        open(log_file_path, 'w').close()

    # Guardar línea JSON
    with open(log_file_path, "a") as f:
        f.write(json.dumps(data) + "\n")

    return {"status": "ok", "saved_in": log_file_path}

@app.get("/metrics")
def read_metrics(date: str = None):
    """
    Permite consultar métricas de un día específico.
    GET /metrics?date=2025-10-07
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    file_path = os.path.join(LOG_DIR, f"metrics_{date}.txt")
    if not os.path.exists(file_path):
        return {"error": f"No hay datos para {date}"}

    with open(file_path, "r") as f:
        lines = [json.loads(line) for line in f]

    return {"date": date, "count": len(lines), "metrics": lines}