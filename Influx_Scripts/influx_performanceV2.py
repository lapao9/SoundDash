"""
influx_performanceV2.py

Compara diretamente as queries como estão na app (webAppGrafana.py)
versus versões melhoradas, para cada rota principal.

Rotas analisadas:
  /api/stats    → 4 queries separadas  vs  1 query com pivot
  /api/eventos  → sem agregação        vs  com sort otimizado
  /api/download → tudo raw             vs  com agregação adaptativa
  /api/lden     → aggregateWindow + Python vs  query mais direta

Uso: python3 influx_performanceV2.py
"""

from influxdb_client import InfluxDBClient
from time import perf_counter

# ─── Configurações ────────────────────────────────────────────────────────────
INFLUX_URL = "http://localhost:8086"
TOKEN      = "VfIVKgRa7ZcYF_LdpSWHliW2u3M_Q8iLUw6SUNReVbbjVio957NRpJollg9p-LxqJKm4CHOpupQPQ4fApef2uQ=="
ORG        = "ISEL"          
BUCKET     = "SoundDashHosp"  
MEASUREMENT = "Sensor1"

# Range a usar nos testes — ajusta para o range onde tens dados
RANGE_START = "-1y"   # ou ex: "2025-09-29T00:00:00Z"
RANGE_END   = "now()" # ou ex: "2025-09-29T10:00:00Z"
WINDOW      = "1m"    # agregação usada na app
# ─────────────────────────────────────────────────────────────────────────────


def run_query(client, query: str, label: str):
    """Executa query, mede tempo, devolve (tables, elapsed, count)."""
    t0 = perf_counter()
    try:
        tables = client.query_api().query(query, org=ORG)
        count = sum(len(t.records) for t in tables)
        elapsed = perf_counter() - t0
        print(f"    ✅  {count:>6} registos  |  {elapsed:.4f}s")
        return tables, elapsed, count
    except Exception as e:
        elapsed = perf_counter() - t0
        print(f"    ❌  Erro: {e}  ({elapsed:.4f}s)")
        return [], elapsed, 0


def comparar(label_antes, query_antes, label_depois, query_depois, client):
    """Corre os dois e mostra a diferença."""
    print(f"\n  ANTES  — {label_antes}")
    _, t_antes, c_antes = run_query(client, query_antes, label_antes)

    print(f"  DEPOIS — {label_depois}")
    _, t_depois, c_depois = run_query(client, query_depois, label_depois)

    if t_antes > 0 and t_depois > 0:
        melhoria = ((t_antes - t_depois) / t_antes) * 100
        sinal = "🟢" if melhoria > 10 else ("🟡" if melhoria > 0 else "🔴")
        print(f"\n  {sinal}  Diferença: {melhoria:+.1f}%  "
              f"({t_antes:.4f}s → {t_depois:.4f}s)")
    return t_antes, t_depois


# ══════════════════════════════════════════════════════════════════════════════
# ROTA /api/stats
# ══════════════════════════════════════════════════════════════════════════════

