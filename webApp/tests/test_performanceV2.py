#!/usr/bin/env python3
"""
test_performance.py - VERSÃO CORRIGIDA

Testa performance de queries raw vs agregado
Com measurements corretos: sensor1, sensor2, etc.
"""

import time
import requests
from influxdb_client import InfluxDBClient

# ─── Configuração ─────────────────────────────────────────────────────────────
INFLUX_URL = "http://10.64.137.6:8086"
INFLUX_TOKEN = "LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA=="
INFLUX_ORG = "ISEL"
SENSOR_ID = 3  # Testar com sensor2 (que tem dados segundo test_multistation)
# ─────────────────────────────────────────────────────────────────────────────

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()


# ══════════════════════════════════════════════════════════════════════════════
# TESTES RAW
# ══════════════════════════════════════════════════════════════════════════════

def test_5min_raw():
    """Query 5 minutos - bucket raw"""
    query = f'''
    from(bucket: "SoundDashHosp")
      |> range(start: -5m)
      |> filter(fn: (r) => r["_measurement"] == "sensor{SENSOR_ID}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"✅ 5min RAW (sensor{SENSOR_ID}): {elapsed:.3f}s - {points} pontos")
    return elapsed, points


def test_1h_raw():
    """Query 1 hora - bucket raw"""
    query = f'''
    from(bucket: "SoundDashHosp")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "sensor{SENSOR_ID}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"✅ 1h RAW (sensor{SENSOR_ID}): {elapsed:.3f}s - {points} pontos")
    return elapsed, points


def test_7d_raw():
    """Query 7 dias - bucket raw (deve ser lento!)"""
    query = f'''
    from(bucket: "SoundDashHosp")
      |> range(start: -7d)
      |> filter(fn: (r) => r["_measurement"] == "sensor{SENSOR_ID}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"⚠️  7d RAW (sensor{SENSOR_ID}): {elapsed:.3f}s - {points} pontos")
    return elapsed, points


def test_30d_raw():
    """Query 30 dias - bucket raw (MUITO lento!)"""
    query = f'''
    from(bucket: "SoundDashHosp")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "sensor{SENSOR_ID}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"🔴 30d RAW (sensor{SENSOR_ID}): {elapsed:.3f}s - {points} pontos")
    return elapsed, points


# ══════════════════════════════════════════════════════════════════════════════
# TESTES AGREGADO
# ══════════════════════════════════════════════════════════════════════════════

def test_7d_hourly():
    """Query 7 dias - bucket agregado (hourly)"""
    query = f'''
    from(bucket: "SoundDashHosp_hourly")
      |> range(start: -7d)
      |> filter(fn: (r) => r["_measurement"] == "sensor{SENSOR_ID}_hourly")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    start = time.time()
    try:
        result = query_api.query(query)
        elapsed = time.time() - start
        points = sum([len(table.records) for table in result])
        print(f"✅ 7d AGREGADO (sensor{SENSOR_ID}_hourly): {elapsed:.3f}s - {points} pontos")
        return elapsed, points
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 7d AGREGADO: Erro ({elapsed:.3f}s) - {e}")
        return elapsed, 0


def test_30d_hourly():
    """Query 30 dias - bucket agregado (hourly) - deve ser RÁPIDO!"""
    query = f'''
    from(bucket: "SoundDashHosp_hourly")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "sensor{SENSOR_ID}_hourly")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    start = time.time()
    try:
        result = query_api.query(query)
        elapsed = time.time() - start
        points = sum([len(table.records) for table in result])
        print(f"🟢 30d AGREGADO (sensor{SENSOR_ID}_hourly): {elapsed:.3f}s - {points} pontos")
        return elapsed, points
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 30d AGREGADO: Erro ({elapsed:.3f}s) - {e}")
        return elapsed, 0


# ══════════════════════════════════════════════════════════════════════════════
# TESTE VIA FLASK
# ══════════════════════════════════════════════════════════════════════════════

