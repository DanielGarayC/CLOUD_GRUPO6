import pandas as pd
from pathlib import Path


METRICS_DIR = Path("/app/metrics_storage")

# ================== CONFIGURACIÓN DE ZONAS ==================

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

# Mapeo: zona de disponibilidad → workers que se deben evaluar
ZONA_A_WORKER = {
    "BE": "server2",
    "HP": ["server3", "server4"],
    "UHP": ["worker1", "worker2", "worker3"]
}
# ================== FUNCIONES DE LECTURA ==================
def obtener_unico_csv():
    archivos = list(METRICS_DIR.glob("*.csv"))
    if len(archivos) == 0:
        return None
    if len(archivos) > 1:
        print(f"⚠️ Advertencia: hay más de un CSV, usando el primero: {archivos[0]}")
    return archivos[0]



# ================== FUNCIONES DE CÁLCULO ==================

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

def parse_ram_to_gb(ram_str):
    """
    Convierte RAM en MB o GB a float en GB.
    Maneja: "512MB", "512mb", "1GB", "1gb", "512 MB", 512, 1.5, etc.
    """
    if ram_str is None:
        return 1.0  # Default 1GB
    
    # Convertir a string y limpiar
    s = str(ram_str).strip().lower()
    
    # Remover espacios internos (ej: "512 mb" -> "512mb")
    s = s.replace(" ", "")
    
    # Detectar unidad y extraer número
    if "mb" in s:
        try:
            # Extraer solo la parte numérica antes de "mb"
            num_str = s.replace("mb", "").strip()
            return float(num_str) / 1024.0
        except ValueError:
            print(f"⚠️ Error parseando RAM MB: '{ram_str}' -> '{num_str}'")
            return 1.0
    
    elif "gb" in s:
        try:
            # Extraer solo la parte numérica antes de "gb"
            num_str = s.replace("gb", "").strip()
            return float(num_str)
        except ValueError:
            print(f"⚠️ Error parseando RAM GB: '{ram_str}' -> '{num_str}'")
            return 1.0
    
    else:
        # Sin unidad: asumir que es un número puro (GB)
        try:
            return float(s)
        except ValueError:
            print(f"⚠️ Error parseando RAM sin unidad: '{ram_str}'")
            return 1.0

