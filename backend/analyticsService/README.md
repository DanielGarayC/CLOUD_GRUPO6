# 📊 Analytics Service

Servicio de análisis y almacenamiento de métricas de recursos del cluster.

## 🎯 Descripción

Este servicio recopila y analiza:
- **Recursos utilizados**: De instancias en slices `RUNNING` (Base de Datos)
- **Métricas del sistema**: En tiempo real desde el `monitoringService`
- **Almacenamiento histórico**: Guarda snapshots en CSV para análisis posterior

## 📁 Estructura

```
backend/analyticsService/
├── app.py                    # Aplicación FastAPI principal
├── requirements.txt          # Dependencias Python
├── Dockerfile               # Imagen Docker con Python 3.11
├── docker-compose.yml       # Orquestación
├── .env.example             # Variables de entorno de ejemplo
├── README.md                # Esta documentación
└── metrics_storage/         # Directorio de almacenamiento (generado)
    └── metrics_snapshot_YYYY-MM-DD.csv
```

## 🚀 Instalación y Uso

### Opción 1: Con Docker Compose (Recomendado)

```bash
# Construir e iniciar
docker-compose up -d

# Ver logs
docker-compose logs -f analytics-service

# Detener
docker-compose down
```

### Opción 2: Desarrollo local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
export DB_USER=root
export DB_PASS=root
export DB_HOST=localhost
export DB_NAME=mydb
export MONITORING_URL=http://192.168.201.1:5010/metrics

# Ejecutar
python app.py
```

## 📊 Endpoints API

### **GET /** - Información del servicio
```bash
curl http://localhost:5030/
```

### **GET /health** - Health check
```bash
curl http://localhost:5030/health
```

### **GET /resources/summary** - Resumen completo (Dashboard Admin)
```bash
curl http://localhost:5030/resources/summary | jq
```

**Respuesta:**
```json
{
  "timestamp": "2025-11-24T02:12:37Z",
  "workers": {
    "server2": {
      "ip": "192.168.201.2",
      "capacidad": {
        "cpu_total": 4,
        "ram_total_gb": 8.0,
        "storage_total_gb": 100.0
      },
      "utilizado_bd": {
        "cpu": 2,
        "ram_gb": 4.0,
        "storage_gb": 40.0,
        "instancias_running": 2,
        "slices_detalle": "Slice1 (VM1), Slice2 (VM2)"
      },
      "disponible": {
        "cpu": 2,
        "ram_gb": 4.0,
        "storage_gb": 60.0
      },
      "utilizacion_percent": {
        "cpu": 50.0,
        "ram": 50.0,
        "storage": 40.0
      },
      "metricas_sistema": {
        "cpu_percent_sistema": 1.5,
        "ram_percent_sistema": 24.8,
        "disk_percent_sistema": 36.3,
        "qemu_count": 0
      },
      "estado": "online"
    }
  },
  "cluster_totals": {
    "cpu_total": 12,
    "cpu_utilizado": 5,
    "cpu_disponible": 7,
    "ram_total_gb": 24.0,
    "ram_utilizado_gb": 10.0,
    "instancias_running_total": 5
  }
}
```

### **POST /resources/snapshot** - Crear snapshot manual
```bash
curl -X POST http://localhost:5030/resources/snapshot
```

### **GET /metrics/files** - Listar archivos CSV disponibles
```bash
curl http://localhost:5030/metrics/files | jq
```

### **GET /metrics/export/{fecha}** - Exportar CSV por fecha
```bash
# Descargar CSV del día actual
curl -O http://localhost:5030/metrics/export/2025-11-24

# Fecha específica
curl -O http://localhost:5030/metrics/export/2025-11-23
```

### **GET /metrics/latest** - Obtener últimas métricas en JSON
```bash
curl http://localhost:5030/metrics/latest | jq
```

## 📄 Formato CSV

```csv
timestamp,worker_nombre,worker_ip,cpu_total,ram_total_gb,storage_total_gb,cpu_utilizado_bd,ram_utilizado_bd_gb,storage_utilizado_bd_gb,instancias_running,slices_detalle,cpu_percent_sistema,ram_percent_sistema,disk_percent_sistema,ram_sistema_gb,disk_free_gb,qemu_count
2025-11-24 02:12:37,server2,192.168.201.2,4,8.0,100.0,2,4.0,40.0,2,"Slice1 (VM1), Slice2 (VM2)",1.5,24.8,36.3,1.98,63.7,0
```

## ⚙️ Variables de Entorno

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `DB_USER` | Usuario de MySQL | `root` |
| `DB_PASS` | Contraseña de MySQL | `root` |
| `DB_HOST` | Host de MySQL | `slice_db` |
| `DB_NAME` | Nombre de la base de datos | `mydb` |
| `MONITORING_URL` | URL del monitoring service | `http://monitoring_service:5010/metrics` |

## 🔧 Integración con Frontend

Desde el frontend (dashboard admin), puedes consumir estos endpoints:

```javascript
// Obtener resumen de recursos
fetch('http://analytics-service:5030/resources/summary')
  .then(res => res.json())
  .then(data => {
    console.log('Recursos del cluster:', data);
  });

// Exportar métricas
window.location.href = 'http://analytics-service:5030/metrics/export/2025-11-24';
```

## 📊 Características

✅ Calcula recursos utilizados **solo de slices RUNNING**  
✅ Métricas en tiempo real del sistema operativo  
✅ Almacenamiento automático en CSV cada consulta  
✅ Exportación de datos históricos  
✅ Dashboard completo con totales del cluster  
✅ API REST para integración con frontend  

## 🐛 Troubleshooting

### No se conecta a la base de datos
```bash
# Verificar que la BD esté corriendo
docker ps | grep slice_db

# Ver logs
docker-compose logs analytics-service
```

### No obtiene métricas del monitoring service
```bash
# Verificar que monitoring_service esté corriendo
curl http://monitoring_service:5010/metrics

# Verificar red Docker
docker network inspect backend_network
```

### Permisos en metrics_storage
```bash
# Dar permisos
chmod -R 755 metrics_storage/
```

## 📝 Licencia

Parte del proyecto CLOUD_GRUPO6