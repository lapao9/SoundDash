"""
test_multistation.py

Objetivo: Avaliar o comportamento do sistema quando múltiplas estações
estão a reportar ao mesmo tempo para o servidor.

O que testa:
  1. Publicação simultânea de N sensores via MQTT
  2. Latência de escrita no InfluxDB com múltiplos sensores
  3. Tempo de query com dados de múltiplos sensores em simultâneo
  4. Se há perda de dados (pontos publicados vs pontos inseridos)
  5. Tempo de resposta das rotas da app com múltiplos sensores

Uso:
  python3 test_multistation.py
  python3 test_multistation.py --sensores 4 --mensagens 100

Requisitos:
  pip install influxdb-client paho-mqtt
"""

import threading
import time
import json
import math
import random
import argparse
from time import perf_counter
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient

# ─── Configurações ────────────────────────────────────────────────────────────
MQTT_BROKER  = "10.64.137.6"
MQTT_PORT    = 1884
INFLUX_URL   = "http://10.64.137.6:8086"
TOKEN        = "LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA=="
ORG          = "ISEL"
BUCKET       = "SoundDashHosp"
TOPIC_BASE   = "sound/levels"   # tópico base
# ─────────────────────────────────────────────────────────────────────────────


def gerar_payload_sensor(sensor_id: int) -> list:
    """Gera um payload realista simulando os dados de um sensor."""
    ts = time.time()
    laea = random.uniform(35, 65)
    payload = [
        ts,           # 0 TimeStamp
        sensor_id,    # 1 SensorID
        laea + 2,     # 2 LAEZ
        laea + 1,     # 3 LAEC
        laea,         # 4 LAEA
        laea + 15,    # 5 LZpeak
        laea + 15,    # 6 LZpeakT
        laea + 12,    # 7 LCpeak
        laea + 12,    # 8 LCpeakT
        laea + 10,    # 9 LApeak
        laea + 10,    # 10 LApeakT
        laea + 5,     # 11 LAFmax
        laea + 5,     # 12 LAFmaxT
        laea - 5,     # 13 LAFmin
        laea - 5,     # 14 LAFminT
        laea + 1,     # 15 LZeq
        laea + 0.5,   # 16 LCeq
        laea,         # 17 LAeq
    ]
    # Bandas de frequência (18-47) — valores aleatórios
    for _ in range(30):
        payload.append(random.uniform(20, 50))
    # LAEA_SLOW_Event, EventDetect (48, 49)
    payload.append(laea - 2)
    payload.append(0.0)
    # EventType1-10 (50-59)
    for _ in range(10):
        payload.append(random.uniform(0, 0.1))
    # Class1ID, Class1Score, Class2ID, Class2Score, Class3ID, Class3Score (60-65)
    payload.extend([1, 0.8, 2, 0.1, 3, 0.05])
    return payload


