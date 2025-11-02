FROM python:3.11-slim

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalar herramientas del sistema necesarias
RUN apt-get update && \
    apt-get install -y --no-install-recommends openssh-client iproute2 && \
    rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar dependencias
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install cryptography PyMySQL flask_sqlalchemy

# Copiar el resto de la app
COPY . .

# Exponer puerto Flask
EXPOSE 5000

# Comando por defecto
CMD ["python", "app.py"]
