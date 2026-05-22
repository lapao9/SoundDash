# test_performance.py

import time
import requests
from influxdb_client import InfluxDBClient

# Configuração
INFLUX_URL = "http://10.64.137.6:8086"
INFLUX_TOKEN = "LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA=="
INFLUX_ORG = "ISEL"

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
query_api = client.query_api()

# Cenário 1: Query 5 minutos (dados raw)
def test_5min_raw():
    query = '''
    from(bucket: "SoundDashHosp")
      |> range(start: -5m)
      |> filter(fn: (r) => r["_measurement"] == "sensor2")
      |> filter(fn: (r) => r["_field"] == "LAeq")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"5min RAW: {elapsed:.3f}s - {points} pontos")
    return elapsed, points

# Cenário 2: Query 1 hora (dados raw)
def test_1h_raw():
    query = '''
    from(bucket: "SoundDashHosp")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "sound_levels")
      |> filter(fn: (r) => r["_field"] == "LAeq")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"1h RAW: {elapsed:.3f}s - {points} pontos")
    return elapsed, points

# Cenário 3: Query 1 hora (dados agregados)
def test_1h_aggregated():
    query = '''
    from(bucket: "SoundDashHosp_aggregated")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "sound_levels_1min")
      |> filter(fn: (r) => r["_field"] == "LAeq")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"1h AGGREGATED: {elapsed:.3f}s - {points} pontos")
    return elapsed, points

# Cenário 4: Query 24 horas (dados agregados por hora)
def test_24h_hourly():
    query = '''
    from(bucket: "SoundDashHosp_aggregated")
      |> range(start: -24h)
      |> filter(fn: (r) => r["_measurement"] == "sound_levels_1hour")
      |> filter(fn: (r) => r["_field"] == "LAeq")
    '''
    start = time.time()
    result = query_api.query(query)
    elapsed = time.time() - start
    
    points = sum([len(table.records) for table in result])
    print(f"24h HOURLY: {elapsed:.3f}s - {points} pontos")
    return elapsed, points

# Cenário 5: Query via Flask (end-to-end)
def test_flask_endpoint():
    url = "http://10.64.137.6:5000/api/data"
    params = {
        'sensor_id': 2,
        'start': '-5m',
        'field': 'LAeq'
    }
    
    start = time.time()
    response = requests.get(url, params=params)
    elapsed = time.time() - start
    
    data = response.json()
    points = len(data.get('values', []))
    print(f"FLASK 5min: {elapsed:.3f}s - {points} pontos - HTTP {response.status_code}")
    return elapsed, points

# Executar todos os testes
if __name__ == "__main__":
    print("=== TESTES DE PERFORMANCE ===\n")
    
    print("Teste 1: 5 minutos RAW")
    test_5min_raw()
    time.sleep(1)
    
    print("\nTeste 2: 1 hora RAW")
    test_1h_raw()
    time.sleep(1)
    
    print("\nTeste 3: 1 hora AGREGADO (1min)")
    test_1h_aggregated()
    time.sleep(1)
    
    print("\nTeste 4: 24 horas AGREGADO (1h)")
    test_24h_hourly()
    time.sleep(1)
    
    print("\nTeste 5: Flask Endpoint (5min)")
    test_flask_endpoint()
    
    print("\n=== FIM DOS TESTES ===")