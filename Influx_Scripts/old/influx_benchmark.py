"""
influx_benchmark.py

Dois objetivos:
  1. Testar a robustez e performance do InfluxDB para diferentes ranges temporais
  2. Explorar features nativas do InfluxDB (aggregateWindow, quantile, 
     movingAverage, derivative, histogram)

Uso: python3 influx_benchmark.py
"""

from influxdb_client import InfluxDBClient
from datetime import datetime, timezone, timedelta
from time import perf_counter
import json
import math

# ─── Configurações ────────────────────────────────────────────────────────────
INFLUX_URL = "http://localhost:8086"
TOKEN       = "zn7AgCy9Eb8U2wSXUfYcKR3snX81byyHDapRBGeisbJ-HfUzkyTp3MM5NMyFdvY2R9oV78xtJP3Fhs5N7_yOnQ=="
ORG         = "myorg"
BUCKET      = "sounddash"
MEASUREMENT = "Sensor1"   # ajusta ao sensor que importaste
# ─────────────────────────────────────────────────────────────────────────────


def run_query(client, query: str, label: str) -> tuple:
    """Executa uma query, mede o tempo e devolve (resultados, tempo_segundos)."""
    print(f"\n  ▶ {label}")
    t0 = perf_counter()
    try:
        tables = client.query_api().query(query, org=ORG)
        count = sum(len(t.records) for t in tables)
        elapsed = perf_counter() - t0
        print(f"    ✅  {count} registos em {elapsed:.3f}s")
        return tables, elapsed
    except Exception as e:
        elapsed = perf_counter() - t0
        print(f"    ❌  Erro ({elapsed:.3f}s): {e}")
        return [], elapsed


# ══════════════════════════════════════════════════════════════════════════════
# OBJETIVO 1 — PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

