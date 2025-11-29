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
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "admin")
RPC_QUEUE_VMPLACEMENT = os.getenv("RPC_QUEUE_VMPLACEMENT", "rpc_vm_placement")

print("🐇 Iniciando VM Placement RPC Consumer...")
print(f"Host RabbitMQ: {RABBITMQ_HOST}")
print(f"Cola RPC: {RPC_QUEUE_VMPLACEMENT}")

# =============================
# HANDLER DEL RPC
# =============================
def on_request(ch, method, props, body):
    print("[RPC VM-PLACEMENT] Request recibido:", body)
    response = None  # por si algo raro pasa

    try:
        # 1) Parsear el JSON del body
        try:
            slice_data = json.loads(body)
        except Exception as e:
            response = {
                "can_deploy": False,
                "placement_plan": [],
                "error": f"JSON inválido: {e}"
            }
        else:
            # 2) Toda la lógica de VM Placement protegida
            try:
                ruta_csv = obtener_unico_csv()

                if ruta_csv is None:
                    response = {
                        "can_deploy": False,
                        "placement_plan": [],
                        "error": "No existe CSV de métricas aún"
                    }
                else:
                    # Lista de VMs que vienen del Slice Manager
                    instancias_req = slice_data.get("instancias", [])

                    ganador, plataforma, workers_aptos, workers_no_aptos = run_vm_placement(
                        slice_data,
                        ruta_csv=ruta_csv,
                        imprimir=True
                    )

                    if ganador is not None:
                        # modo single-worker
                        if isinstance(ganador, list) and ganador:
                            worker_ganador = ganador[0]
                        else:
                            worker_ganador = ganador

                        placement_plan = [
                            {
                                "nombre_vm": vm["nombre"],
                                "worker": worker_ganador
                            }
                            for vm in instancias_req
                        ]

                        response = {
                            "can_deploy": True,
                            "placement_plan": placement_plan,
                            "modo": "single-worker",
                        }
                    
                    # modo multi-worker
                    ok_plan, plan, vms_restantes, msg_plan = distribuir_vms_max_localidad(
                        slice_data,
                        ruta_csv=ruta_csv,
                        imprimir=True
                    )

                    placement_plan = []

                    if ok_plan:
                        # plan: {worker_name: [indices_vm_asignadas]}
                        for worker_name, indices in plan.items():
                            for idx in indices:
                                if isinstance(idx, int) and 0 <= idx < len(instancias_req):
                                    vm_info = instancias_req[idx]
                                    placement_plan.append({
                                        "nombre_vm": vm_info["nombre"],
                                        "worker": worker_name
                                    })

                    # can_deploy = True solo si TODAS las VMs quedaron asignadas
                    can_deploy = bool(ok_plan and not vms_restantes)

                    # (opcional) detalle de VMs no asignadas
                    vms_no_asignadas_detalle = []
                    for vm in vms_restantes:
                        idx = vm.get("index")
                        nombre_vm = None
                        if isinstance(idx, int) and 0 <= idx < len(instancias_req):
                            nombre_vm = instancias_req[idx]["nombre"]

                        vms_no_asignadas_detalle.append({
                            "index": idx,
                            "nombre_vm": nombre_vm,
                            "cpu": vm.get("cpu"),
                            "ram": vm.get("ram"),
                            "storage": vm.get("storage")
                        })

                    response = {
                        "can_deploy": can_deploy,
                        "placement_plan": placement_plan if can_deploy else [],
                        "modo": "multi-worker",
                    }

                    if not can_deploy:
                        response["error"] = (
                            "No se pudo asignar el slice completo con las restricciones actuales"
                        )

            except Exception as e:
                # ⚠️ Cualquier error interno de VM Placement cae aquí
                print(f"❌ Error interno en VM Placement: {type(e).__name__}: {e}")
                response = {
                    "can_deploy": False,
                    "placement_plan": [],
                    "error": f"Error interno en VM Placement: {type(e).__name__}: {e}"
                }

    finally:
        # Pase lo que pase, SIEMPRE respondemos y hacemos ACK
        if response is None:
            response = {
                "can_deploy": False,
                "placement_plan": [],
                "error": "Error inesperado: response vacío en consumer"
            }

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


# ==============================
# MAIN LOOP (CON CREDENCIALES)
# ==============================
credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        credentials=credentials,
        heartbeat=0
    )
)
channel = connection.channel()

channel.queue_declare(queue=RPC_QUEUE_VMPLACEMENT, durable=False)
channel.basic_qos(prefetch_count=1)
channel.basic_consume(
    queue=RPC_QUEUE_VMPLACEMENT,
    on_message_callback=on_request
)

print("Esperando requests RPC…")
channel.start_consuming()
