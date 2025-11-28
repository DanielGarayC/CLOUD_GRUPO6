#!/usr/bin/env python3
import pika
import json
import os
from vm_placement_core import (
    obtener_unico_csv,
    run_vm_placement,
    distribuir_vms_max_localidad
)

# =============================
# CONFIG
# =============================
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RPC_QUEUE_VMPLACEMENT = os.getenv("RPC_QUEUE_VMPLACEMENT", "rpc_vm_placement")

print("🐇 Iniciando VM Placement RPC Consumer...")
print(f"Host RabbitMQ: {RABBITMQ_HOST}")
print(f"Cola RPC: {RPC_QUEUE_VMPLACEMENT}")

# =============================
# HANDLER DEL RPC
# =============================
def on_request(ch, method, props, body):
    print("📥 [RPC VM-PLACEMENT] Request recibido:", body)
    
    try:
        request_json = json.loads(body)
    except:
        response = {"ok": False, "error": "JSON inválido"}
    else:
        ruta_csv = obtener_unico_csv()

        if ruta_csv is None:
            response = {
                "ok": False,
                "error": "No existe CSV de métricas aún"
            }
        else:
            ganador, plataforma, workers_aptos, workers_no_aptos = run_vm_placement(
                request_json,
                ruta_csv=ruta_csv,
                imprimir=True
            )

            if ganador is not None:
                response = {
                    "ok": True,
                    "modo": "single-worker",
                    "worker": ganador,
                    "plataforma": plataforma,
                    "workers_aptos": workers_aptos,
                    "workers_no_aptos": workers_no_aptos
                }
            else:
                ok_plan, plan, vms_restantes, msg_plan = distribuir_vms_max_localidad(
                    request_json,
                    ruta_csv=ruta_csv,
                    imprimir=True
                )

                response = {
                    "ok": ok_plan,
                    "modo": "multi-worker",
                    "worker": None,
                    "plataforma": plataforma,
                    "workers_aptos": workers_aptos,
                    "workers_no_aptos": workers_no_aptos,
                    "plan": plan,
                    "vms_no_asignadas": [
                        {
                            "index": vm["index"],
                            "cpu": vm["cpu"],
                            "ram": vm["ram"],
                            "storage": vm["storage"]
                        }
                        for vm in vms_restantes
                    ],
                    "mensaje": msg_plan
                }

    # RESPUESTA AL RPC
    ch.basic_publish(
        exchange="",
        routing_key=props.reply_to,
        properties=pika.BasicProperties(
            correlation_id=props.correlation_id
        ),
        body=json.dumps(response)
    )

    ch.basic_ack(delivery_tag=method.delivery_tag)
    print("📤 [RPC VM-PLACEMENT] Respuesta enviada.")


# =============================
# MAIN LOOP
# =============================
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host=RABBITMQ_HOST)
)
channel = connection.channel()

channel.queue_declare(queue=RPC_QUEUE_VMPLACEMENT, durable=False)
channel.basic_qos(prefetch_count=1)
channel.basic_consume(
    queue=RPC_QUEUE_VMPLACEMENT,
    on_message_callback=on_request
)

print("🔥 LISTO. Esperando requests RPC…")
channel.start_consuming()
