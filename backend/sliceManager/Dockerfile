FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# si tu archivo se llama app.py (según pegaste), copia ese nombre:
COPY app.py .

EXPOSE 8000
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8000"]