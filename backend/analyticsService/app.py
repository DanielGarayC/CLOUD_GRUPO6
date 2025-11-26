from fastapi import FastAPI
from fastapi.responses import Response
from datetime import datetime
from sqlalchemy import create_engine, text
import requests
import csv
import os
from pathlib import Path
from typing import Optional

app = FastAPI(title="Analytics Service", version="1.0")

# ======================================
# CONFIGURACIÓN
# ======================================
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "root")
DB_HOST = os.getenv("DB_HOST", "slice_db")
DB_NAME = os.getenv("DB_NAME", "mydb")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

MONITORING_URL = os.getenv("MONITORING_URL", "http://monitoring_service:5010/metrics")

# Directorio para almacenar métricas
METRICS_STORAGE_DIR = Path("/app/metrics_storage")
METRICS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# ======================================
# FUNCIONES AUXILIARES
# ======================================

def parse_resource_value(value: str, resource_type: str) -> float:
    """Parsear valores como '8GB', '100GB', '4' a números"""
    if not value:
        return 0.0
    
    value = str(value).upper().strip()
    
    # CPU es solo número
    if resource_type == 'cpu':
        return float(value)
    
    # RAM y Storage pueden tener GB/MB
    if 'GB' in value:
        return float(value.replace('GB', '').strip())
    elif 'MB' in value:
        return float(value.replace('MB', '').strip()) / 1024
    else:
        return float(value)

def obtener_capacidad_total_workers():
    """Obtiene la capacidad TOTAL configurada de cada worker desde la BD"""
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    nombre,
                    ip,
                    cpu,
                    ram,
                    storage
                FROM worker
                WHERE nombre IN ('server2', 'server3', 'server4','worker1','worker2','worker3')
            """)
            
            result = conn.execute(query)
            capacidades = {}
            
            for row in result:
                capacidades[row.nombre] = {
                    "ip": row.ip,
                    "cpu_total": int(parse_resource_value(row.cpu, 'cpu')),
                    "ram_total_gb": parse_resource_value(row.ram, 'ram'),
                    "storage_total_gb": parse_resource_value(row.storage, 'storage')
                }
            
            return capacidades
            
    except Exception as e:
        print(f"❌ Error obteniendo capacidades: {e}")
        return {}

def obtener_recursos_utilizados_bd():
    """
    Calcula recursos UTILIZADOS por instancias en slices RUNNING únicamente
    """
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    w.nombre as worker_nombre,
                    w.ip as worker_ip,
                    SUM(CAST(REPLACE(i.cpu, ' ', '') AS UNSIGNED)) as cpu_utilizado,
                    SUM(
                        CASE 
                            WHEN i.ram LIKE '%GB%' THEN CAST(REPLACE(REPLACE(i.ram, 'GB', ''), ' ', '') AS DECIMAL(10,2))
                            WHEN i.ram LIKE '%MB%' THEN CAST(REPLACE(REPLACE(i.ram, 'MB', ''), ' ', '') AS DECIMAL(10,2)) / 1024
                            ELSE CAST(i.ram AS DECIMAL(10,2))
                        END
                    ) as ram_utilizado_gb,
                    SUM(
                        CAST(REPLACE(REPLACE(i.storage, 'GB', ''), ' ', '') AS DECIMAL(10,2))
                    ) as storage_utilizado_gb,
                    COUNT(i.idinstancia) as num_instancias_running,
                    GROUP_CONCAT(CONCAT(s.nombre, ' (', i.nombre, ')') SEPARATOR ', ') as slices_instancias
                FROM instancia i
                JOIN slice s ON i.slice_idslice = s.idslice
                LEFT JOIN worker w ON i.worker_idworker = w.idworker
                WHERE s.estado = 'RUNNING'
                  AND w.nombre IS NOT NULL
                GROUP BY w.nombre, w.ip
            """)
            
            result = conn.execute(query)
            recursos_utilizados = {}
            
            for row in result:
                recursos_utilizados[row.worker_nombre] = {
                    "ip": row.worker_ip,
                    "cpu_utilizado": float(row.cpu_utilizado or 0),
                    "ram_utilizado_gb": float(row.ram_utilizado_gb or 0),
                    "storage_utilizado_gb": float(row.storage_utilizado_gb or 0),
                    "num_instancias_running": int(row.num_instancias_running or 0),
                    "slices_instancias": row.slices_instancias or ""
                }
            
            print(f"📊 Recursos utilizados (RUNNING): {recursos_utilizados}")
            return recursos_utilizados
            
    except Exception as e:
        print(f"❌ Error obteniendo recursos utilizados: {e}")
        return {}

