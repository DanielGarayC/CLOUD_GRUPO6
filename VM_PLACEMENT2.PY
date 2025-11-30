import pandas as pd

slice_data = {
    "idslice": 19,
    "nombre": "oli",
    "estado": "STOPPED",
    "zonadisponibilidad": "BE",
    "fecha_creacion": "2025-10-12",
    "fecha_upload": None,
    "topologia": {
        "nodes": [
            {"id": 1, "label": "VM1", "x": 100, "y": 0},
            {"id": 2, "label": "VM2", "x": -50, "y": 86.60254037844388},
            {"id": 3, "label": "VM3", "x": -50, "y": -86.60254037844383}
        ],
        "edges": [
            {"from": 1, "to": 2, "id": "f50e0b85-95e6-44bd-b6ea-9b9c7be57668"},
            {"from": 1, "to": 3, "id": "0689e997-4c3b-4a12-8def-26f5a3a3fed1"},
            {"from": 2, "to": 3, "id": "a43918b0-7509-45e3-aa16-a08e25af5749"}
        ]
    },
    "instancias": [
        {
            "idinstancia": 1,
            "nombre": "VM1",
            "estado": "STOPPED",
            "cpu": "1",
            "ram": "0.2GB",
            "storage": "2GB",
            "salidainternet": 0,
            "imagen_idimagen": 1,
            "ip": None,
            "vnc_idvnc": None,
            "worker_idworker": None
        },
        {
            "idinstancia": 2,
            "nombre": "VM2",
            "estado": "STOPPED",
            "cpu": "1",
            "ram": "0.2GB",
            "storage": "2GB",
            "salidainternet": 0,
            "imagen_idimagen": 1,
            "ip": None,
            "vnc_idvnc": None,
            "worker_idworker": None
        },
        {
            "idinstancia": 3,
            "nombre": "VM3",
            "estado": "STOPPED",
            "cpu": "1",
            "ram": "0.2GB",
            "storage": "2GB",
            "salidainternet": 0,
            "imagen_idimagen": 1,
            "ip": None,
            "vnc_idvnc": None,
            "worker_idworker": None
        }
    ]
}

ZONAS_DISPONIBILIDAD = {
    "BE": {   # Best Effort
        "nombre": "Best Effort (BE)",
        "tipo_carga": "Baja prioridad",
        "descripcion": "Uso esporádico, alto tiempo en desuso, cargas no críticas.",
        "factor_cpu": 16.0,     # 1:16
        "factor_ram": 1.5,      # 1:1.5
        "factor_storage": 1.0   # 1:1
    },
    "HP": {  # High Priority
        "nombre": "High Priority (HP)",
        "tipo_carga": "Prioridad intermedia",
        "descripcion": "Uso intermitente, más frecuente que BE, pero no constante.",
        "factor_cpu": 5.0,      # 1:5
        "factor_ram": 1.3,      # 1:1.3
        "factor_storage": 1.0   # 1:1
    },
    "UHP": {  # Ultra High Priority
        "nombre": "Ultra High Priority (UHP)",
        "tipo_carga": "Alta prioridad permanente",
        "descripcion": "Uso continuo, cargas críticas y de larga duración.",
        "factor_cpu": 2.0,      # 1:2
        "factor_ram": 1.1,      # 1:1.1
        "factor_storage": 1.0   # 1:1
    }
}

UMBRAL_ZONAS = {
    "BE": {   # Best Effort
        "nombre": "Best Effort (BE)",
        "umbral_cpu": 90,     # 90%
        "umbral_tiempo": 5    # minutos
    },
    "HP": {   # High Priority
        "nombre": "High Priority (HP)",
        "umbral_cpu": 80,     # 80%
        "umbral_tiempo": 7    # minutos
    },
    "UHP": {  # Ultra High Priority
        "nombre": "Ultra High Priority (UHP)",
        "umbral_cpu": 70,     # 70%
        "umbral_tiempo": 10   # minutos
    }
}

def obtener_libres_actual(ruta_csv):
    df = pd.read_csv(ruta_csv)

    # aseguramos orden por timestamp
    df = df.sort_values(by="timestamp")

    # tomamos el último registro de cada worker
    ultimos = df.groupby("worker_nombre").tail(1)

    libres = {}

    for _, row in ultimos.iterrows():
        worker = row["worker_nombre"]

        # === CPU libre ===
        cpu_total = row["cpu_total"]
        cpu_usado = (row["cpu_percent_sistema"] / 100) * cpu_total
        cpu_libre = cpu_total - cpu_usado

        # === RAM libre (GB) ===
        ram_total = row["ram_total_gb"]
        ram_usado = (row["ram_percent_sistema"] / 100) * ram_total
        ram_libre = ram_total - ram_usado

        # === STORAGE libre (GB) ===
        storage_total = row["storage_total_gb"]
        disk_usado = (row["disk_percent_sistema"] / 100) * storage_total
        storage_libre = storage_total - disk_usado

        libres[worker] = {
            "cpu_free": round(cpu_libre, 2),
            "ram_free_gb": round(ram_libre, 2),
            "storage_free_gb": round(storage_libre, 2)
        }

    return libres


