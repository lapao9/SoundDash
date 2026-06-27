"""
influx_perf_tab2.py

Mede as 4 queries da Tabela tab:perf2 do relatório final.
Corre na VM do ISEL onde o InfluxDB tem ~4 meses de dados reais.

Uso: python influx_perf_tab2.py
"""

from influxdb_client import InfluxDBClient
from time import perf_counter

INFLUX_URL  = "http://localhost:8086"
TOKEN       = "VfIVKgRa7ZcYF_LdpSWHliW2u3M_Q8iLUw6SUNReVbbjVio957NRpJollg9p-LxqJKm4CHOpupQPQ4fApef2uQ=="
ORG         = "ISEL"
BUCKET      = "SoundDashHosp"
MEASUREMENT = "Sensor1"


def run(client, query, label):
    print(f"\n  -> {label}")
    t0 = perf_counter()
    try:
        tables = client.query_api().query(query, org=ORG)
        count  = sum(len(t.records) for t in tables)
        elapsed = perf_counter() - t0
        print(f"     {count} registos  |  {elapsed:.3f}s")
        return count, elapsed
    except Exception as e:
        elapsed = perf_counter() - t0
        print(f"     ERRO: {e}  ({elapsed:.3f}s)")
        return 0, elapsed


if __name__ == "__main__":
    print("\nA ligar ao InfluxDB...")
    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        client.ping()
        print("Ligado.\n")

        results = []

        # 1 dia sem agregacao
        q = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -1d)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
        '''
        results.append(("1 dia  | sem agregacao",
                         *run(client, q, "1 dia | sem agregacao")))

        # 1 semana com agregacao 1 min
        q = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -7d)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
        '''
        results.append(("1 semana | agregacao 1 min",
                         *run(client, q, "1 semana | agregacao 1 min")))

        # 1 mes com agregacao 1 hora
        q = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -30d)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
        '''
        results.append(("1 mes  | agregacao 1 hora",
                         *run(client, q, "1 mes | agregacao 1 hora")))

        # 3 meses com agregacao 1 hora
        q = f'''
        from(bucket: "{BUCKET}")
          |> range(start: -90d)
          |> filter(fn: (r) => r["_measurement"] == "{MEASUREMENT}")
          |> filter(fn: (r) => r["_field"] == "LAEA")
          |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
        '''
        results.append(("3 meses | agregacao 1 hora",
                         *run(client, q, "3 meses | agregacao 1 hora")))

        print("\n" + "="*55)
        print("RESULTADOS PARA tab:perf2")
        print("="*55)
        print(f"  {'Query':<30} {'Registos':>10} {'Tempo':>8}")
        print("  " + "-"*50)
        for label, count, elapsed in results:
            print(f"  {label:<30} {count:>10}  {elapsed:.3f}s")
        print()