def test_api_stats(client):
    print("\n" + "═"*60)
    print("ROTA /api/stats")
    print("═"*60)
    print("""
  O que faz na app:
    Quando o utilizador está na página 'Monitorização por Período'
    e carrega em 'Atualizar Gráficos', a app chama /api/stats que
    vai procurar LAEA, LCpeak, LAFmax e LAFmin para mostrar os gráficos.

  Problema atual:
    A app faz 4 queries SEPARADAS ao InfluxDB — uma por campo.
    Cada query abre uma ligação, espera resposta, e fecha.
    São 4 viagens ao InfluxDB quando podiam ser 1.

    Código atual (webAppGrafana.py linha ~300):
      queries = {
        "laea":   "... filter LAEA   ... aggregateWindow ...",
        "lcpeak": "... filter LCpeak ... aggregateWindow ...",
        "lafmax": "... filter LAFmax ... aggregateWindow ...",
        "lafmin": "... filter LAFmin ... aggregateWindow ...",
      }
      data = {key: process_query(q) for key, q in queries.items()}
      ↑ Executa as 4 em sequência, uma a seguir à outra.

  Solução proposta:
    1 query com pivot — filtra os 4 campos de uma vez e junta-os
    por timestamp numa só tabela.
    """)

    # ── ANTES: 4 queries separadas (exatamente como está na app) ──────────
    query_laea = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
      |> aggregateWindow(every: {WINDOW}, fn: mean, createEmpty: false)
      |> limit(n: 10000)
    '''
    query_lcpeak = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LCpeak")
      |> aggregateWindow(every: {WINDOW}, fn: max, createEmpty: false)
      |> limit(n: 10000)
    '''
    query_lafmax = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAFmax")
      |> aggregateWindow(every: {WINDOW}, fn: max, createEmpty: false)
      |> limit(n: 10000)
    '''
    query_lafmin = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAFmin")
      |> aggregateWindow(every: {WINDOW}, fn: min, createEmpty: false)
      |> limit(n: 10000)
    '''

    print("  ANTES — 4 queries separadas (como está na app)")
    t0 = perf_counter()
    for q in [query_laea, query_lcpeak, query_lafmax, query_lafmin]:
        tables = client.query_api().query(q, org=ORG)
        _ = sum(len(t.records) for t in tables)
    t_antes = perf_counter() - t0
    print(f"    ✅  4 queries executadas em sequência  |  {t_antes:.4f}s total")

    # ── DEPOIS: 1 query com pivot ──────────────────────────────────────────
    query_pivot = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak"
                        or r["_field"] == "LAFmax" or r["_field"] == "LAFmin")
      |> aggregateWindow(every: {WINDOW}, fn: mean, createEmpty: false)
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> limit(n: 10000)
    '''

    print("  DEPOIS — 1 query com pivot (proposta de melhoria)")
    _, t_depois, _ = run_query(client, query_pivot, "pivot 4 campos")

    melhoria = ((t_antes - t_depois) / t_antes) * 100
    sinal = "🟢" if melhoria > 10 else ("🟡" if melhoria > 0 else "🔴")
    print(f"\n  {sinal}  Diferença: {melhoria:+.1f}%  ({t_antes:.4f}s → {t_depois:.4f}s)")
    print("""
  O que mudou:
    ANTES:  4 filtros separados + 4 aggregateWindow + 4 limites
            = 4 passagens pelos dados
    DEPOIS: 1 filtro com OR + 1 aggregateWindow + pivot + 1 limite
            = 1 passagem pelos dados
    """)
    return t_antes, t_depois


# ══════════════════════════════════════════════════════════════════════════════
# ROTA /api/eventos
# ══════════════════════════════════════════════════════════════════════════════

def test_api_eventos(client):
    print("\n" + "═"*60)
    print("ROTA /api/eventos")
    print("═"*60)
    print("""
  O que faz na app:
    Página 'Eventos Detetados' — o utilizador escolhe um intervalo
    e sensor, e a app devolve todos os momentos onde EventDetect > 0.

  Problema atual:
    A query filtra EventType0 a EventType9, mas os campos reais no
    InfluxDB são EventType1 a EventType10. O EventType0 não existe
    — é um filtro desnecessário que faz o InfluxDB procurar um campo
    que não existe.

    Código atual (webAppGrafana.py linha ~200):
      fields = ['EventDetect'] + [f'EventType{{i}}' for i in range(0, 10)]
      ↑ Gera: EventDetect, EventType0, EventType1, ..., EventType9
      ↑ Devia ser: EventDetect, EventType1, ..., EventType10

    Adicionalmente, o sort final é feito DEPOIS do pivot e do filter,
    o que significa que ordena os dados já filtrados — está correto,
    mas podia ser removido se o InfluxDB já devolver ordenado por tempo.
    """)

    fields_errado = ['EventDetect'] + [f'EventType{i}' for i in range(0, 10)]
    field_filter_errado = " or ".join([f'r["_field"] == "{f}"' for f in fields_errado])

    query_antes = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}" and ({field_filter_errado}))
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> filter(fn: (r) => r["EventDetect"] > 0)
      |> sort(columns: ["_time"])
    '''

    fields_correto = ['EventDetect'] + [f'EventType{i}' for i in range(1, 11)]
    field_filter_correto = " or ".join([f'r["_field"] == "{f}"' for f in fields_correto])

    query_depois = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}" and ({field_filter_correto}))
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> filter(fn: (r) => r["EventDetect"] > 0)
    '''

    return comparar(
        "EventType0..9 (errado) + sort",   query_antes,
        "EventType1..10 (correto) sem sort redundante", query_depois,
        client
    )


# ══════════════════════════════════════════════════════════════════════════════
# ROTA /api/download
# ══════════════════════════════════════════════════════════════════════════════

def test_api_download(client):
    print("\n" + "═"*60)
    print("ROTA /api/download")
    print("═"*60)
    print("""
  O que faz na app:
    Botão 'Descarregar CSV' na página de monitorização por período.
    Vai procurar TODOS os campos de TODOS os timestamps no range
    escolhido e gera um CSV para download.

  Problema atual:
    procura absolutamente todos os dados raw sem qualquer limite ou
    agregação. Para um range de 1 semana a 16 medições/segundo,
    isso são ~9.7 milhões de linhas. O Python depois itera sobre
    todas para construir o CSV — muito lento e consome muita memória.

    Código atual (webAppGrafana.py linha ~429):
      query = f'''
        from(bucket: "{bucket}")
          |> range(start: ..., stop: ...)
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
      '''
      ↑ Sem limit, sem agregação — tudo raw.
      Depois itera com tqdm e constrói o CSV linha a linha.

  Solução proposta:
    Para ranges grandes, aplicar agregação automática.
    O utilizador recebe um CSV com menos linhas mas representativo.
    Para ranges pequenos (< 1h), manter dados raw.
    """)

    # ANTES: tudo raw
    query_antes = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
    '''

    # DEPOIS: com agregação + só campos principais
    query_depois = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak"
                        or r["_field"] == "LAFmax" or r["_field"] == "LAFmin"
                        or r["_field"] == "LAeq" or r["_field"] == "EventDetect")
      |> aggregateWindow(every: {WINDOW}, fn: mean, createEmpty: false)
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    return comparar(
        "Todos os campos, sem agregação (como está na app)",
        query_antes,
        "Campos principais com agregação 1m (proposta)",
        query_depois,
        client
    )