def evaluar_workers(slice_req, workers_libres):
    resultados = {}

    # Zonas fijas por servidor físico
    zonas_por_worker = {
        "server2": "BE",
        "server3": "HP",
        "server4": "UHP"
    }

    for worker, libres in workers_libres.items():

        # Obtener la zona configurada para este worker
        zona_actual = zonas_por_worker.get(worker, "BE")

        f_cpu = ZONAS_DISPONIBILIDAD[zona_actual]["factor_cpu"]
        f_ram = ZONAS_DISPONIBILIDAD[zona_actual]["factor_ram"]
        f_sto = ZONAS_DISPONIBILIDAD[zona_actual]["factor_storage"]

        causas_no = []
        causas_si = []

        # Cálculo REAL con división según la zona correspondiente
        cpu_req_real = slice_req["cpu_req"] / f_cpu
        ram_req_real = slice_req["ram_req"] / f_ram
        sto_req_real = slice_req["storage_req"] / f_sto

        # CPU
        if cpu_req_real <= libres["cpu_free"]:
            causas_si.append(f"CPU suficiente ({zona_actual}): req={cpu_req_real:.2f}, libre={libres['cpu_free']}")
        else:
            causas_no.append(
                f"CPU insuficiente ({zona_actual}): req={cpu_req_real:.2f}, libre={libres['cpu_free']}"
            )

        # RAM
        if ram_req_real <= libres["ram_free_gb"]:
            causas_si.append(f"RAM suficiente ({zona_actual}): req={ram_req_real:.3f}GB, libre={libres['ram_free_gb']}GB")
        else:
            causas_no.append(
                f"RAM insuficiente ({zona_actual}): req={ram_req_real:.3f}GB, libre={libres['ram_free_gb']}GB"
            )

        # STORAGE
        if sto_req_real <= libres["storage_free_gb"]:
            causas_si.append(f"Storage suficiente ({zona_actual}): req={sto_req_real:.2f}GB, libre={libres['storage_free_gb']}GB")
        else:
            causas_no.append(
                f"Storage insuficiente ({zona_actual}): req={sto_req_real:.2f}GB, libre={libres['storage_free_gb']}GB"
            )

        puede = len(causas_no) == 0

        resultados[worker] = {
            "puede_desplegar": puede,
            "motivo_si": causas_si,
            "motivo_no": causas_no,
            "req_cpu_real": cpu_req_real,
            "req_ram_real": ram_req_real,
            "req_sto_real": sto_req_real,
            "zona": zona_actual
        }

    return resultados





def evaluar_slice_con_csv(ruta_csv, slice_data):
    workers_libres = obtener_libres_actual(ruta_csv)

    # Cálculo de recursos brutos del slice
    total_cpu = sum(int(vm["cpu"]) for vm in slice_data["instancias"])
    total_ram = sum(float(vm["ram"].replace("GB", "")) for vm in slice_data["instancias"])
    total_storage = sum(float(vm["storage"].replace("GB", "")) for vm in slice_data["instancias"])

    slice_req = {
        "cpu_req": total_cpu,
        "ram_req": total_ram,
        "storage_req": total_storage
    }

    return evaluar_workers(slice_req, workers_libres)



ruta_csv = "metrics_2025-11-25 (1).csv"

resultado = evaluar_slice_con_csv(ruta_csv, slice_data)

ruta_csv = "metrics_2025-11-25 (1).csv"
resultado = evaluar_slice_con_csv(ruta_csv, slice_data)

print("\n================ RESULTADO DE EVALUACIÓN (MODO UHP) ================\n")

for worker, info in resultado.items():
    print(f"### WORKER: {worker} ###")

    if info["puede_desplegar"]:
        print("✔ Puede desplegar el slice")
    else:
        print("✖ No puede desplegar el slice")

    print("\n  Motivos de cumplimiento:")
    if info["motivo_si"]:
        for m in info["motivo_si"]:
            print(f"    - {m}")
    else:
        print("    (Ninguno)")

    print("\n  Motivos de rechazo:")
    if info["motivo_no"]:
        for m in info["motivo_no"]:
            print(f"    - {m}")
    else:
        print("    (Ninguno)")

    print("\n  Requerimientos reales aplicando factores UHP:")
    print(f"    CPU requerida real     : {info['req_cpu_real']:.2f}")
    print(f"    RAM requerida real (GB): {info['req_ram_real']:.2f}")
    print(f"    Storage requerido (GB) : {info['req_sto_real']:.2f}")
    print("\n-------------------------------------------------------------------\n")
