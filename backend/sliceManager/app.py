import os, json, time
from fastapi import FastAPI
from pydantic import BaseModel
from kafka import KafkaProducer

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")

# Productor Kafka
# (pequeña espera por si el broker demora en estar listo)
time.sleep(3)
producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    key_serializer=lambda k: k.encode("utf-8")
)

app = FastAPI()

class SliceOrder(BaseModel):
    slice_id: str
    accion: str = "create"
    cpu: int = 1

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/send")
def send(order: SliceOrder):
    # Publica SIEMPRE al topic de Linux (por ahora solo probamos Linux)
    payload = order.model_dump()
    producer.send("slice.driver.linux", key=order.slice_id, value=order.dict())
    producer.flush()
    return {"sent_to": "slice.driver.linux", "key": order.slice_id, "value": order.dict()}