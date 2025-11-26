# Imagen base con Python 3.11
FROM python:3.11-slim

# Directorio de trabajo
WORKDIR /app

# Copiar requirements y instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY app.py .

# Crear directorio para métricas
RUN mkdir -p /app/metrics_storage

# Exponer puerto
EXPOSE 5030

# Variables de entorno por defecto
ENV DB_USER=root
ENV DB_PASS=root
ENV DB_HOST=slice_db
ENV DB_NAME=mydb
ENV MONITORING_URL=http://192.168.201.1:5010/metrics

# Volumen para persistencia
VOLUME ["/app/metrics_storage"]

# Comando de inicio
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5030"]