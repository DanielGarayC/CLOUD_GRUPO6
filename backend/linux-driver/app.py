#Pronto con Kafka :'v
import os, json, time
from kafka import KafkaConsumer, KafkaProducer

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC     = os.getenv("KAFKA_TOPIC", "slice.driver.linux")
GROUP     = os.getenv("KAFKA_GROUP", "linux-driver-group")

time.sleep(3)

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=BOOTSTRAP,
    group_id=GROUP,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else None,
    key_deserializer=lambda k: k.decode("utf-8") if k else None
)

producer_events = KafkaProducer(
    bootstrap_servers=BOOTSTRAP,
    value_serializer=lambda v: v.encode("utf-8"),   # str -> bytes
    key_serializer=lambda k: k.encode("utf-8")
)


print(f"Linux Driver: escuchando {TOPIC} ...")
for msg in consumer:
    slice_id = msg.key or "no-key"
    print(f"[LINUX] key={msg.key} value={msg.value}")
    # Publicar un evento mínimo (solo para probar conectividad)
    producer_events.send("slice.events", key=slice_id, value="RECEIVED")
    producer_events.flush()