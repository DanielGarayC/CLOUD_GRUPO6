import psutil
import socket
import json
import time
from datetime import datetime

HEADNODE_IP = "10.0.10.1"
PORT = 5000
INTERVAL = 10  # luego podrás bajar a 1

def get_metrics():
    return {
        "hostname": socket.gethostname(),
        "timestamp": datetime.utcnow().isoformat(),  
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('/').percent,
        "load": psutil.getloadavg()
    }

def send_to_headnode(data):
    import requests
    try:
        r = requests.post(f"http://{HEADNODE_IP}:{PORT}/metrics", json=data)
        r.raise_for_status()
        print(f"✅ Datos enviados: {data['timestamp']}")
    except Exception as e:
        print(f"❌ Error al enviar datos: {e}")

while True:
    sleep_time = INTERVAL - (time.time() % INTERVAL)
    time.sleep(sleep_time)                
    metrics = get_metrics()
    send_to_headnode(metrics)
