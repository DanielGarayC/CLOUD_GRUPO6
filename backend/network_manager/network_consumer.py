# network_consumer.py
import pika, json
from sqlalchemy.orm import Session
from database import SessionLocal
import network as svc   # tu network.py normal

QUEUE = "network_rpc"

def handle_request(body: dict):
    """
    body = {"action": "ASIGNAR_VLAN"}  o  {"action": "ASIGNAR_VNC"}
    """
    action = body.get("action")
    db: Session = SessionLocal()

    try:
        if action == "ASIGNAR_VLAN":
            result = svc.asignar_vlan(db)
            return result

        elif action == "ASIGNAR_VNC":
            result = svc.asignar_vnc(db)
            return result

        else:
            return {"error": f"acción desconocida: {action}"}

    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()


def main():
    print("🐰 Network RPC Consumer escuchando...")

    conn = pika.BlockingConnection(
        pika.ConnectionParameters(host="rabbitmq")
    )
    ch = conn.channel()

    ch.queue_declare(queue=QUEUE)

    def callback(ch, method, props, body):
        body_json = json.loads(body.decode())
        print("📩 RPC recibido:", body_json)

        response = handle_request(body_json)

        ch.basic_publish(
            exchange="",
            routing_key=props.reply_to,
            properties=pika.BasicProperties(correlation_id=props.correlation_id),
            body=json.dumps(response)
        )

        ch.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=QUEUE, on_message_callback=callback)

    ch.start_consuming()


if __name__ == "__main__":
    main()
