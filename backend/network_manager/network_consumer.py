import json
import pika
from rabbitmq_utils import get_connection, RPC_QUEUE_NETWORK
from database import SessionLocal    # ajusta al nombre real de tu sesión
import network as svc                # tus funciones listar/asignar/...

def process_request(message: dict):
    """
    Ejecuta la acción pedida y devuelve un dict serializable.
    Aquí reusamos la lógica de network.py, pero SIN FastAPI.
    """
    action = message.get("action")
    db = SessionLocal()
    try:
        if action == "ASIGNAR_VLAN":
            result = svc.asignar_vlan(db)
            return result   # {"idvlan":..., "numero":...}

        elif action == "VLAN_INTERNET":
            result = svc.obtener_vlan_internet(db)
            return result

        elif action == "ASIGNAR_VNC":
            result = svc.asignar_vnc(db)
            return result

        else:
            return {"error": f"Acción desconocida: {action}"}

    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()


def on_request(ch, method, props, body):
    message = json.loads(body)
    print(f"[network_manager RPC] Request: {message}")

    response = process_request(message)

    # Enviar respuesta a la cola indicada en reply_to
    ch.basic_publish(
        exchange="",
        routing_key=props.reply_to,
        properties=pika.BasicProperties(
            correlation_id=props.correlation_id
        ),
        body=json.dumps(response),
    )

    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    conn = get_connection()
    ch = conn.channel()

    ch.queue_declare(queue=RPC_QUEUE_NETWORK, durable=True)
    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=RPC_QUEUE_NETWORK, on_message_callback=on_request)

    print(f"[network_manager RPC] Esperando requests en {RPC_QUEUE_NETWORK}...")
    ch.start_consuming()


if __name__ == "__main__":
    main()