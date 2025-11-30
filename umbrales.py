import pandas as pd
import matplotlib.pyplot as plt

FILE_PATH = r"C:\Users\Ricardo\Xd\Documents\CLOUD FINAL\CLOUD_GRUPO6\metrics_2025-11-26 (1).csv"

workers_interes = [
    "worker2" 
]

VENTANA_MINUTOS = 10         # ventana hacia atrás desde el tiempo actual
umbral = 2.8                # 70% de 4 cores, por ejemplo
worker_objetivo = "worker2" # sobre este vamos a medir intervalos

# -------- CARGA Y PREPROCESO --------
df = pd.read_csv(FILE_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df[df["worker_nombre"].isin(workers_interes)]
df = df.sort_values("timestamp")

# -------- VENTANA DESDE EL ÚLTIMO TIEMPO HACIA ATRÁS --------
t_fin_global = df["timestamp"].max()
t_inicio_ventana = t_fin_global - pd.Timedelta(minutes=VENTANA_MINUTOS)
df = df[df["timestamp"] >= t_inicio_ventana]

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
sub = df[df["worker_nombre"] == worker_objetivo].sort_values("timestamp").copy()

# por si acaso: si no hay datos de ese worker en la ventana, salimos
if sub.empty:
    print(f"No hay datos de {worker_objetivo} en la ventana seleccionada.")
else:
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

    # imprimir intervalos
    print(f"Intervalos donde {worker_objetivo} >= {umbral}:")
    for i, (ini, fin, dur) in enumerate(intervalos, start=1):
        segs = int(dur.total_seconds())
        m = segs // 60
        s = segs % 60
        print(f"  Intervalo {i}: {ini.time()}  ->  {fin.time()}  ({m} min {s} s)")

# ============================================================
# 2) GRÁFICO
# ============================================================
fig, ax = plt.subplots(figsize=(12, 6))

# curvas de cada worker
for worker in workers_interes:
    sub_w = df[df["worker_nombre"] == worker]
    if sub_w.empty:
        continue
    ax.plot(sub_w["timestamp"], sub_w["cpu_utilizado_bd"], marker="o", label=worker)

# línea horizontal de umbral
ax.axhline(y=umbral, linestyle="--", linewidth=1.5, label=f"Umbral 70% ({umbral})")

# sombrear intervalos donde worker_objetivo supera el umbral
if sub.empty is False:
    for ini, fin, _ in intervalos:
        ax.axvspan(ini, fin, alpha=0.1)  # sombreado suave

ax.set_xlabel("Tiempo")
ax.set_ylabel("CPU utilizado (cpu_utilizado_bd)")
ax.set_title("CPU utilizado en función del tiempo por worker")
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