def test_flask_endpoint():
    """Testa endpoint Flask /api/data"""
    url = "http://10.64.137.6:5000/api/data"
    params = {
        'sensor_id': SENSOR_ID,
        'start': '-5m',
        'field': 'LAEA'
    }
    
    start = time.time()
    try:
        response = requests.get(url, params=params, timeout=10)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            points = len(data.get('values', []))
            print(f"✅ FLASK 5min (sensor{SENSOR_ID}): {elapsed:.3f}s - {points} pontos - HTTP {response.status_code}")
        else:
            print(f"❌ FLASK: HTTP {response.status_code} ({elapsed:.3f}s)")
        
        return elapsed, points if response.status_code == 200 else 0
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ FLASK: Erro ({elapsed:.3f}s) - {e}")
        return elapsed, 0


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{'═'*70}")
    print(f"  TESTES DE PERFORMANCE - sensor{SENSOR_ID}")
    print(f"{'═'*70}\n")
    
    resultados = []
    
    # Testes RAW (ordem crescente de duração)
    print("📊 TESTES RAW (bucket: SoundDashHosp):")
    print("-" * 70)
    
    r = test_5min_raw()
    resultados.append(("5min RAW", r))
    time.sleep(1)
    
    r = test_1h_raw()
    resultados.append(("1h RAW", r))
    time.sleep(1)
    
    r = test_7d_raw()
    resultados.append(("7d RAW", r))
    time.sleep(1)
    
    # 30 dias raw - comentado porque pode ser muito lento
    print("\n⚠️  30 dias RAW pode demorar 10-60s! Pressiona Ctrl+C para cancelar...")
    time.sleep(3)
    r = test_30d_raw()
    resultados.append(("30d RAW", r))
    
    # Testes AGREGADO
    print(f"\n📊 TESTES AGREGADO (bucket: SoundDashHosp_hourly):")
    print("-" * 70)
    
    r = test_7d_hourly()
    resultados.append(("7d AGREGADO", r))
    time.sleep(1)
    
    r = test_30d_hourly()
    resultados.append(("30d AGREGADO", r))
    time.sleep(1)
    
    # Teste Flask
    print(f"\n📊 TESTE FLASK ENDPOINT:")
    print("-" * 70)
    r = test_flask_endpoint()
    resultados.append(("FLASK 5min", r))
    
    # Sumário
    print(f"\n{'═'*70}")
    print(f"  SUMÁRIO DOS RESULTADOS")
    print(f"{'═'*70}")
    print(f"{'Teste':<20} {'Tempo (s)':<12} {'Pontos':<10}")
    print("-" * 70)
    
    for nome, (tempo, pontos) in resultados:
        print(f"{nome:<20} {tempo:<12.3f} {pontos:<10}")
    
    # Comparação 30 dias
    print(f"\n{'─'*70}")
    print(f"  COMPARAÇÃO: 30 DIAS")
    print(f"{'─'*70}")
    
    raw_30d = next((r for r in resultados if r[0] == "30d RAW"), None)
    agg_30d = next((r for r in resultados if r[0] == "30d AGREGADO"), None)
    
    if raw_30d and agg_30d:
        tempo_raw, pontos_raw = raw_30d[1]
        tempo_agg, pontos_agg = agg_30d[1]
        
        if tempo_agg > 0:
            melhoria_tempo = (tempo_raw - tempo_agg) / tempo_raw * 100
            melhoria_pontos = (1 - pontos_agg / pontos_raw) * 100 if pontos_raw > 0 else 0
            
            print(f"  Tempo RAW:      {tempo_raw:.2f}s ({pontos_raw} pontos)")
            print(f"  Tempo AGREGADO: {tempo_agg:.2f}s ({pontos_agg} pontos)")
            print(f"  ")
            print(f"  🚀 Melhoria tempo:  {melhoria_tempo:+.1f}% ({tempo_raw/tempo_agg:.0f}× mais rápido)")
            print(f"  📉 Redução pontos:  {melhoria_pontos:.1f}%")
    
    print(f"\n{'═'*70}\n")
    print("✅ Testes concluídos!")
    print("\n💡 Se bucket agregado não existe, cria com:")
    print("   influx bucket create --name SoundDashHosp_hourly --org ISEL --retention 8760h")
