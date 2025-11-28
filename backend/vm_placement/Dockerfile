FROM python:3.10-slim

WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY vm_placement_core.py .
COPY vm_placement_consumer.py .

# Crear el directorio para el volumen
RUN mkdir -p /app/metrics_storage

# Ejecutar el consumer
CMD ["python3", "vm_placement_consumer.py"]