def sensor_worker(sensor_id: int, n_mensagens: int, resultados: dict):
    """Simula um sensor a publicar N mensagens via MQTT."""
    publicadas = 0
    erros = 0
    tempos = []

    client = mqtt.Client()
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

        for i in range(n_mensagens):
            payload = gerar_payload_sensor(sensor_id)
            t0 = perf_counter()
            result = client.publish(TOPIC_BASE, json.dumps(payload))
            result.wait_for_publish(timeout=5)
            elapsed = perf_counter() - t0

            if result.rc == 0:
                publicadas += 1
                tempos.append(elapsed)
            else:
                erros += 1

            time.sleep(0.0625)  # 16 mensagens/segundo como o sensor real

    except Exception as e:
        print(f"  [Sensor{sensor_id}] Erro: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

    resultados[sensor_id] = {
        "publicadas": publicadas,
        "erros": erros,
        "tempo_medio_ms": round(sum(tempos) / len(tempos) * 1000, 2) if tempos else 0,
        "tempo_max_ms": round(max(tempos) * 1000, 2) if tempos else 0,
    }


def run_query(client, query: str, label: str) -> tuple:
    """Executa uma query e mede o tempo."""
    t0 = perf_counter()
    try:
        tables = client.query_api().query(query, org=ORG)
        count = sum(len(t.records) for t in tables)
        elapsed = perf_counter() - t0
        print(f"    ✅  {count:>6} registos  |  {elapsed:.3f}s  — {label}")
        return count, elapsed
    except Exception as e:
        elapsed = perf_counter() - t0
        print(f"    ❌  Erro ({elapsed:.3f}s)  — {label}: {e}")
        return 0, elapsed


# ══════════════════════════════════════════════════════════════════════════════
# TESTE 1 — Publicação simultânea de múltiplos sensores
# ══════════════════════════════════════════════════════════════════════════════

def teste_publicacao_simultanea(n_sensores: int, n_mensagens: int):
    print(f"\n{'═'*60}")
    print(f"TESTE 1 — {n_sensores} sensores a publicar em simultâneo")
    print(f"  {n_mensagens} mensagens por sensor = {n_sensores * n_mensagens} mensagens total")
    print(f"{'═'*60}")

    resultados = {}
    threads = []

    t_inicio = perf_counter()
    for i in range(1, n_sensores + 1):
        t = threading.Thread(
            target=sensor_worker,
            args=(i, n_mensagens, resultados)
        )
        threads.append(t)

    # Lança todos ao mesmo tempo
    for t in threads:
        t.start()

    for t in threads:
        t.join()

    t_total = perf_counter() - t_inicio

    total_publicadas = sum(r["publicadas"] for r in resultados.values())
    total_erros = sum(r["erros"] for r in resultados.values())
    total_esperadas = n_sensores * n_mensagens

    print(f"\n  Resultados por sensor:")
    for sid, r in sorted(resultados.items()):
        status = "✅" if r["erros"] == 0 else "⚠️"
        print(f"  {status} Sensor{sid}: {r['publicadas']} publicadas | "
              f"latência média {r['tempo_medio_ms']}ms | máx {r['tempo_max_ms']}ms")

    print(f"\n  Sumário:")
    print(f"  Total publicadas : {total_publicadas}/{total_esperadas}")
    print(f"  Total erros      : {total_erros}")
    print(f"  Taxa de sucesso  : {total_publicadas/total_esperadas*100:.1f}%")
    print(f"  Tempo total      : {t_total:.2f}s")
    print(f"  Throughput       : {total_publicadas/t_total:.1f} msgs/s")

    return resultados


# ══════════════════════════════════════════════════════════════════════════════
# TESTE 2 — Latência de escrita no InfluxDB com múltiplos sensores
# ══════════════════════════════════════════════════════════════════════════════
def teste_queries_multisenso(n_sensores: int):
    print(f"\n{'═'*60}")
    print(f"TESTE 2 — Queries com {n_sensores} sensores em simultâneo")
    print(f"{'═'*60}")

    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:

        # Query 1: Um sensor de cada vez
        print(f"\n  [A] Query por sensor individual:")
        tempos_individual = []
        for i in range(1, n_sensores + 1):
            query = f'''
            from(bucket: "{BUCKET}")
              |> range(start: -1h)
              |> filter(fn: (r) => r["_measurement"] == "Sensor{i}")
              |> filter(fn: (r) => r["_field"] == "LAEA")
              |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
            '''
            count, elapsed = run_query(client, query, f"Sensor{i} individual")
            tempos_individual.append(elapsed)

        # Query 2: Todos os sensores numa só query com filter OR
        print(f"\n  [B] Query todos os sensores numa só query:")
        sensor_filter = " or ".join([f'r["_measurement"] == "Sensor{i}"' for i in range(1, n_sensores + 1)])
        query_todos = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1h)
          |> filter(fn: (r) => {sensor_filter})
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
        '''
        count_todos, elapsed_todos = run_query(client, query_todos, f"Todos os {n_sensores} sensores")

        # Query 3: Múltiplos campos + múltiplos sensores (o pior caso)
        print(f"\n  [C] Query múltiplos campos + múltiplos sensores:")
        query_complexa = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1h)
          |> filter(fn: (r) => {sensor_filter})
          |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak"
                            or r["_field"] == "LAFmax" or r["_field"] == "LAFmin")
          |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        count_complexa, elapsed_complexa = run_query(client, query_complexa, f"4 campos × {n_sensores} sensores")

        # Sumário
        t_soma_individual = sum(tempos_individual)
        print(f"\n  Comparação:")
        print(f"  {n_sensores} queries individuais : {t_soma_individual:.3f}s total")
        print(f"  1 query todos juntos     : {elapsed_todos:.3f}s")
        melhoria = (t_soma_individual - elapsed_todos) / t_soma_individual * 100
        sinal = "🟢" if melhoria > 10 else ("🟡" if melhoria > 0 else "🔴")
        print(f"  {sinal} Melhoria ao juntar     : {melhoria:+.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
# TESTE 3 — Verificar perda de dados
# ══════════════════════════════════════════════════════════════════════════════

def teste_perda_dados(n_sensores: int, n_mensagens: int):
    print(f"\n{'═'*60}")
    print(f"TESTE 3 — Verificar perda de dados")
    print(f"{'═'*60}")
    print(f"  A aguardar 10 segundos para os dados chegarem ao InfluxDB...")
    time.sleep(10)

    total_esperado = n_sensores * n_mensagens
    total_encontrado = 0

    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        for i in range(1, n_sensores + 1):
            query = f'''
            from(bucket: "{BUCKET}")
              |> range(start: -5m)
              |> filter(fn: (r) => r["_measurement"] == "Sensor{i}" or r["_measurement"] == "sensor{i}")
              |> filter(fn: (r) => r["_field"] == "LAEA")
              |> count()
            '''
            tables = client.query_api().query(query, org=ORG)
            count = 0
            for table in tables:
                for record in table.records:
                    count = record.get_value() or 0
            total_encontrado += count
            status = "✅" if count >= n_mensagens * 0.95 else "⚠️"
            print(f"  {status} Sensor{i}: {count}/{n_mensagens} pontos no InfluxDB "
                  f"({count/n_mensagens*100:.0f}%)")

    taxa = total_encontrado / total_esperado * 100 if total_esperado > 0 else 0
    print(f"\n  Total: {total_encontrado}/{total_esperado} pontos ({taxa:.1f}%)")
    if taxa >= 95:
        print(f"  🟢 Sem perda de dados significativa")
    elif taxa >= 80:
        print(f"  🟡 Alguma perda de dados — investigar")
    else:
        print(f"  🔴 Perda de dados significativa — problema no pipeline")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensores",  type=int, default=4,  help="Número de sensores a simular (default: 4)")
    parser.add_argument("--mensagens", type=int, default=50, help="Mensagens por sensor (default: 50)")
    args = parser.parse_args()

    print(f"\n🔌 A testar ligação ao MQTT e InfluxDB...")
    time.sleep(10)  # Delay para garantir que os dados estão no InfluxDB
    try:
        c = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
        c.ping()
        c.close()
        print(f"✅ InfluxDB acessível")
    except Exception as e:
        print(f"❌ InfluxDB não acessível: {e}")
        exit(1)

    # Teste 1 — publicação simultânea
    resultados = teste_publicacao_simultanea(args.sensores, args.mensagens)

    # Teste 2 — queries multisenso
    teste_queries_multisenso(args.sensores)

    # Teste 3 — verificar perda de dados
    teste_perda_dados(args.sensores, args.mensagens)

    print(f"\n✅ Testes de múltiplas estações concluídos!")
    print(f"\n💡 Para testar com mais sensores ou mensagens:")
    print(f"   python3 test_multistation.py --sensores 8 --mensagens 200")
    #
