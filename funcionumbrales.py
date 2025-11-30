import pandas as pd
import matplotlib.pyplot as plt


def analizar_worker(file_path, worker_objetivo, umbral,
                    ventana_minutos, limite_segundos):
    """
    Analiza el CPU de un worker y grafica:

    - file_path: ruta al CSV.
    - worker_objetivo: nombre del worker a analizar (ej. 'worker2').
    - umbral: valor de CPU utilizado (cpu_utilizado_bd) a partir del cual
              se considera que está sobre el umbral (ej. 2.8).
    - ventana_minutos: tamaño de la ventana hacia atrás desde el último
                       timestamp (ej. 10 para últimos 10 minutos).
    - limite_segundos: si algún intervalo sobre el umbral dura más que este
                       tiempo (en segundos), la función retorna True.

    Retorna:
        bool: True si existe algún intervalo con duración > limite_segundos,
              False en caso contrario.
    """

    # -------- CARGA Y PREPROCESO --------
    df = pd.read_csv(file_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Solo nos interesa el worker objetivo
    df = df[df["worker_nombre"] == worker_objetivo]
    df = df.sort_values("timestamp")

    if df.empty:
        print(f"No hay datos de {worker_objetivo} en el CSV.")
        return False

    # -------- VENTANA DESDE EL ÚLTIMO TIEMPO HACIA ATRÁS --------
    t_fin_global = df["timestamp"].max()
    t_inicio_ventana = t_fin_global - pd.Timedelta(minutes=ventana_minutos)
    df = df[df["timestamp"] >= t_inicio_ventana]

    if df.empty:
        print(f"No hay datos de {worker_objetivo} en los últimos "
              f"{ventana_minutos} minutos.")
        return False

    # inicio / fin reales de lo que quedó
    t_inicio = df["timestamp"].min()
    t_fin = df["timestamp"].max()

    delta = t_fin - t_inicio
    total_seconds = delta.total_seconds()
    mins = int(total_seconds // 60)
    secs = int(total_seconds % 60)

    # ============================================================
    # 1) DETECTAR INTERVALOS > UMBRAL PARA worker_objetivo
    # ============================================================
    sub = df.sort_values("timestamp").copy()

    # columna booleana: está o no sobre el umbral
    sub["sobre_umbral"] = sub["cpu_utilizado_bd"] >= umbral

    # agrupar tramos consecutivos True/False
    sub["grupo"] = (sub["sobre_umbral"] != sub["sobre_umbral"].shift()).cumsum()

    # intervalo de muestreo aproximado (para ajustar el fin)
    dt_med = sub["timestamp"].diff().median()

    intervalos = []
    for gid, bloque in sub[sub["sobre_umbral"]].groupby("grupo"):
        inicio_int = bloque["timestamp"].min()
        fin_int = bloque["timestamp"].max()
        # opcional: sumar un paso de muestreo al final
        if pd.notnull(dt_med):
            fin_int = fin_int + dt_med

        dur_int = fin_int - inicio_int
        intervalos.append((inicio_int, fin_int, dur_int))

    if not intervalos:
        print(f"{worker_objetivo}: no hay intervalos sobre el umbral {umbral}.")
        # no hay intervalos => no se supera el límite
        supera_limite = False
    else:
        print(f"Intervalos donde {worker_objetivo} >= {umbral}:")
        supera_limite = False
        for i, (ini, fin, dur) in enumerate(intervalos, start=1):
            segs = int(dur.total_seconds())
            m = segs // 60
            s = segs % 60
            print(f"  Intervalo {i}: {ini.time()}  ->  {fin.time()}  "
                  f"({m} min {s} s)")
            if segs > limite_segundos:
                supera_limite = True

    # ============================================================
    # 2) GRÁFICO
    # ============================================================
    fig, ax = plt.subplots(figsize=(12, 6))

    # curva del worker
    ax.plot(df["timestamp"], df["cpu_utilizado_bd"],
            marker="o", label=worker_objetivo)

    # línea horizontal de umbral
    ax.axhline(y=umbral, linestyle="--", linewidth=1.5,
               label=f"Umbral ({umbral})")

    # sombrear intervalos donde worker_objetivo supera el umbral
    for ini, fin, _ in intervalos:
        ax.axvspan(ini, fin, alpha=0.1)

    ax.set_xlabel("Tiempo")
    ax.set_ylabel("CPU utilizado (cpu_utilizado_bd)")
    ax.set_title(f"CPU utilizado - {worker_objetivo}")
    ax.legend()
    plt.xticks(rotation=45)

    ax.text(0.01, 0.95, f"Inicio: {t_inicio.strftime('%H:%M:%S')}",
            transform=ax.transAxes, fontsize=9, va="top")
    ax.text(0.99, 0.95, f"Fin: {t_fin.strftime('%H:%M:%S')}",
            transform=ax.transAxes, fontsize=9, va="top", ha="right")
    ax.text(0.5, 0.02, f"Ventana mostrada: {mins} min {secs} s",
            transform=ax.transAxes, fontsize=9, ha="center", va="bottom")

    plt.tight_layout()
    plt.show()

    return supera_limite


# ================== EJEMPLO DE USO ==================
if __name__ == "__main__":
    FILE_PATH = r"C:\Users\Ricardo\Xd\Documents\CLOUD FINAL\CLOUD_GRUPO6\metrics_2025-11-26 (1).csv"

    alerta = analizar_worker(
        file_path=FILE_PATH,
        worker_objetivo="server2",
        umbral=3.2,
        ventana_minutos=10,
        limite_segundos=180  # por ejemplo: 1 minuto
    )

    print("¿Se supera el límite?", alerta)
