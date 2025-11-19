# network_consumer.py
import pika
import json
import os
import time
from sqlalchemy.orm import Session
from database import SessionLocal
import network as svc   # tu network.py normal


# ==========================
# CONFIG
# ==========================
RABBIT_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBIT_USER = os.getenv("RABBITMQ_USER", "guest")
RABBIT_PASS = os.getenv("RABBITMQ_PASS", "guest")
QUEUE = os.getenv("RABBITMQ_QUEUE_NETWORK", "network_rpc")


# ==========================
# LÓGICA DE NEGOCIO
# ==========================
def handle_request(body: dict):
    """
    body = {"action": "ASIGNAR_VLAN"}  
    o      {"action": "ASIGNAR_VNC"}
    """
    action = body.get("action")
    db: Session = SessionLocal()

    try:
        if action == "ASIGNAR_VLAN":
            return svc.asignar_vlan(db)

        elif action == "ASIGNAR_VNC":
            return svc.asignar_vnc(db)

        else:
            return {"error": f"acción desconocida: {action}"}

    except Exception as e:
        return {"error": str(e)}

    finally:
        db.close()


# ==========================
# CONEXIÓN CON RETRY INFINITO
# ==========================
def connect_rabbitmq():
    while True:
        try:
            print(f"🔄 Intentando conectar a RabbitMQ en {RABBIT_HOST}...")

            credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
            params = pika.ConnectionParameters(
                host=RABBIT_HOST,
                credentials=credentials,
                heartbeat=30,
                blocked_connection_timeout=30
            )

            conn = pika.BlockingConnection(params)
            print("✅ Conexión exitosa a RabbitMQ")
            return conn

        except Exception as e:
            print(f"❌ Error conectando a RabbitMQ: {e}")
            print("⏳ Reintentando en 3 segundos...\n")
            time.sleep(3)


# ==========================
# MAIN LOOP (NO MUERE NUNCA)
# ==========================
def main():
    print("🐰 Iniciando Network RPC Consumer...")

    while True:
        try:
            conn = connect_rabbitmq()
            ch = conn.channel()

            ch.queue_declare(queue=QUEUE)
            print(f"📡 Esperando mensajes RPC en la cola '{QUEUE}'...")

            def callback(ch, method, props, body):
                try:
                    body_json = json.loads(body.decode())
                    print(f"📩 RPC recibido: {body_json}")

                    response = handle_request(body_json)

                    ch.basic_publish(
                        exchange="",
                        routing_key=props.reply_to,
                        properties=pika.BasicProperties(
                            correlation_id=props.correlation_id
                        ),
                        body=json.dumps(response)
                    )

                except Exception as e:
                    print(f"💥 Error procesando RPC: {e}")

                finally:
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(queue=QUEUE, on_message_callback=callback)

            # ⚠️ IMPORTANTE: si se pierde la conexión,
            # start_consuming() lanza excepción → el loop reconecta
            ch.start_consuming()

        except Exception as e:
            print(f"💥 El consumer falló: {e}")
            print("🔁 Reiniciando consumer en 3 segundos...\n")
            time.sleep(3)


if __name__ == "__main__":
    main()
