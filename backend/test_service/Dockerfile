FROM python:3.11-slim

WORKDIR /app

# Asumimos que los requerimientos están en la misma carpeta
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY test_service.py .

CMD ["uvicorn", "test_service:app", "--host", "0.0.0.0", "--port", "4000"]
