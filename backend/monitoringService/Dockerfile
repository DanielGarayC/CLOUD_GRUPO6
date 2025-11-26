# Imagen base liviana con Python
FROM python:3.10-slim

# Directorio de trabajo
WORKDIR /app

# Copiamos los archivos del servicio
COPY . /app

# Instalamos dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Creamos el directorio de logs
RUN mkdir -p /app/logs_metrics

# Exponemos el puerto (por defecto FastAPI corre en 5000)
EXPOSE 5010

# Comando de inicio
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5010"]
CMD ["python", "app.py"]
