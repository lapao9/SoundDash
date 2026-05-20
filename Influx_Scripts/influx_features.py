"""
influx_features.py

Objetivo: Explorar as features nativas do InfluxDB (Flux) que podem
ser aproveitadas no projeto SoundDashHosp, em vez de fazer esses
cálculos no Python.

Features exploradas:
  1. aggregateWindow  — compressão de dados por janela de tempo
  2. quantile         — percentis nativos (P50, P95)
  3. movingAverage    — suavização da curva de ruído
  4. derivative       — deteção de variações bruscas
  5. pivot            — múltiplos campos numa só query
  6. Lden             — cálculo do indicador acústico dia/tarde/noite

Uso: python3 influx_features.py
"""

from influxdb_client import InfluxDBClient
from time import perf_counter
import math

# ─── Configurações ────────────────────────────────────────────────────────────
INFLUX_URL = "http://localhost:8086"
TOKEN      = "VfIVKgRa7ZcYF_LdpSWHliW2u3M_Q8iLUw6SUNReVbbjVio957NRpJollg9p-LxqJKm4CHOpupQPQ4fApef2uQ=="
ORG        = "ISEL"          
BUCKET     = "SoundDashHosp"  
MEASUREMENT = "Sensor1"
# ─────────────────────────────────────────────────────────────────────────────


def run_query(client, query: str, label: str):
    """Executa uma query, mede o tempo e devolve (tables, elapsed)."""
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


