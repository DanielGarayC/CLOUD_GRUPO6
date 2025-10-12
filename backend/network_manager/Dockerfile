FROM python:3.10-slim

WORKDIR /app

COPY . /app

RUN pip install fastapi uvicorn pymysql sqlalchemy

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]