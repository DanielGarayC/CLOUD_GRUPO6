FROM python:3.10-slim

WORKDIR /app

# Copiar requirements primero (mejor para cache)
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Levantar el consumidor RabbitMQ + API FastAPI simultáneamente
CMD ["sh", "-c", "python network_consumer.py & uvicorn service:app --host 0.0.0.0 --port 8100"]