def test_performance(client):
    print("\n" + "═"*60)
    print("OBJETIVO 1 — TESTES DE PERFORMANCE")
    print("═"*60)

    results = {}

    # Ranges a testar com diferentes agregações
    test_cases = [
        ("Últimos 30 min  | sem agregação",
         "range(start: -30m)",   None),
        ("Últimas 1 hora  | sem agregação",
         "range(start: -1h)",    None),
        ("Últimas 6 horas | agregação 1m",
         "range(start: -6h)",    "1m"),
        ("Último dia      | agregação 5m",
         "range(start: -1d)",    "5m"),
        ("Última semana   | agregação 15m",
         "range(start: -7d)",    "15m"),
        ("Último mês      | agregação 1h",
         "range(start: -30d)",   "1h"),
    ]

    for label, range_clause, window in test_cases:
        if window:
            query = f'''
            from(bucket: "{BUCKET}")
              |> {range_clause}
              |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
              |> filter(fn: (r) => r["_field"] == "LAEA")
              |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
            '''
        else:
            query = f'''
            from(bucket: "{BUCKET}")
              |> {range_clause}
              |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
              |> filter(fn: (r) => r["_field"] == "LAEA")
            '''
        _, elapsed = run_query(client, query, label)
        results[label] = elapsed

    # Teste de query com múltiplos campos simultâneos (como faz a app)
    label = "Multi-campo (LAEA+LCpeak+LAFmax+LAFmin) | 1h | 1m"
    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak"
                        or r["_field"] == "LAFmax" or r["_field"] == "LAFmin")
      |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    _, elapsed = run_query(client, query, label)
    results[label] = elapsed

    # Teste de query de eventos (como faz /api/eventos)
    label = "Query eventos (pivot + filter EventDetect) | 1h"
    fields = ['EventDetect'] + [f'EventType{i}' for i in range(1, 11)]
    field_filter = " or ".join([f'r["_field"] == "{f}"' for f in fields])
    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}" and ({field_filter}))
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> filter(fn: (r) => r["EventDetect"] > 0)
      |> sort(columns: ["_time"])
    '''
    _, elapsed = run_query(client, query, label)
    results[label] = elapsed

    print("\n📊 Resumo de Performance:")
    print(f"  {'Query':<50} {'Tempo':>8}")
    print("  " + "-"*60)
    for label, t in results.items():
        status = "🟢" if t < 1 else ("🟡" if t < 3 else "🔴")
        print(f"  {status} {label:<48} {t:>6.3f}s")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# OBJETIVO 2 — FEATURES DO INFLUXDB
# ══════════════════════════════════════════════════════════════════════════════

def test_features(client):
    print("\n" + "═"*60)
    print("OBJETIVO 2 — FEATURES NATIVAS DO INFLUXDB")
    print("═"*60)

    # ── Feature 1: aggregateWindow com diferentes funções ─────────────────
    print("\n[Feature 1] aggregateWindow — mean, max, min por janela de 1 minuto")
    for fn in ["mean", "max", "min"]:
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1h)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: 1m, fn: {fn}, createEmpty: false)
        '''
        tables, _ = run_query(client, query, f"aggregateWindow fn={fn}")
        for table in tables:
            sample = [r.get_value() for r in table.records[:3]]
            if sample:
                print(f"    Primeiros 3 valores ({fn}): {[round(v,2) for v in sample if v]}")
                break

    # ── Feature 2: quantile (percentis nativos) ────────────────────────────
    print("\n[Feature 2] quantile — percentis P50 e P95 nativos do InfluxDB")
    for q in [0.50, 0.95]:
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1h)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> quantile(q: {q}, method: "estimate_tdigest")
        '''
        tables, elapsed = run_query(client, query, f"quantile P{int(q*100)}")
        for table in tables:
            for record in table.records:
                print(f"    P{int(q*100)} LAEA = {round(record.get_value(), 2)} dB  ({elapsed:.3f}s)")

    # ── Feature 3: movingAverage ───────────────────────────────────────────
    print("\n[Feature 3] movingAverage — média móvel de 10 pontos")
    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -30m)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
      |> movingAverage(n: 10)
    '''
    tables, _ = run_query(client, query, "movingAverage n=10")
    for table in tables:
        sample = [round(r.get_value(), 2) for r in table.records[:5] if r.get_value()]
        if sample:
            print(f"    Primeiros 5 valores suavizados: {sample}")
            break

    # ── Feature 4: derivative (variação por segundo) ───────────────────────
    print("\n[Feature 4] derivative — variação do LAEA por segundo")
    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -30m)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
      |> derivative(unit: 1s, nonNegative: false)
    '''
    tables, _ = run_query(client, query, "derivative por segundo")
    for table in tables:
        sample = [round(r.get_value(), 4) for r in table.records[:5] if r.get_value() is not None]
        if sample:
            print(f"    Variação dB/s (primeiros 5): {sample}")
            break

    # ── Feature 5: pivot multi-campo num só query ──────────────────────────
    print("\n[Feature 5] pivot — múltiplos campos numa só query (mais eficiente)")
    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -5m)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak"
                        or r["_field"] == "LAFmax" or r["_field"] == "LAFmin")
      |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    tables, elapsed = run_query(client, query, "pivot 4 campos em 1 query")
    for table in tables:
        for record in table.records[:2]:
            vals = {k: round(v, 2) for k, v in record.values.items()
                   if k in ["LAEA", "LCpeak", "LAFmax", "LAFmin"] and v is not None}
            if vals:
                print(f"    {record.get_time().strftime('%H:%M:%S')} → {vals}")

    # ── Feature 6: Lden calculado diretamente no InfluxDB ─────────────────
    print("\n[Feature 6] Lden — cálculo direto em Flux (sem Python)")
    # Nota: InfluxDB Flux permite fazer math inline
    query = f'''
    import "math"

    night = from(bucket: "{BUCKET}")
      |> range(start: -24h, stop: -16h)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
      |> mean()
      |> map(fn: (r) => ({{ r with _value: math.pow(base: 10.0, exp: r._value / 10.0) }}))
      |> mean()

    night
    '''
    tables, elapsed = run_query(client, query, "média linear LAEA noite (base para Lden)")
    for table in tables:
        for record in table.records:
            v = record.get_value()
            if v:
                lden_component = 10 * math.log10(v) if v > 0 else None
                print(f"    Valor linear médio noite: {v:.4f} → {round(lden_component,2)} dB")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n🔌 A ligar ao InfluxDB...")
    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        # Verificar ligação
        try:
            health = client.ping()
            print(f"✅ Ligado! InfluxDB a responder.")
        except Exception as e:
            print(f"❌ Não foi possível ligar: {e}")
            exit(1)

        test_performance(client)
        test_features(client)

    print("\n✅ Testes concluídos!")
