import pandas as pd

slice_data = {
    "idslice": 19,
    "nombre": "oli",
    "estado": "STOPPED",
    "zonadisponibilidad": "BE",  # 👈 Aquí pones BE / HP / UHP
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
        "umbral_tiempo": 3    # minutos
    },
    "HP": {   # High Priority
        "nombre": "High Priority (HP)",
        "umbral_cpu": 80,     # 80%
        "umbral_tiempo": 2    # minutos
    },
    "UHP": {  # Ultra High Priority
        "nombre": "Ultra High Priority (UHP)",
        "umbral_cpu": 70,     # 70%
        "umbral_tiempo": 1   # minutos
    }
}

# Mapeo: zona de disponibilidad → worker que se debe evaluar
ZONA_A_WORKER = {
    "BE": "server2",
    "HP": ["server3","server4"],
    "UHP": ["worker1","worker2","worker3"] 
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
        cpu_usado = row["cpu_utilizado_bd"]
        cpu_libre = cpu_total - cpu_usado

        # === RAM libre (GB) ===
        ram_total = row["ram_total_gb"]
        ram_usado = row["ram_utilizado_bd_gb"]
        ram_libre = ram_total - ram_usado

        # === STORAGE libre (GB) ===
        storage_total = row["storage_total_gb"]
        disk_usado = row["storage_utilizado_bd_gb"]
        storage_libre = storage_total - disk_usado

        libres[worker] = {
            "cpu_free": round(cpu_libre, 2),
            "ram_free_gb": round(ram_libre, 2),
            "storage_free_gb": round(storage_libre, 2)
        }
    

    
    return libres


def evaluar_workers(slice_req, workers_libres, zona):
    """
    Ahora zona viene de slice_data["zonadisponibilidad"]
    y SOLO se evalúan los workers que vengan en workers_libres.
    """
    resultados = {}

    f_cpu = ZONAS_DISPONIBILIDAD[zona]["factor_cpu"]
    f_ram = ZONAS_DISPONIBILIDAD[zona]["factor_ram"]
    f_sto = ZONAS_DISPONIBILIDAD[zona]["factor_storage"]

    for worker, libres in workers_libres.items():

        causas_no = []
        causas_si = []

        # ============================
        #  APLICACIÓN DE FACTORES α (DIVISIÓN)
        # ============================
        cpu_req_real = slice_req["cpu_req"] / f_cpu
        ram_req_real = slice_req["ram_req"] / f_ram
        sto_req_real = slice_req["storage_req"] / f_sto

        # CPU
        if cpu_req_real <= libres["cpu_free"]:
            causas_si.append(f"CPU suficiente: req={cpu_req_real:.2f}, libre={libres['cpu_free']}")
        else:
            causas_no.append(
                f"CPU insuficiente: req={cpu_req_real:.2f}, libre={libres['cpu_free']}"
            )

        # RAM
        if ram_req_real <= libres["ram_free_gb"]:
            causas_si.append(
                f"RAM suficiente: req={ram_req_real:.2f}GB, libre={libres['ram_free_gb']}GB"
            )
        else:
            causas_no.append(
                f"RAM insuficiente: req={ram_req_real:.2f}GB, libre={libres['ram_free_gb']}GB"
            )

        # STORAGE
        if sto_req_real <= libres["storage_free_gb"]:
            causas_si.append(
                f"Storage suficiente: req={sto_req_real:.2f}GB, libre={libres['storage_free_gb']}GB"
            )
        else:
            causas_no.append(
                f"Storage insuficiente: req={sto_req_real:.2f}GB, libre={libres['storage_free_gb']}GB"
            )

        puede = len(causas_no) == 0

        resultados[worker] = {
            "puede_desplegar": puede,
            "motivo_si": causas_si,
            "motivo_no": causas_no,
            "req_cpu_real": cpu_req_real,
            "req_ram_real": ram_req_real,
            "req_sto_real": sto_req_real,
        }

    return resultados


def evaluar_slice_con_csv(ruta_csv, slice_data):
    workers_libres = obtener_libres_actual(ruta_csv)

    # === Cálculo de recursos del slice (igual que antes) ===
    total_cpu = sum(int(vm["cpu"]) for vm in slice_data["instancias"])
    total_ram = sum(float(vm["ram"].lower().replace("gb", "")) for vm in slice_data["instancias"])
    total_storage = sum(float(vm["storage"].lower().replace("gb", "")) for vm in slice_data["instancias"])

    slice_req = {
        "cpu_req": total_cpu,
        "ram_req": total_ram,
        "storage_req": total_storage
    }

    # === Obtener zona ===
    zona = slice_data.get("zonadisponibilidad", "BE")

    # === Obtener workers permitidos para la zona (puede ser 1 o varios) ===
    worker_objetivo = ZONA_A_WORKER.get(zona)

    if not worker_objetivo:
        # Si la zona no está mapeada o viene vacía → analizamos todos (fallback original)
        workers_filres = workers_libres
    else:
        # Normalizamos a lista si es un solo string
        if isinstance(worker_objetivo, str):
            worker_objetivo = [worker_objetivo]

        # Filtramos solo los workers que sí tienen data en el CSV
        workers_filres = {}
        for w in worker_objetivo:
            w_norm = w.lower()
            if w_norm in workers_libres:
                workers_filres[w_norm] = workers_libres[w_norm]

    if not workers_filres:
        # Ningún worker permitido tiene métrica en el CSV
        return {}

    # === Llamamos a tu función original de evaluación (igual que antes) ===
    return evaluar_workers(slice_req, workers_filres, zona)


def analizar_worker_10min(file_path, worker_objetivo, umbral,
                    ventana_minutos, limite_segundos):
    """
    Retorna True si, para el worker_objetivo, en la ventana de tiempo indicada
    existe al menos un intervalo continuo donde cpu_utilizado_bd >= umbral
    con duración mayor a limite_segundos.
    """

    # -------- CARGA Y PREPROCESO --------
    df = pd.read_csv(file_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Solo el worker objetivo
    df = df[df["worker_nombre"] == worker_objetivo].sort_values("timestamp")

    if df.empty:
        # No hay datos de ese worker
        return False

    # -------- VENTANA DESDE EL ÚLTIMO TIEMPO HACIA ATRÁS --------
    t_fin_global = df["timestamp"].max()
    t_inicio_ventana = t_fin_global - pd.Timedelta(minutes=ventana_minutos)
    df = df[df["timestamp"] >= t_inicio_ventana]

    if df.empty:
        # No hay datos en la ventana
        return False

    # -------- DETECCIÓN DE INTERVALOS SOBRE EL UMBRAL --------
    sub = df.copy()
    sub["sobre_umbral"] = sub["cpu_utilizado_bd"] >= umbral
    sub["grupo"] = (sub["sobre_umbral"] != sub["sobre_umbral"].shift()).cumsum()

    dt_med = sub["timestamp"].diff().median()

    intervalos = []
    for _, bloque in sub[sub["sobre_umbral"]].groupby("grupo"):
        inicio_int = bloque["timestamp"].min()
        fin_int = bloque["timestamp"].max()
        if pd.notnull(dt_med):
            fin_int = fin_int + dt_med  # aproximar hasta la siguiente muestra
        dur_int = fin_int - inicio_int
        intervalos.append(dur_int)

    if not intervalos:
        return False

    # ¿Algún intervalo supera el límite?
    for dur in intervalos:
        if dur.total_seconds() > limite_segundos:
            return True

    return False

def evaluar_intervalos_zona(ruta_csv, zona, workers_zona):
    cfg = UMBRAL_ZONAS[zona]
    umbral_pct = cfg["umbral_cpu"]
    limite_segundos = cfg["umbral_tiempo"] * 60   # ej. 1 min → 60 s

    ventana_min = 10  # 👈 Ventana fija de 10 minutos, igual que en tu prueba

    df = pd.read_csv(ruta_csv)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    resultados_intervalo = {}

    for worker in workers_zona:
        df_w = df[df["worker_nombre"] == worker]
        if df_w.empty:
            resultados_intervalo[worker] = None
            continue

        cpu_total = df_w["cpu_total"].max()
        umbral_abs = (umbral_pct / 100.0) * cpu_total

        supera = analizar_worker_10min(
            file_path=ruta_csv,
            worker_objetivo=worker,
            umbral=umbral_abs,
            ventana_minutos=ventana_min,   # siempre 10
            limite_segundos=limite_segundos
        )
        resultados_intervalo[worker] = supera

    return resultados_intervalo




# ==================== EJECUCIÓN ====================

ruta_csv = "metrics_2025-11-26 (1).csv"

resultado = evaluar_slice_con_csv(ruta_csv, slice_data)

print(f"\n================ RESULTADO DE EVALUACIÓN (ZONA {slice_data['zonadisponibilidad']}) ================\n")

if not resultado:
    print("⚠ No se encontró el worker correspondiente a la zona o no hay datos en el CSV.")
else:
    for worker, info in resultado.items():
        print(f"### WORKER: {worker} ###")

        if info["puede_desplegar"]:
            print("✔ Puede desplegar el slice")
        else:
            print("✖ No puede desplegar el slice")

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

        print("\n  Requerimientos reales aplicando factores de zona:")
        print(f"    CPU requerida real     : {info['req_cpu_real']:.2f}")
        print(f"    RAM requerida real (GB): {info['req_ram_real']:.2f}")
        print(f"    Storage requerido (GB) : {info['req_sto_real']:.2f}")
        print("\n-------------------------------------------------------------------\n")

        # -------- Evaluar umbrales de CPU por zona --------
    zona = slice_data["zonadisponibilidad"]
    workers_zona = list(resultado.keys())

    intervalos = evaluar_intervalos_zona(ruta_csv, zona, workers_zona)

    print(f"\n=== Evaluación de intervalos de CPU para la zona {zona} ===\n")
    cfg = UMBRAL_ZONAS[zona]
    print(f"Umbral zona: {cfg['umbral_cpu']}% de CPU sostenido por más de {cfg['umbral_tiempo']} minutos\n")

    for worker, supera in intervalos.items():
        if supera is None:
            print(f"- {worker}: sin métricas en el CSV")
        elif supera:
            print(f"- {worker}: ❌ SUPERA el intervalo (no cumple umbral de zona)")
        else:
            print(f"- {worker}: ✅ NO supera el intervalo (ok para la zona)")


    