# ══════════════════════════════════════════════════════════════════════════════
# ROTA /api/lden
# ══════════════════════════════════════════════════════════════════════════════

def test_api_lden(client):
    print("\n" + "═"*60)
    print("ROTA /api/lden")
    print("═"*60)
    print("""
  O que faz na app:
    Calcula o Lden — indicador acústico europeu que divide o dia
    em 3 períodos (dia/tarde/noite) com penalizações.

  Como está implementado:
    Faz 3 queries separadas ao InfluxDB (uma por período do dia),
    cada uma com aggregateWindow para comprimir os dados, e depois
    calcula a média em Python convertendo dB → linear → dB.

    Código atual (webAppGrafana.py linha ~148):
      Lnight = fetch_avg(client, d0, d7, sensor, window)
      Lday   = fetch_avg(client, d8, d15, sensor, window)
      Levening = fetch_avg(client, d16, d23, sensor, window)
      ↑ 3 queries separadas

    Dentro de fetch_avg:
      |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
      ↑ Agrega primeiro, depois Python faz a média das médias

  Problema:
    Média das médias não é matematicamente correto para dB.
    A conversão correta é linear → média → dB, que é o que o código
    faz (10^(val/20)) mas com expoente 20 em vez de 10 — possível
    bug. O expoente correto para pressão sonora é 10, não 20.
    (20 seria para amplitude/tensão elétrica)

  Solução proposta:
    1 query só com mean() direto, sem aggregateWindow intermédio.
    Menos complexidade, matematicamente mais limpo.
    """)

    # ANTES: 3 queries com aggregateWindow (como está na app)
    print("  ANTES — 3 queries separadas com aggregateWindow (como está na app)")
    t0 = perf_counter()
    for periodo_start, periodo_end in [
        (f"{RANGE_START}", "-8mo"),
        ("-8mo", "-4mo"),
        ("-4mo", f"{RANGE_END}"),
    ]:
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: {periodo_start}, stop: {periodo_end})
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: {WINDOW}, fn: mean, createEmpty: false)
        '''
        tables = client.query_api().query(query, org=ORG)
        _ = sum(len(t.records) for t in tables)
        
    t_antes = perf_counter() - t0
    print(f"    ✅  3 queries executadas  |  {t_antes:.4f}s total")

    # DEPOIS: 3 queries com mean() direto (mais simples)
    print("  DEPOIS — 3 queries com mean() direto (proposta)")
    t0 = perf_counter()
    for periodo_start, periodo_end in [
        (f"{RANGE_START}", "-8mo"),
        ("-8mo", "-4mo"),
        ("-4mo", f"{RANGE_END}"),
    ]:
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: {periodo_start}, stop: {periodo_end})
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> mean()
        '''
        tables = client.query_api().query(query, org=ORG)
        _ = sum(len(t.records) for t in tables)
    t_depois = perf_counter() - t0
    print(f"    ✅  3 queries executadas  |  {t_depois:.4f}s total")

    melhoria = ((t_antes - t_depois) / t_antes) * 100 if t_antes > 0 else 0
    sinal = "🟢" if melhoria > 10 else ("🟡" if melhoria > 0 else "🔴")
    print(f"\n  {sinal}  Diferença: {melhoria:+.1f}%  ({t_antes:.4f}s → {t_depois:.4f}s)")
    print("""
  O que mudou:
    ANTES:  aggregateWindow comprime para janelas de 1m,
            depois Python faz a média das janelas
    DEPOIS: mean() calcula a média de todos os pontos diretamente
            no InfluxDB, devolve 1 valor por período — mais simples
    """)
    return t_antes, t_depois