def test_features(client):
    print("\n" + "═"*60)
    print("FEATURES NATIVAS DO INFLUXDB — Exploração")
    print("═"*60)
    print(f"  Bucket      : {BUCKET}")
    print(f"  Measurement : {MEASUREMENT}")

    # ── Feature 1: aggregateWindow ─────────────────────────────────────────
    print("\n" + "─"*60)
    print("[Feature 1] aggregateWindow — média, máximo e mínimo por janela")
    print("─"*60)
    print("  O que é: Divide o tempo em janelas (ex: 1 minuto) e calcula")
    print("  um valor resumido por janela. Essencial para não carregar")
    print("  milhões de pontos quando o range é grande.")
    print("  Uso no projeto: todos os gráficos de evolução temporal.\n")

    for fn in ["mean", "max", "min"]:
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1y)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: 1m, fn: {fn}, createEmpty: false)
        '''
        tables, _ = run_query(client, query, f"aggregateWindow fn={fn} (janelas de 1 minuto)")
        for table in tables:
            sample = [round(r.get_value(), 2) for r in table.records[:3] if r.get_value()]
            if sample:
                print(f"    Primeiros 3 valores ({fn}): {sample} dB")
                break

    # ── Feature 2: quantile ────────────────────────────────────────────────
    print("\n" + "─"*60)
    print("[Feature 2] quantile — percentis calculados diretamente no InfluxDB")
    print("─"*60)
    print("  O que é: Calcula percentis (P50, P95, etc.) sem precisar de")
    print("  trazer os dados para Python e calcular lá.")
    print("  P50 = mediana — metade do tempo o ruído estava abaixo deste valor")
    print("  P95 = 95% do tempo o ruído estava abaixo deste valor")
    print("  Uso no projeto: página 'Monitorização por Período' já mostra")
    print("  percentis — podem ser calculados aqui em vez de no Python.\n")

    for q, nome in [(0.50, "P50 (mediana)"), (0.95, "P95")]:
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1y)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> quantile(q: {q}, method: "estimate_tdigest")
        '''
        tables, elapsed = run_query(client, query, f"quantile {nome}")
        for table in tables:
            for record in table.records:
                v = record.get_value()
                if v:
                    print(f"    {nome} LAEA = {round(v, 2)} dB")

    # ── Feature 3: movingAverage ───────────────────────────────────────────
    print("\n" + "─"*60)
    print("[Feature 3] movingAverage — suavização da curva de ruído")
    print("─"*60)
    print("  O que é: Calcula a média dos últimos N pontos para suavizar")
    print("  a curva. Remove picos isolados que distorcem a visualização.")
    print("  Uso no projeto: Modo Display — o gráfico em monitor de parede")
    print("  fica mais limpo e estável com movingAverage.\n")

    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1y)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
      |> movingAverage(n: 10)
    '''
    tables, _ = run_query(client, query, "movingAverage n=10 (média dos últimos 10 pontos)")
    for table in tables:
        sample = [round(r.get_value(), 2) for r in table.records[:5] if r.get_value()]
        if sample:
            print(f"    Primeiros 5 valores suavizados: {sample} dB")
            break

    # ── Feature 4: derivative ──────────────────────────────────────────────
    print("\n" + "─"*60)
    print("[Feature 4] derivative — variação do nível sonoro por segundo")
    print("─"*60)
    print("  O que é: Calcula a diferença entre pontos consecutivos.")
    print("  Um valor alto significa que o ruído subiu ou desceu bruscamente.")
    print("  Uso no projeto: deteção de eventos sonoros súbitos.")
    print("  Ex: +5 dB/s pode indicar uma porta a bater ou alarme.\n")

    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1y)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
      |> derivative(unit: 1s, nonNegative: false)
    '''
    tables, _ = run_query(client, query, "derivative — variação dB por segundo")
    for table in tables:
        sample = [round(r.get_value(), 4) for r in table.records[:5] if r.get_value() is not None]
        if sample:
            print(f"    Variação dB/s (primeiros 5 pontos): {sample}")
            positivos = [v for v in sample if v > 2]
            if positivos:
                print(f"    ⚠️  Picos detectados (>2 dB/s): {positivos}")
            break

    # ── Feature 5: pivot ───────────────────────────────────────────────────
    print("\n" + "─"*60)
    print("[Feature 5] pivot — múltiplos campos numa só query")
    print("─"*60)
    print("  O que é: Em vez de fazer 4 queries separadas (uma por campo),")
    print("  o pivot junta tudo numa só query. Mais eficiente.")
    print("  Uso no projeto: a rota /api/stats faz 4 queries separadas —")
    print("  com pivot podia ser 1 query só.\n")

    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -1y)
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak"
                        or r["_field"] == "LAFmax" or r["_field"] == "LAFmin")
      |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    tables, elapsed = run_query(client, query, "pivot — 4 campos numa só query")
    for table in tables:
        for record in table.records[:3]:
            vals = {k: round(v, 2) for k, v in record.values.items()
                    if k in ["LAEA", "LCpeak", "LAFmax", "LAFmin"] and v is not None}
            if vals:
                print(f"    {record.get_time().strftime('%H:%M:%S')} → {vals}")

    # ── Feature 6: Lden ───────────────────────────────────────────────────
    print("\n" + "─"*60)
    print("[Feature 6] Lden — indicador acústico dia/tarde/noite")
    print("─"*60)
    print("  O que é: Indicador normalizado europeu de ruído ambiental.")
    print("  Divide o dia em 3 períodos com penalizações:")
    print("    Dia    (08h–20h) → sem penalização")
    print("    Tarde  (20h–23h) → +5 dB de penalização")
    print("    Noite  (23h–08h) → +10 dB de penalização")
    print("  Uso no projeto: já está implementado em test.py e /api/lden.")
    print("  Aqui calculamos usando queries Flux diretamente.\n")

    def fetch_mean_linear(client, range_start, range_stop):
        """Busca LAEA e devolve a média em escala linear (para somar energias)."""
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: {range_start}, stop: {range_stop})
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> mean()
        '''
        tables = client.query_api().query(query, org=ORG)
        for table in tables:
            for record in table.records:
                v = record.get_value()
                if v is not None:
                    return 10 ** (float(v) / 10)
        return None

    # Usar os dados que temos — range completo
    # Em produção usarias datas concretas do dia que queres calcular
    print("  A calcular Lden com os dados disponíveis...")
    print("  (Em produção especificarias a data do dia a calcular)\n")

    # Dividir os dados em 3 partes iguais para simular dia/tarde/noite
    # porque os nossos dados são de um período curto
    Lday_lin    = fetch_mean_linear(client, "-1y", "-8mo")
    Levening_lin = fetch_mean_linear(client, "-8mo", "-4mo")
    Lnight_lin  = fetch_mean_linear(client, "-4mo", "now()")

    if all(v is not None for v in [Lday_lin, Levening_lin, Lnight_lin]):
        Lday    = 10 * math.log10(Lday_lin)
        Levening = 10 * math.log10(Levening_lin)
        Lnight  = 10 * math.log10(Lnight_lin)

        # Fórmula Lden oficial
        Lden = 10 * math.log10(
            (12 * 10**(Lday/10) +
              4 * 10**((Levening + 5)/10) +
              8 * 10**((Lnight + 10)/10)) / 24
        )
        print(f"    Lday    = {Lday:.2f} dB")
        print(f"    Levening = {Levening:.2f} dB  (+5 dB penalização → {Levening+5:.2f} dB)")
        print(f"    Lnight  = {Lnight:.2f} dB  (+10 dB penalização → {Lnight+10:.2f} dB)")
        print(f"\n    ➡️  Lden = {Lden:.2f} dB")
        print(f"\n    Interpretação:")
        if Lden < 55:
            print(f"    🟢 Abaixo de 55 dB — dentro dos limites recomendados pela OMS")
        elif Lden < 65:
            print(f"    🟡 Entre 55–65 dB — zona de atenção")
        else:
            print(f"    🔴 Acima de 65 dB — acima dos limites recomendados")
    else:
        print("    ⚠️  Dados insuficientes para calcular Lden.")
        print("    Importa mais CSVs com dados de diferentes períodos do dia.")


if __name__ == "__main__":
    print("\n🔌 A ligar ao InfluxDB...")
    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        try:
            client.ping()
            print("✅ Ligado!")
        except Exception as e:
            print(f"❌ Não foi possível ligar: {e}")
            exit(1)

        test_features(client)

    print("\n✅ Exploração de features concluída!")
