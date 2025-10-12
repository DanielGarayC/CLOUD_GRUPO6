#!/usr/bin/env python3
import psutil
import socket
import json
import time
import requests
from datetime import datetime

# ===========================
# CONFIGURACIÓN
# ===========================
HEADNODE_URL = "http://10.0.10.1:5000/metrics"  # IP del Headnode
INTERVAL = 10  # segundos entre envíos (igual en todos los workers)

# ===========================
# FUNCIÓN: obtener métricas del worker
# ===========================
def get_metrics():
    qemu_count = len([p for p in psutil.process_iter(['name']) if 'qemu' in (p.info['name'] or '')])
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    return {
        "hostname": socket.gethostname(),
        "timestamp_sent": datetime.utcnow().isoformat(),          # Hora UTC exacta del envío
        "cpu_percent": psutil.cpu_percent(interval=1),            # Uso CPU (%)
        "cpu_count": psutil.cpu_count(logical=True),              # Núcleos
        "ram_percent": mem.percent,                               # Uso RAM (%)
        "ram_total_gb": round(mem.total / (1024**3), 2),          # RAM total
        "disk_percent": disk.percent,                             # Uso disco (%)
        "disk_free_gb": round(disk.free / (1024**3), 2),          # Disco libre
        "qemu_count": qemu_count                                  # Cantidad de VMs (procesos qemu)
    }

# ===========================
# FUNCIÓN: enviar métricas
# ===========================
def send_to_headnode(data):
    try:
        response = requests.post(HEADNODE_URL, json=data, timeout=5)
        if response.status_code == 200:
            print(f"✅ [{data['hostname']}] Métricas enviadas correctamente.")
        else:
            print(f"⚠️ [{data['hostname']}] Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ [{data['hostname']}] Error al enviar datos: {e}")

# ===========================
# LOOP PRINCIPAL
# ===========================
if __name__ == "__main__":
    hostname = socket.gethostname()
    print(f"  Daemon iniciado en {hostname}. Enviando métricas cada {INTERVAL}s...")

    # Sincronizar inicio para que todos los workers envíen a la vez (en segundos múltiplos del INTERVAL)
    drift = time.time() % INTERVAL
    if drift > 0:
        time.sleep(INTERVAL - drift)

    while True:
        metrics = get_metrics()
        send_to_headnode(metrics)

        # Esperar hasta el siguiente ciclo exacto
        drift = time.time() % INTERVAL
        time.sleep(INTERVAL - drift)
