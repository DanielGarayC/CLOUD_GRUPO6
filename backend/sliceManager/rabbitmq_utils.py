# rabbitmq_utils.py
import os
import json
import pika
import uuid


RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "admin")
QUEUE_NETWORK = os.getenv("RABBITMQ_QUEUE_NETWORK", "network_tasks")
RPC_QUEUE_NETWORK = os.getenv("RABBITMQ_QUEUE_RPC_NETWORK", "network_rpc")


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
def rpc_call_network(request: dict, timeout: int = 5):
    """
    Hace una llamada RPC al Network Manager a través de RabbitMQ.
    Bloquea hasta recibir la respuesta o hasta timeout.
    """
    conn = get_connection()
    ch = conn.channel()

    # Cola RPC donde escucha el Network Manager
    ch.queue_declare(queue=RPC_QUEUE_NETWORK, durable=True)

    # Cola de respuesta exclusiva para esta conexión
    result = ch.queue_declare(queue="", exclusive=True)
    callback_queue = result.method.queue

    corr_id = str(uuid.uuid4())
    response_body = {"error": "RPC timeout"}

    def on_response(ch_, method, props, body):
        nonlocal response_body
        if props.correlation_id == corr_id:
            response_body = json.loads(body)
            ch_.basic_ack(delivery_tag=method.delivery_tag)
            ch_.stop_consuming()

    ch.basic_consume(
        queue=callback_queue,
        on_message_callback=on_response,
        auto_ack=False,
    )

    ch.basic_publish(
        exchange="",
        routing_key=RPC_QUEUE_NETWORK,
        properties=pika.BasicProperties(
            reply_to=callback_queue,
            correlation_id=corr_id,
        ),
        body=json.dumps(request),
    )

    # Esperar respuesta (bloqueante pero simple)
    ch.connection.process_data_events(time_limit=timeout)
    conn.close()
    return response_body