# ══════════════════════════════════════════════════════════════════════════════
# PERCENTIS — Python vs InfluxDB nativo
# ══════════════════════════════════════════════════════════════════════════════

def test_percentis(client):
    print("\n" + "═"*60)
    print("PERCENTIS — /api/stats (P50 e P95 do LAEA)")
    print("═"*60)
    print("""
    O que faz na app:
      A página 'Monitorização por Período' mostra os percentis P50
      e P95 do LAEA. A app procura todos os valores de LAEA para Python
      e calcula os percentis lá com uma lista em memória.

    Problema atual:
      Para 1 semana de dados (16 medições/segundo) isso são ~9 milhões
      de valores transferidos do InfluxDB para Python só para calcular
      2 números. Muito ineficiente.

    Solução proposta:
      quantile() nativo do InfluxDB — o cálculo fica no InfluxDB
      e a app recebe diretamente 1 valor por percentil.
      """)

    # ANTES: procura todos os valores, calcula em Python
    print("  ANTES — procura todos os valores LAEA, calcula percentis em Python")
    query_todos = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_END})
      |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    t0 = perf_counter()
    tables = client.query_api().query(query_todos, org=ORG)
    valores = [r.get_value() for t in tables for r in t.records if r.get_value() is not None]
    valores.sort()
    n = len(valores)
    p50 = valores[int(n * 0.50)] if n > 0 else None
    p95 = valores[int(n * 0.95)] if n > 0 else None
    t_antes = perf_counter() - t0
    print(f"    ✅  {n} valores transferidos  |  P50={round(p50,2) if p50 else 'N/A'} dB  P95={round(p95,2) if p95 else 'N/A'} dB  |  {t_antes:.4f}s")

    # DEPOIS: quantile nativo no InfluxDB
    print("  DEPOIS — quantile() nativo no InfluxDB, devolve 1 valor por percentil")
    t0 = perf_counter()
    for q, nome in [(0.50, "P50"), (0.95, "P95")]:
        query_q = f'''
        from(bucket: "{BUCKET}")
          |> range(start: {RANGE_START}, stop: {RANGE_END})
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> quantile(q: {q}, method: "estimate_tdigest")
        '''
        tables = client.query_api().query(query_q, org=ORG)
        for t in tables:
            for r in t.records:
                v = r.get_value()
                if v:
                    print(f"    {nome} = {round(v, 2)} dB")
    t_depois = perf_counter() - t0
    print(f"    ✅  2 valores recebidos  |  {t_depois:.4f}s")

    melhoria = ((t_antes - t_depois) / t_antes) * 100 if t_antes > 0 else 0
    sinal = "🟢" if melhoria > 10 else ("🟡" if melhoria > 0 else "🔴")
    print(f"\n  {sinal}  Diferença: {melhoria:+.1f}%  ({t_antes:.4f}s → {t_depois:.4f}s)")
    print("""
    O que mudou:
      ANTES:  N milhões de valores transferidos → Python ordena → calcula
      DEPOIS: InfluxDB calcula internamente → devolve 2 números
      Quanto mais dados, maior a diferença.
      """)
    return t_antes, t_depois


