#!/usr/bin/env python3
"""
benchmark_performance_fast.py

Versão RÁPIDA do benchmark - foca em comparação 7 dias
Skip de testes que demoram >30s

Uso:
    python3 benchmark_performance_fast.py
    python3 benchmark_performance_fast.py --sensor 3
"""

import time
import argparse
import statistics
from datetime import datetime
from influxdb_client import InfluxDBClient

# ────────────────────────────────────────────────────────────────────────────
INFLUX_URL = "http://10.64.137.6:8086"
TOKEN = "LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA=="
ORG = "ISEL"
BUCKET_RAW = "SoundDashHosp"
BUCKET_AGG = "SoundDashHosp_hourly"
TIMEOUT = 30  # segundos
# ────────────────────────────────────────────────────────────────────────────


def query_with_timeout(client, query, timeout=TIMEOUT):
    """Query com timeout"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    
    def _query():
        result = client.query_api().query(query, org=ORG)
        return sum(len(table.records) for table in result)
    
    start = time.perf_counter()
    try:
        with ThreadPoolExecutor() as executor:
            future = executor.submit(_query)
            points = future.result(timeout=timeout)
            elapsed = time.perf_counter() - start
            return elapsed, points, False
    except TimeoutError:
        elapsed = time.perf_counter() - start
        return elapsed, 0, True
    except Exception as e:
        elapsed = time.perf_counter() - start
        return elapsed, 0, True


def test_scenario(client, sensor_id, name, duration, bucket, measurement_suffix=""):
    """Testa um cenário"""
    measurement = f"sensor{sensor_id}{measurement_suffix}"
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: {duration})
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    
    print(f"A testar {name}...", end=" ", flush=True)
    elapsed, points, timeout = query_with_timeout(client, query)
    
    if timeout:
        print(f"TIMEOUT ({elapsed:.1f}s) - query cancelada")
        return None
    else:
        print(f"{elapsed:.3f}s - {points:,} pontos")
        return {"name": name, "time": elapsed, "points": points}


def run_benchmark(sensor_id):
    """Benchmark otimizado"""
    
    print("")
    print("="*80)
    print(f"  BENCHMARK RAPIDO - sensor{sensor_id}")
    print(f"  Foco: Comparacao 7 dias RAW vs AGREGADO")
    print("="*80)
    print("")
    
    client = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
    results = {}
    
    # Testes RAW (só até 7 dias)
    print("BUCKET RAW:")
    print("-" * 80)
    
    scenarios_raw = [
        ("5min_raw", "-5m", BUCKET_RAW),
        ("1h_raw", "-1h", BUCKET_RAW),
        ("6h_raw", "-6h", BUCKET_RAW),
        ("24h_raw", "-24h", BUCKET_RAW),
        ("7d_raw", "-7d", BUCKET_RAW),
    ]
    
    for name, duration, bucket in scenarios_raw:
        r = test_scenario(client, sensor_id, name, duration, bucket)
        if r:
            results[name] = r
    
    # Testes AGREGADO
    print("")
    print("BUCKET AGREGADO:")
    print("-" * 80)
    
    scenarios_agg = [
        ("7d_agg", "-7d", BUCKET_AGG, "_hourly"),
        ("14d_agg", "-14d", BUCKET_AGG, "_hourly"),
        ("30d_agg", "-30d", BUCKET_AGG, "_hourly"),
    ]
    
    for name, duration, bucket, suffix in scenarios_agg:
        r = test_scenario(client, sensor_id, name, duration, bucket, suffix)
        if r:
            results[name] = r
    
    client.close()
    return results


def print_report(results, sensor_id):
    """Relatório final"""
    
    print("")
    print("="*80)
    print("  RESULTADOS")
    print("="*80)
    print("")
    
    # Tabela resumo
    print(f"{'Teste':<20} {'Tempo (s)':<12} {'Pontos':<15}")
    print("-" * 80)
    
    for key in ["5min_raw", "1h_raw", "6h_raw", "24h_raw", "7d_raw", "7d_agg", "14d_agg", "30d_agg"]:
        if key in results:
            r = results[key]
            print(f"{r['name']:<20} {r['time']:<12.3f} {r['points']:<15,}")
    
    # Comparação 7 dias
    if "7d_raw" in results and "7d_agg" in results:
        print("")
        print("="*80)
        print("  COMPARACAO: 7 DIAS")
        print("="*80)
        print("")
        
        raw = results["7d_raw"]
        agg = results["7d_agg"]
        
        speedup = raw["time"] / agg["time"] if agg["time"] > 0 else 0
        reduction = (1 - agg["points"] / raw["points"]) * 100 if raw["points"] > 0 else 0
        
        print(f"RAW:       {raw['time']:>8.3f}s  ({raw['points']:,} pontos)")
        print(f"AGREGADO:  {agg['time']:>8.3f}s  ({agg['points']:,} pontos)")
        print("")
        print(f"MELHORIA:  {speedup:>8.1f}x mais rapido")
        print(f"REDUCAO:   {reduction:>8.1f}% menos pontos")
    
    # Comparação 14 dias
    if "14d_agg" in results:
        print("")
        print("="*80)
        print("  ESTIMATIVA: 14 DIAS RAW vs AGREGADO")
        print("="*80)
        print("")
        
        agg = results["14d_agg"]
        
        # Extrapolar RAW baseado em 7d
        if "7d_raw" in results:
            raw_7d = results["7d_raw"]
            raw_14d_est = raw_7d["time"] * 2
            raw_14d_points_est = raw_7d["points"] * 2
            
            speedup = raw_14d_est / agg["time"] if agg["time"] > 0 else 0
            
            print(f"RAW (estimado):  {raw_14d_est:>8.1f}s  ({raw_14d_points_est:,} pontos)")
            print(f"AGREGADO:        {agg['time']:>8.3f}s  ({agg['points']:,} pontos)")
            print("")
            print(f"MELHORIA ESTIMADA: {speedup:>8.1f}x mais rapido")
    
    # Sumário executivo
    print("")
    print("="*80)
    print("  SUMARIO EXECUTIVO")
    print("="*80)
    print("")
    
    print(f"Sensor: sensor{sensor_id}")
    print(f"Data:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")
    
    if "7d_raw" in results and "7d_agg" in results:
        raw = results["7d_raw"]
        agg = results["7d_agg"]
        speedup = raw["time"] / agg["time"] if agg["time"] > 0 else 0
        
        print("CONCLUSAO:")
        print("")
        print(f"  Bucket agregado reduz tempo de query de 7 dias")
        print(f"  de {raw['time']:.1f}s para {agg['time']:.3f}s")
        print(f"  ")
        print(f"  Melhoria: {speedup:.0f}x mais rapido")
        print("")
        
        if speedup > 100:
            print("  Performance: EXCEPCIONAL")
            print("  Sistema otimizado para queries longas.")
        elif speedup > 50:
            print("  Performance: MUITO BOA")
            print("  Bucket agregado altamente eficaz.")
        elif speedup > 20:
            print("  Performance: BOA")
            print("  Melhoria significativa com agregacao.")
        else:
            print("  Performance: MODERADA")
    
    print("")
    print("="*80)


def export_simple_csv(results, sensor_id):
    """Exporta CSV simples"""
    filename = f"benchmark_sensor{sensor_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w') as f:
        f.write("teste,tempo_segundos,pontos\n")
        for r in results.values():
            f.write(f"{r['name']},{r['time']:.6f},{r['points']}\n")
    
    print(f"Exportado: {filename}")
    print("")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor', type=int, default=3, help='Sensor ID (default: 3)')
    args = parser.parse_args()
    
    # Testar conexão
    print("")
    print("Testando conexao...")
    try:
        c = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
        c.ping()
        c.close()
        print("InfluxDB: OK")
    except Exception as e:
        print(f"ERRO: {e}")
        exit(1)
    
    # Benchmark
    results = run_benchmark(args.sensor)
    
    # Relatório
    print_report(results, args.sensor)
    
    # CSV
    export_simple_csv(results, args.sensor)
    
    print("Benchmark concluido!")
    print("")