def evaluar_workers(slice_req, workers_libres, zona):
    """
    Evalúa recursos de cada worker dado el requerimiento del slice y la zona.
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

    # === Cálculo de recursos del slice =====
    total_cpu = sum(int(vm["cpu"]) for vm in slice_data["instancias"])
    total_ram = sum(parse_ram_to_gb(vm["ram"]) for vm in slice_data["instancias"])
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
        # Si la zona no está mapeada o viene vacía → analizamos todos
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

    return evaluar_workers(slice_req, workers_filres, zona)


def analizar_worker_10min(file_path, worker_objetivo, umbral,
                          ventana_minutos, limite_segundos):
    """
    Retorna True si, para el worker_objetivo, en la ventana de tiempo indicada
    existe al menos un intervalo continuo donde cpu_utilizado_bd >= umbral
    con duración mayor a limite_segundos.
    """
    df = pd.read_csv(file_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df[df["worker_nombre"] == worker_objetivo].sort_values("timestamp")

    if df.empty:
        return False

    t_fin_global = df["timestamp"].max()
    t_inicio_ventana = t_fin_global - pd.Timedelta(minutes=ventana_minutos)
    df = df[df["timestamp"] >= t_inicio_ventana]

    if df.empty:
        return False

    sub = df.copy()
    sub["sobre_umbral"] = sub["cpu_utilizado_bd"] >= umbral
    sub["grupo"] = (sub["sobre_umbral"] != sub["sobre_umbral"].shift()).cumsum()

    dt_med = sub["timestamp"].diff().median()

    intervalos = []
    for _, bloque in sub[sub["sobre_umbral"]].groupby("grupo"):
        inicio_int = bloque["timestamp"].min()
        fin_int = bloque["timestamp"].max()
        if pd.notnull(dt_med):
            fin_int = fin_int + dt_med
        dur_int = fin_int - inicio_int
        intervalos.append(dur_int)

    if not intervalos:
        return False

    for dur in intervalos:
        if dur.total_seconds() > limite_segundos:
            return True

    return False


def evaluar_intervalos_zona(ruta_csv, zona, workers_zona):
    cfg = UMBRAL_ZONAS[zona]
    umbral_pct = cfg["umbral_cpu"]
    limite_segundos = cfg["umbral_tiempo"] * 60

    ventana_min = 10  # siempre 10 minutos

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
            ventana_minutos=ventana_min,
            limite_segundos=limite_segundos
        )
        resultados_intervalo[worker] = supera

    return resultados_intervalo


def competir_workers(file_path, workers_a_competir):
    """
    Compite workers a partir del último timestamp del CSV y aplica el algoritmo:
      - ch = CPU_free/CPU_total
      - rh = RAM_free/RAM_total
      - Dh = DISK_free/STORAGE_total
      - A = min(ch, rh, Dh)
      - Bh = |ch - rh| + |rh - Dh| + |Dh - ch|
      - Primero gana mayor A
      - Si empatan en A:
            * A < 0.5  → gana mayor Scoreh (0.9*A + 0.1*Bh)
            * A ≥0.5   → gana menor Scoreh
    """
    if not workers_a_competir:
        return {"ganadores": [], "scores": {}}

    df = pd.read_csv(file_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    ultimos = df.groupby("worker_nombre").tail(1)

    scores = {}

    for _, row in ultimos.iterrows():
        worker = row["worker_nombre"]
        if worker not in workers_a_competir:
            continue

        CPU_free = row["cpu_total"] - row["cpu_utilizado_bd"]
        RAM_free = row["ram_total_gb"] - row["ram_utilizado_bd_gb"]
        DISK_free = row["storage_total_gb"] - row["storage_utilizado_bd_gb"]

        ch = CPU_free / row["cpu_total"] if row["cpu_total"] else 0
        rh = RAM_free / row["ram_total_gb"] if row["ram_total_gb"] else 0
        Dh = DISK_free / row["storage_total_gb"] if row["storage_total_gb"] else 0

        A = min(ch, rh, Dh)
        Bh = abs(ch - rh) + abs(rh - Dh) + abs(Dh - ch)
        Scoreh = 0.9 * A + 0.1 * Bh

        scores[worker] = {
            "A": round(A, 4),
            "Bh": round(Bh, 4),
            "Scoreh": round(Scoreh, 4)
        }

    if not scores:
        return {"ganadores": [], "scores": {}}

    mejor_A = max(v["A"] for v in scores.values())
    empatados = [w for w, v in scores.items() if v["A"] == mejor_A]

    if len(empatados) == 1:
        ganadores = [empatados[0]]
    else:
        if mejor_A < 0.5:
            mejor = max(empatados, key=lambda w: scores[w]["Scoreh"])
        else:
            mejor = min(empatados, key=lambda w: scores[w]["Scoreh"])

        final_Score = scores[mejor]["Scoreh"]
        ganadores = [w for w in empatados if scores[w]["Scoreh"] == final_Score]

    return {"ganadores": ganadores, "scores": scores}


# ================== PIPELINE COMPLETO ==================

def run_vm_placement(slice_data, ruta_csv, imprimir=True):
    """
    Ejecuta TODO el flujo:
      - Evalúa recursos
      - Evalúa intervalos de CPU
      - Determina workers aptos / no aptos
      - Hace competir a los aptos
      - Devuelve: ganador, plataforma, lista de aptos y no aptos
    """
    zona = slice_data.get("zonadisponibilidad", "BE")
    resultado = evaluar_slice_con_csv(ruta_csv, slice_data)

    if imprimir:
        print(f"\n================ RESULTADO DE EVALUACIÓN (ZONA {zona}) ================\n")

    if not resultado:
        if imprimir:
            print("⚠ No se encontró el worker correspondiente a la zona o no hay datos en el CSV.")
        plataforma = "OpenStack" if zona == "UHP" else "Linux"
        return None, plataforma, [], []

    if imprimir:
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

    # Evaluar umbrales
    workers_zona = list(resultado.keys())
    intervalos = evaluar_intervalos_zona(ruta_csv, zona, workers_zona)

    if imprimir:
        cfg = UMBRAL_ZONAS[zona]
        print(f"\n=== Evaluación de intervalos de CPU para la zona {zona} ===\n")
        print(f"Umbral zona: {cfg['umbral_cpu']}% de CPU sostenido por más de {cfg['umbral_tiempo']} minutos\n")

        for worker, supera in intervalos.items():
            if supera is None:
                print(f"- {worker}: sin métricas en el CSV")
            elif supera:
                print(f"- {worker}: ❌ SUPERA el intervalo (no cumple umbral de zona)")
            else:
                print(f"- {worker}: ✅ NO supera el intervalo (ok para la zona)")

    # Elegibilidad final
    workers_aptos = []
    workers_no_aptos = []

    for worker, info in resultado.items():
        puede = info["puede_desplegar"]
        supera = intervalos.get(worker)  # True / False / None

        if puede and (supera is False):
            workers_aptos.append(worker)
        else:
            workers_no_aptos.append(worker)

    if imprimir:
        print("\n=================== RESUMEN FINAL: ELEGIBILIDAD DE WORKERS ===================\n")

        print("Workers APTOS para desplegar el slice:")
        if not workers_aptos:
            print("  (Ninguno) ❌")
        else:
            for w in workers_aptos:
                print(f"- {w}: ✅ apto")

        print("\nWorkers NO APTOS para desplegar el slice:")
        if not workers_no_aptos:
            print("  (Ninguno) ✅ Todos cumplen")
        else:
            for w in workers_no_aptos:
                print(f"- {w}: ❌ no apto")

        print("\n==========================================================================\n")
        print("Resumen de workers aptos:")
        print("workers_aptos     =", workers_aptos)
        print("workers_no_aptos  =", workers_no_aptos)

        print("\n==========================================================================\n")
        print("Competencia de workers:")

    ganador = None
    if workers_aptos:
        res_comp = competir_workers(ruta_csv, workers_aptos)
        ganadores = res_comp["ganadores"]
        metricas = res_comp["scores"]

        if imprimir:
            for w, v in metricas.items():
                print(f"- {w}: A = {v['A']} , Bh = {v['Bh']}")

            if not ganadores:
                print("❌ No hay workers aptos para competir.")
            else:
                print("\nWorkers ganadores:")
                for g in ganadores:
                    print(f"- {g}: ✅ ganador")

        if ganadores:
            ganador = ganadores[0] if len(ganadores) == 1 else ganadores
            if imprimir:
                print(f"\nEl ganador y en donde se desplegará el Slice es {ganador}")
    else:
        if imprimir:
            print("❌ No hay workers aptos para competir.")

    plataforma = "OpenStack" if zona == "UHP" else "Linux"
    return ganador, plataforma, workers_aptos, workers_no_aptos



def normalizar_instancias(instancias):
    """
    Convierte slice_data["instancias"] en una lista de VMs con valores numéricos.
    Guarda el índice original para poder referirse luego a la VM.

    Cada elemento devuelto tiene:
        {
            "index": índice en la lista original,
            "cpu":   núm. de vCPUs (int),
            "ram":   GB de RAM (float),
            "storage": GB de disco (float)
        }
    """
    vms = []
    for idx, vm in enumerate(instancias):
        cpu = int(vm["cpu"])
        
        # 🟢 USAR parse_ram_to_gb EN LUGAR DE CONVERSIÓN MANUAL
        ram_gb = parse_ram_to_gb(vm["ram"])
        
        # 🟢 MEJORAR PARSEO DE STORAGE
        storage_str = str(vm["storage"]).strip().lower().replace(" ", "")
        if "gb" in storage_str:
            sto_gb = float(storage_str.replace("gb", ""))
        elif "mb" in storage_str:
            sto_gb = float(storage_str.replace("mb", "")) / 1024.0
        else:
            try:
                sto_gb = float(storage_str)
            except ValueError:
                print(f"⚠️ Error parseando storage: '{vm['storage']}'")
                sto_gb = 10.0  # Default 10GB

        vms.append({
            "index": idx,
            "cpu": cpu,
            "ram": ram_gb,
            "storage": sto_gb,
        })
    return vms
def asignar_vms_max_localidad(vms, workers_libres, zona):
    """
    Intenta asignar TODAS las VMs a los workers dados (workers_libres),
    respetando los factores de la zona y buscando MÁXIMA LOCALIDAD:
      - Llenar la mayor cantidad posible en el primer worker (más grande),
        luego en el segundo, etc.

    Parámetros:
        vms: lista de dicts con keys: index, cpu, ram, storage
        workers_libres: dict {worker: {cpu_free, ram_free_gb, storage_free_gb}}
        zona: string "BE" / "HP" / "UHP"

    Devuelve:
        ok (bool): True si TODAS las VMs se pudieron colocar en algún worker.
        plan (dict): {worker: [indices_vm_asignadas]}
        vms_restantes (lista): VMs que NO se pudieron asignar.
    """
    # Factores de sobreprovisión por zona
    f_cpu = ZONAS_DISPONIBILIDAD[zona]["factor_cpu"]
    f_ram = ZONAS_DISPONIBILIDAD[zona]["factor_ram"]
    f_sto = ZONAS_DISPONIBILIDAD[zona]["factor_storage"]

    # Copiamos capacidades para no modificar el dict original
    capacidades = {}
    for worker, libres in workers_libres.items():
        capacidades[worker] = {
            "cpu": libres["cpu_free"],
            "ram": libres["ram_free_gb"],
            "storage": libres["storage_free_gb"],
        }

    # Ordenamos workers por CPU libre (puedes refinar a criterio multi-recurso si quieres)
    workers_ordenados = sorted(
        capacidades.keys(),
        key=lambda w: capacidades[w]["cpu"],
        reverse=True
    )

    # Inicializamos plan vacío
    plan = {w: [] for w in workers_ordenados}

    # VMs ordenadas de mayor a menor CPU (primero colocamos las grandes)
    vms_restantes = sorted(vms, key=lambda v: v["cpu"], reverse=True)

    # Recorremos worker por worker, llenando al máximo cada uno
    for worker in workers_ordenados:
        cap = capacidades[worker]

        nuevas_restantes = []
        for vm in vms_restantes:
            cpu_eff = vm["cpu"] / f_cpu
            ram_eff = vm["ram"] / f_ram
            sto_eff = vm["storage"] / f_sto

            if (cpu_eff <= cap["cpu"] and
                ram_eff <= cap["ram"] and
                sto_eff <= cap["storage"]):

                # Asignamos la VM a este worker
                plan[worker].append(vm["index"])
                cap["cpu"]     -= cpu_eff
                cap["ram"]     -= ram_eff
                cap["storage"] -= sto_eff
            else:
                # Esta VM no cabe en ESTE worker; la intentamos con los siguientes
                nuevas_restantes.append(vm)

        vms_restantes = nuevas_restantes

        if not vms_restantes:
            # Ya coloqué todas las VMs; máxima localidad alcanzada dentro de lo posible
            break

    ok = (len(vms_restantes) == 0)
    return ok, plan, vms_restantes
def distribuir_vms_max_localidad(slice_data, ruta_csv, imprimir=True):
    """
    Calcula a qué worker iría cada VM del slice, buscando MÁXIMA LOCALIDAD.

    Flujo:
      - Determina la zona (BE/HP/UHP) con fallback a BE.
      - Lee métricas actuales del CSV.
      - Toma solo workers de la zona (ZONA_A_WORKER) si están definidos.
      - Aplica umbrales de CPU de la zona usando evaluar_intervalos_zona.
      - Normaliza las VMs del slice.
      - Ejecuta asignar_vms_max_localidad.

    Devuelve:
        ok (bool): True si TODAS las VMs se pudieron asignar a algún worker.
        plan (dict): {worker: [indices_vm_asignadas]}
        vms_no_asignadas (lista de dicts VM que no cupieron)
        mensaje (str): explicación en caso de fallo parcial/total.
    """
    # Normalizamos zona
    zona = slice_data.get("zonadisponibilidad", "BE")
    zona = str(zona).upper()
    if zona not in ZONAS_DISPONIBILIDAD:
        zona = "BE"

    # Métricas actuales de workers (último timestamp por worker)
    workers_libres_all = obtener_libres_actual(ruta_csv)

    # Filtramos solo workers de la zona, si están mapeados
    worker_obj = ZONA_A_WORKER.get(zona)
    if worker_obj:
        if isinstance(worker_obj, str):
            worker_obj = [worker_obj]
        workers_filtrados = {
            w: libres
            for w, libres in workers_libres_all.items()
            if w in worker_obj
        }
    else:
        # Si la zona no está mapeada, usamos todos los workers
        workers_filtrados = workers_libres_all

    if not workers_filtrados:
        return False, {}, [], "No hay métricas para los workers de la zona."

    # Aplicamos umbrales de zona (CPU sostenida X min en los últimos 10 min)
    intervalos = evaluar_intervalos_zona(ruta_csv, zona, list(workers_filtrados.keys()))
    workers_ok = {
        w: libres
        for w, libres in workers_filtrados.items()
        if intervalos.get(w) is False   # solo los que NO superan el umbral
    }

    if not workers_ok:
        return False, {}, [], "Ningún worker cumple los umbrales de la zona."

    # Normalizamos VMs del slice
    if "instancias" not in slice_data or not slice_data["instancias"]:
        return False, {}, [], "El slice no contiene instancias a evaluar."

    vms = normalizar_instancias(slice_data["instancias"])

    # Asignamos buscando máxima localidad
    ok, plan, vms_restantes = asignar_vms_max_localidad(vms, workers_ok, zona)

    if imprimir:
        print("\n===== PLAN DE ASIGNACIÓN POR VM (MÁXIMA LOCALIDAD) =====\n")
        print(f"Zona de disponibilidad: {zona}\n")
        print("Workers considerados (tras umbrales de zona):")
        for w in workers_ok.keys():
            print(f"  - {w}")
        print("\nAsignación resultante:")
        for worker, indices in plan.items():
            if not indices:
                continue
            print(f"  Worker {worker}: VMs -> {indices}")
        if vms_restantes:
            print("\nVMs que NO se pudieron asignar:")
            for vm in vms_restantes:
                print(f"  - index={vm['index']} (cpu={vm['cpu']}, ram={vm['ram']}GB, storage={vm['storage']}GB)")
        else:
            print("\nTodas las VMs fueron asignadas correctamente.")
        print("\n========================================================\n")

    mensaje = "" if ok else "Quedaron VMs sin asignar."
    return ok, plan, vms_restantes, mensaje




