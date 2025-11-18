# rabbitmq_utils.py
import os
import json
import pika

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "admin")
QUEUE_NETWORK = os.getenv("RABBITMQ_QUEUE_NETWORK", "network_tasks")

def get_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    params = pika.ConnectionParameters(host=RABBITMQ_HOST,
                                       credentials=credentials)
    return pika.BlockingConnection(params)

def publish_to_network(message: dict):
    """Productor: usado por slice-manager."""
    conn = get_connection()
    ch = conn.channel()

    # Aseguramos que la cola exista
    ch.queue_declare(queue=QUEUE_NETWORK, durable=True)

    body = json.dumps(message)
    ch.basic_publish(
        exchange="",
        routing_key=QUEUE_NETWORK,
        body=body,
        properties=pika.BasicProperties(
            delivery_mode=2  # persistente
        ),
    )
    conn.close()
