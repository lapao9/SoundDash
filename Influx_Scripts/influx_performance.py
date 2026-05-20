"""
influx_performance.py

Objetivo: Testar a robustez e performance do InfluxDB para diferentes
ranges temporais e tipos de query, simulando o uso real da aplicação.

Uso: python3 influx_performance.py

Resultados:
  B < 1s   — excelente
  S 1s–3s  — aceitável
  M > 3s   — problema
"""

from influxdb_client import InfluxDBClient
from time import perf_counter

# ─── Configurações ────────────────────────────────────────────────────────────
INFLUX_URL = "http://localhost:8086"
TOKEN      = "VfIVKgRa7ZcYF_LdpSWHliW2u3M_Q8iLUw6SUNReVbbjVio957NRpJollg9p-LxqJKm4CHOpupQPQ4fApef2uQ=="
ORG        = "ISEL"          
BUCKET     = "SoundDashHosp"  
MEASUREMENT = "sensor1"
# ─────────────────────────────────────────────────────────────────────────────


def run_query(client, query: str, label: str) -> float:
    """Executa uma query, mede o tempo e devolve os segundos."""
    print(f"\n  --> {label}")
    t0 = perf_counter() 
    try:
        tables = client.query_api().query(query, org=ORG)
        count = sum(len(t.records) for t in tables)
        elapsed = perf_counter() - t0
        print(f"    ✅  {count} registos em {elapsed:.3f}s")
        return elapsed
    except Exception as e:
        elapsed = perf_counter() - t0
        print(f"    ❌  Erro ({elapsed:.3f}s): {e}")
        return elapsed


def test_performance(client):
    print("\n" + "═"*60)
    print("TESTES DE PERFORMANCE — InfluxDB")
    print("═"*60)
    print(f"  Bucket      : {BUCKET}")
    print(f"  Measurement : {MEASUREMENT}")

    results = {}

    # ── Teste 1: Queries simples sem agregação ─────────────────────────────
    print("\n[Grupo 1] Queries simples — sem agregação (dados raw)")
    print("  → Simula o que acontece quando o utilizador pede 'últimos X minutos' (LAEA)")
    print("    sem compressão. Rápido para ranges pequenos, lento para ranges grandes.\n")

    for label, range_clause in [
        ("Últimos 30 min  | sem agregação", "range(start: -30m)"),
        ("Últimas 1 hora  | sem agregação", "range(start: -1h)"),
        ("Últimas 6 horas | sem agregação", "range(start: -6h)"),
    ]:
        # Usar range real baseado nos dados que temos
        query = f'''
        from(bucket: "{BUCKET}")
          |> {range_clause}
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
        '''
        results[label] = run_query(client, query, label)

    # ── Teste 2: Queries com agregação ────────────────────────────────────
    print("\n[Grupo 2] Queries com agregação — comprime dados por janela de tempo (LAEA)")
    print("  → Obrigatório para ranges grandes. Sacrifica detalhe, ganha velocidade.\n")

    for label, range_clause, window in [
        ("Últimas 6 horas | agregação 1m",  "range(start: -6h)",  "1m"),
        ("Último dia      | agregação 5m",  "range(start: -1d)",  "5m"),
        ("Última semana   | agregação 15m", "range(start: -7d)",  "15m"),
        ("Último mês      | agregação 1h",  "range(start: -30d)", "1h"),
    ]:
        query = f'''
        from(bucket: "{BUCKET}")
          |> {range_clause}
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
        '''
        results[label] = run_query(client, query, label)

    # ── Teste 3: Queries multi-campo (como faz a app) ─────────────────────
    print("\n[Grupo 3] Queries multi-campo — simula a app a pedir vários parâmetros")
    print("  → A app pede LAEA, LCpeak, LAFmax e LAFmin ao mesmo tempo.\n")

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
    results[label] = run_query(client, query, label)

    # ── Teste 4: Query de eventos (a mais pesada da app) ──────────────────
    print("\n[Grupo 4] Query de eventos — a query mais pesada da app")
    print("  → Usa pivot + filter. Simula a página 'Eventos Detetados'.\n")

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
    results[label] = run_query(client, query, label)

    # ── Resumo ────────────────────────────────────────────────────────────
    print("\n" + "═"*60)
    print("📊 RESUMO DE PERFORMANCE")
    print("═"*60)
    print(f"  {'Query':<50} {'Tempo':>8}")
    print("  " + "-"*60)
    for label, t in results.items():
        status = "B" if t < 1 else ("S" if t < 3 else "M")
        print(f"  {status} {label:<48} {t:>6.3f}s")

    print("\n  Legenda: B < 1s (bom/excelente)  S 1–3s (suficiente/aceitável)  M > 3s (mau/problema)")
    print("\n  ⚠️  Nota: Com poucos dados os resultados são sempre rápidos.")
    print("     Os testes são mais representativos com semanas/meses de dados reais.")


if __name__ == "__main__":
    print("\n🔌 A ligar ao InfluxDB...")
    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        try:
            client.ping()
            print("✅ Ligado!")
        except Exception as e:
            print(f"❌ Não foi possível ligar: {e}")
            exit(1)

        test_performance(client)

    print("\n✅ Testes de performance concluídos!")
