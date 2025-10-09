FROM python:3.11-slim

# Variables de entorno para evitar archivos .pyc y mejorar logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Crear directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar las dependencias
COPY requirements.txt .

# Instalar dependencias

RUN pip install --no-cache-dir -r requirements.txt \
&& pip install cryptography PyMySQL flask_sqlalchemy
# Copiar el resto de la aplicación
COPY . .

# Exponer el puerto 5000 (por defecto Flask)
EXPOSE 5000

# Comando para ejecutar la aplicación
CMD ["python", "app.py"]