# ══════════════════════════════════════════════════════════════════════════════
# RESUMO GERAL
# ══════════════════════════════════════════════════════════════════════════════

def resumo(resultados: dict):
    print("\n" + "═"*60)
    print("RESUMO GERAL")
    print("═"*60)
    print(f"\n  {'Rota':<20} {'Antes':>10} {'Depois':>10} {'Melhoria':>10}")
    print("  " + "-"*55)
    for rota, (t_antes, t_depois) in resultados.items():
        if t_antes > 0:
            melhoria = ((t_antes - t_depois) / t_antes) * 100
            sinal = "🟢" if melhoria > 10 else ("🟡" if melhoria > 0 else "🔴")
        else:
            melhoria = 0
            sinal = "⚪"
        print(f"  {sinal} {rota:<18} {t_antes:>9.4f}s {t_depois:>9.4f}s {melhoria:>+9.1f}%")

    print("""
  Notas importantes:
  ─────────────────
  • Com poucos dados os tempos são todos rápidos — os resultados
    são mais representativos com semanas/meses de dados reais.

  • A melhoria mais impactante na prática é /api/stats (4→1 query)
    porque é chamada frequentemente pela app.

  • O bug do EventType0 em /api/eventos não afeta a performance
    mas devolve dados incorretos — deve ser corrigido.

  • /api/download precisa de agregação adaptativa para ranges grandes,
    caso contrário a app pode ficar sem memória.
    """)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n🔌 A ligar ao InfluxDB...")
    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        try:
            client.ping()
            print("✅ Ligado!")
        except Exception as e:
            print(f"❌ Não foi possível ligar: {e}")
            exit(1)

        resultados = {}
        t1, t2 = test_api_stats(client)
        resultados["/api/stats"] = (t1, t2)

        t1, t2 = test_api_eventos(client)
        resultados["/api/eventos"] = (t1, t2)

        t1, t2 = test_api_download(client)
        resultados["/api/download"] = (t1, t2)

        t1, t2 = test_api_lden(client)
        resultados["/api/lden"] = (t1, t2)

        print("  " + "─"*50)  # debug 
        t1, t2 = test_percentis(client)
        resultados["percentis (P50/P95)"] = (t1, t2)

        resumo(resultados)

    print("✅ Comparação concluída!")