def obtener_metricas_actuales():
    """Obtiene métricas en tiempo real del monitoring service"""
    try:
        resp = requests.get(MONITORING_URL, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"⚠️ Error {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        print(f"❌ No se pudo conectar con monitoring service: {e}")
        return None

def guardar_metricas_snapshot(metricas: dict, recursos_utilizados: dict):
    """
    Guarda un snapshot de las métricas actuales en CSV
    SE GUARDA CADA VEZ que se consulta /resources/summary
    """
    try:
        fecha = datetime.utcnow().strftime("%Y-%m-%d")
        timestamp = datetime.utcnow(). strftime("%Y-%m-%d %H:%M:%S")
        
        # Archivo CSV por día
        csv_file = METRICS_STORAGE_DIR / f"metrics_snapshot_{fecha}.csv"
        
        # Verificar si el archivo existe para escribir header
        file_exists = csv_file.exists()
        
        with open(csv_file, 'a', newline='') as f:
            fieldnames = [
                'timestamp', 'worker_nombre', 'worker_ip',
                # Capacidad total (real desde métricas)
                'cpu_total', 'ram_total_gb', 'storage_total_gb',
                # Recursos utilizados (BD - RUNNING slices)
                'cpu_utilizado_bd', 'ram_utilizado_bd_gb', 'storage_utilizado_bd_gb', 
                'instancias_running', 'slices_detalle',
                # Métricas del sistema (USO REAL)
                'cpu_percent_sistema', 'ram_percent_sistema', 'disk_percent_sistema',
                'ram_sistema_gb', 'disk_free_gb', 'qemu_count'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer. writeheader()
            
            # Escribir una fila por worker
            if metricas and 'metrics' in metricas:
                for worker_nombre, data in metricas['metrics'].items():
                    utilizados = recursos_utilizados.get(worker_nombre, {})
                    
                    ram_total = data.get('ram_total_gb', 0)
                    ram_percent = data.get('ram_percent', 0)
                    ram_sistema = (ram_total * ram_percent / 100) if ram_total > 0 else 0
                    
                    # Calcular disco total real
                    disk_free = data.get('disk_free_gb', 0)
                    disk_percent = data.get('disk_percent', 0)
                    if disk_percent < 100 and disk_percent > 0:
                        disk_total = disk_free / (1 - disk_percent / 100)
                    else:
                        disk_total = 10
                    
                    writer.writerow({
                        'timestamp': timestamp,
                        'worker_nombre': worker_nombre,
                        'worker_ip': utilizados.get('ip', 'N/A'),
                        # Capacidad real
                        'cpu_total': data.get('cpu_count', 0),
                        'ram_total_gb': ram_total,
                        'storage_total_gb': round(disk_total, 2),
                        # Utilizados según BD
                        'cpu_utilizado_bd': utilizados.get('cpu_utilizado', 0),
                        'ram_utilizado_bd_gb': utilizados.get('ram_utilizado_gb', 0),
                        'storage_utilizado_bd_gb': utilizados.get('storage_utilizado_gb', 0),
                        'instancias_running': utilizados.get('num_instancias_running', 0),
                        'slices_detalle': utilizados.get('slices_instancias', ''),
                        # Métricas del sistema (USO REAL)
                        'cpu_percent_sistema': data.get('cpu_percent', 0),
                        'ram_percent_sistema': ram_percent,
                        'disk_percent_sistema': disk_percent,
                        'ram_sistema_gb': round(ram_sistema, 2),
                        'disk_free_gb': disk_free,
                        'qemu_count': data.get('qemu_count', 0)
                    })
        
        print(f"💾 Snapshot guardado en {csv_file}")
        return str(csv_file)
        
    except Exception as e:
        print(f"❌ Error guardando snapshot: {e}")
        return None


def listar_archivos_metricas():
    """Lista todos los archivos CSV de métricas disponibles"""
    try:
        archivos = []
        for csv_file in METRICS_STORAGE_DIR.glob("metrics_snapshot_*.csv"):
            stats = csv_file.stat()
            archivos.append({
                "nombre": csv_file.name,
                "fecha": csv_file.stem.replace("metrics_snapshot_", ""),
                "tamano_kb": round(stats.st_size / 1024, 2),
                "ruta": str(csv_file)
            })
        
        # Ordenar por fecha descendente
        archivos.sort(key=lambda x: x['fecha'], reverse=True)
        return archivos
        
    except Exception as e:
        print(f"❌ Error listando archivos: {e}")
        return []

# ======================================
# ENDPOINTS
# ======================================

@app.get("/")
def root():
    return {
        "service": "Analytics Service",
        "version": "1.0",
        "status": "running",
        "endpoints": {
            "/resources/summary": "GET - Resumen completo de recursos (Dashboard Admin)",
            "/resources/snapshot": "POST - Crear snapshot manual",
            "/metrics/files": "GET - Listar archivos CSV disponibles",
            "/metrics/export/{fecha}": "GET - Exportar métricas por fecha (YYYY-MM-DD)",
            "/metrics/latest": "GET - Obtener últimas métricas guardadas"
        }
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if engine else "disconnected",
        "metrics_storage": str(METRICS_STORAGE_DIR)
    }

@app.get("/resources/summary")
def get_resources_summary():
    """
    📊 Resumen completo de recursos para el dashboard de administrador
    
    Combina:
    - Capacidad total de workers (BD)
    - Recursos utilizados por slices RUNNING (BD)
    - Métricas en tiempo real del sistema (Monitoring Service)
    """
    try:
        capacidades = obtener_capacidad_total_workers()
        recursos_utilizados = obtener_recursos_utilizados_bd()
        metricas = obtener_metricas_actuales()
        
        # Guardar snapshot automáticamente
        guardar_metricas_snapshot(metricas, recursos_utilizados)
        
        resumen = {
            "timestamp": datetime.utcnow().isoformat(),
            "workers": {},
            "cluster_totals": {
                "cpu_total": 0,
                "cpu_utilizado": 0,
                "cpu_disponible": 0,
                "ram_total_gb": 0,
                "ram_utilizado_gb": 0,
                "ram_disponible_gb": 0,
                "storage_total_gb": 0,
                "storage_utilizado_gb": 0,
                "storage_disponible_gb": 0,
                "instancias_running_total": 0
            }
        }
        
        # ✅ CAMBIO CLAVE: Iterar sobre las MÉTRICAS (no sobre capacidades)
        if metricas and "metrics" in metricas:
            for worker_nombre, metric_data in metricas["metrics"].items():
                # Obtener capacidad (de BD o calcular desde métricas)
                if worker_nombre in capacidades:
                    capacidad = capacidades[worker_nombre]
                else:
                    # Si no está en BD, usar datos de las métricas
                    disk_free = metric_data.get('disk_free_gb', 0)
                    disk_percent = metric_data.get('disk_percent', 0)
                    if disk_percent < 100 and disk_percent > 0:
                        disk_total = disk_free / (1 - disk_percent / 100)
                    else:
                        disk_total = 10
                    
                    capacidad = {
                        "ip": f"N/A",  # No conocemos la IP
                        "cpu_total": int(metric_data.get('cpu_count', 4)),
                        "ram_total_gb": float(metric_data.get('ram_total_gb', 8)),
                        "storage_total_gb": round(disk_total, 2)
                    }
                
                utilizados = recursos_utilizados.get(worker_nombre, {
                    "cpu_utilizado": 0,
                    "ram_utilizado_gb": 0,
                    "storage_utilizado_gb": 0,
                    "num_instancias_running": 0,
                    "ip": capacidad. get("ip", "N/A"),
                    "slices_instancias": ""
                })
                
                # Calcular disponible
                cpu_disponible = capacidad["cpu_total"] - utilizados["cpu_utilizado"]
                ram_disponible = capacidad["ram_total_gb"] - utilizados["ram_utilizado_gb"]
                storage_disponible = capacidad["storage_total_gb"] - utilizados["storage_utilizado_gb"]
                
                # Métricas en tiempo real del sistema operativo
                metricas_rt = {
                    "cpu_percent_sistema": metric_data.get("cpu_percent", 0),
                    "ram_percent_sistema": metric_data.get("ram_percent", 0),
                    "disk_percent_sistema": metric_data.get("disk_percent", 0),
                    "disk_free_gb": metric_data.get("disk_free_gb", 0),
                    "qemu_count": metric_data. get("qemu_count", 0),
                    "timestamp_sent": metric_data.get("timestamp_sent", ""),
                    "received_at": metric_data.get("received_at", "")
                }
                
                resumen["workers"][worker_nombre] = {
                    "ip": capacidad.get("ip", "N/A"),
                    "capacidad": {
                        "cpu_total": capacidad["cpu_total"],
                        "ram_total_gb": round(capacidad["ram_total_gb"], 2),
                        "storage_total_gb": round(capacidad["storage_total_gb"], 2)
                    },
                    "utilizado_bd": {
                        "cpu": utilizados["cpu_utilizado"],
                        "ram_gb": round(utilizados["ram_utilizado_gb"], 2),
                        "storage_gb": round(utilizados["storage_utilizado_gb"], 2),
                        "instancias_running": utilizados["num_instancias_running"],
                        "slices_detalle": utilizados["slices_instancias"]
                    },
                    "disponible": {
                        "cpu": max(0, cpu_disponible),
                        "ram_gb": round(max(0, ram_disponible), 2),
                        "storage_gb": round(max(0, storage_disponible), 2)
                    },
                    "utilizacion_percent": {
                        "cpu": round((utilizados["cpu_utilizado"] / capacidad["cpu_total"]) * 100, 2) if capacidad["cpu_total"] > 0 else 0,
                        "ram": round((utilizados["ram_utilizado_gb"] / capacidad["ram_total_gb"]) * 100, 2) if capacidad["ram_total_gb"] > 0 else 0,
                        "storage": round((utilizados["storage_utilizado_gb"] / capacidad["storage_total_gb"]) * 100, 2) if capacidad["storage_total_gb"] > 0 else 0
                    },
                    "metricas_sistema": metricas_rt,
                    "estado": "online"
                }
                
                # Acumular totales del cluster
                resumen["cluster_totals"]["cpu_total"] += capacidad["cpu_total"]
                resumen["cluster_totals"]["cpu_utilizado"] += utilizados["cpu_utilizado"]
                resumen["cluster_totals"]["cpu_disponible"] += max(0, cpu_disponible)
                resumen["cluster_totals"]["ram_total_gb"] += capacidad["ram_total_gb"]
                resumen["cluster_totals"]["ram_utilizado_gb"] += utilizados["ram_utilizado_gb"]
                resumen["cluster_totals"]["ram_disponible_gb"] += max(0, ram_disponible)
                resumen["cluster_totals"]["storage_total_gb"] += capacidad["storage_total_gb"]
                resumen["cluster_totals"]["storage_utilizado_gb"] += utilizados["storage_utilizado_gb"]
                resumen["cluster_totals"]["storage_disponible_gb"] += max(0, storage_disponible)
                resumen["cluster_totals"]["instancias_running_total"] += utilizados["num_instancias_running"]
        
        # Redondear totales
        for key in ["ram_total_gb", "ram_utilizado_gb", "ram_disponible_gb", 
                    "storage_total_gb", "storage_utilizado_gb", "storage_disponible_gb"]:
            resumen["cluster_totals"][key] = round(resumen["cluster_totals"][key], 2)
        
        # Calcular porcentajes totales
        resumen["cluster_totals"]["utilizacion_percent"] = {
            "cpu": round((resumen["cluster_totals"]["cpu_utilizado"] / resumen["cluster_totals"]["cpu_total"]) * 100, 2) if resumen["cluster_totals"]["cpu_total"] > 0 else 0,
            "ram": round((resumen["cluster_totals"]["ram_utilizado_gb"] / resumen["cluster_totals"]["ram_total_gb"]) * 100, 2) if resumen["cluster_totals"]["ram_total_gb"] > 0 else 0,
            "storage": round((resumen["cluster_totals"]["storage_utilizado_gb"] / resumen["cluster_totals"]["storage_total_gb"]) * 100, 2) if resumen["cluster_totals"]["storage_total_gb"] > 0 else 0
        }
        
        return resumen
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}


@app.post("/resources/snapshot")
def create_snapshot():
    """
    💾 Crear snapshot manual de métricas
    """
    try:
        recursos_utilizados = obtener_recursos_utilizados_bd()
        metricas = obtener_metricas_actuales()
        
        if not metricas:
            return {
                "success": False,
                "error": "No se pudieron obtener métricas del monitoring service"
            }
        
        archivo = guardar_metricas_snapshot(metricas, recursos_utilizados)
        
        if archivo:
            return {
                "success": True,
                "mensaje": "Snapshot creado exitosamente",
                "archivo": archivo,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "error": "Error al guardar snapshot"
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/metrics/files")
def list_metrics_files():
    """
    📂 Listar archivos CSV de métricas disponibles para exportar
    """
    try:
        archivos = listar_archivos_metricas()
        
        return {
            "success": True,
            "total_archivos": len(archivos),
            "archivos": archivos,
            "directorio": str(METRICS_STORAGE_DIR)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/metrics/export/{fecha}")
def export_metrics(fecha: str):
    """
    📥 Exportar métricas de un día específico
    
    Parámetro:
        fecha: Formato YYYY-MM-DD (ejemplo: 2025-11-24)
    
    Retorna el contenido del CSV para descargar
    """
    try:
        csv_file = METRICS_STORAGE_DIR / f"metrics_snapshot_{fecha}.csv"
        
        if not csv_file.exists():
            return {
                "success": False,
                "error": f"No se encontró archivo para la fecha {fecha}"
            }
        
        # Leer contenido del CSV
        with open(csv_file, 'r') as f:
            contenido = f.read()
        
        return Response(
            content=contenido,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=metrics_{fecha}.csv"
            }
        )
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/metrics/latest")
def get_latest_metrics():
    """
    📊 Obtener las métricas más recientes guardadas
    
    Lee el último snapshot y retorna los datos en formato JSON
    """
    try:
        archivos = listar_archivos_metricas()
        
        if not archivos:
            return {
                "success": False,
                "error": "No hay archivos de métricas disponibles"
            }
        
        # Tomar el archivo más reciente
        ultimo_archivo = METRICS_STORAGE_DIR / archivos[0]["nombre"]
        
        # Leer CSV y convertir a JSON
        metricas = []
        with open(ultimo_archivo, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                metricas.append(row)
        
        return {
            "success": True,
            "archivo": archivos[0]["nombre"],
            "fecha": archivos[0]["fecha"],
            "total_registros": len(metricas),
            "metricas": metricas[-10:] if len(metricas) > 10 else metricas
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


#extra
@app.get("/metrics/history")
def get_metrics_history(minutes: int = 30):
    """
    Obtener histórico de métricas de los últimos N minutos
    
    Parámetros:
        minutes: Minutos de histórico a obtener (default: 30)
    
    Retorna datos para graficar evolución temporal
    """
    try:
        from datetime import timedelta
        import csv
        from collections import defaultdict
        
        fecha = datetime.utcnow(). strftime("%Y-%m-%d")
        csv_file = METRICS_STORAGE_DIR / f"metrics_snapshot_{fecha}.csv"
        
        if not csv_file.exists():
            return {
                "success": False,
                "error": "No hay datos históricos disponibles para hoy"
            }
        
        # Leer CSV manualmente (sin pandas por ahora)
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        history = defaultdict(lambda: {
            "timestamps": [],
            "cpu_percent": [],
            "ram_percent": [],
            "disk_percent": [],
            "qemu_count": []
        })
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Parsear timestamp
                    row_time = datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
                    
                    # Filtrar por tiempo
                    if row_time >= cutoff_time:
                        worker = row['worker_nombre']
                        history[worker]["timestamps"].append(row['timestamp'])
                        history[worker]["cpu_percent"].append(float(row. get('cpu_percent_sistema', 0)))
                        history[worker]["ram_percent"].append(float(row.get('ram_percent_sistema', 0)))
                        history[worker]["disk_percent"].append(float(row.get('disk_percent_sistema', 0)))
                        history[worker]["qemu_count"]. append(int(row.get('qemu_count', 0)))
                except Exception as e:
                    print(f"Error procesando fila: {e}")
                    continue
        
        return {
            "success": True,
            "period_minutes": minutes,
            "data": dict(history)
        }
        
    except Exception as e:
        print(f"❌ Error obteniendo histórico: {e}")
        return {
            "success": False,
            "error": str(e)
        }



# ======================================
# MAIN
# ======================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Analytics Service escuchando en 0.0.0.0:5030...")
    uvicorn.run(app, host="0.0.0.0", port=5030)