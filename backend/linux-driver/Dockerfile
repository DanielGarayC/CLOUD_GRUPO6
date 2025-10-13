FROM python:3.10-slim

# ---------- CONFIGURACIÓN DE ENTORNO ----------
WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Instalar dependencias del sistema necesarias para SSH y Open vSwitch client
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client iproute2 openvswitch-switch \
 && rm -rf /var/lib/apt/lists/*

# ---------- COPIAR ARCHIVOS ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service.py .

EXPOSE 9100

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "9100"]
