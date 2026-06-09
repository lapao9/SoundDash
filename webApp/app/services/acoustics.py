import math
import pandas as pd
from influxdb_client import InfluxDBClient
from app.config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET


def db_to_linear(db_value: float) -> float:
    return 10 ** (db_value / 10.0)


def linear_to_db(linear_value: float) -> float:
    if linear_value <= 0:
        return None
    return 10 * math.log10(linear_value)


def calcular_media_db(valores_db: list) -> float:
    if not valores_db:
        return None
    lineares = [db_to_linear(v) for v in valores_db if v is not None]
    if not lineares:
        return None
    return linear_to_db(sum(lineares) / len(lineares))


def calcular_percentil_db(valores_db: list, percentil: float) -> float:
    if not valores_db:
        return None
    lineares = sorted([db_to_linear(v) for v in valores_db if v is not None])
    if not lineares:
        return None
    idx = min(int(len(lineares) * percentil), len(lineares) - 1)
    return linear_to_db(lineares[idx])


def calcular_lden_db(Lday: float, Levening: float, Lnight: float) -> float:
    """Official EU Lden: Ld=07-19h (12h), Le=19-23h (4h+5dB), Ln=23-07h (8h+10dB)."""
    if None in (Lday, Levening, Lnight):
        return None
    num = (
        12 * db_to_linear(Lday) +
        4  * db_to_linear(Levening + 5) +
        8  * db_to_linear(Lnight + 10)
    )
    return linear_to_db(num / 24)


def fetch_valores_db(sensor: str, campo: str, start: str, stop: str) -> list:
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "{campo}")
    '''
    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        tables = client.query_api().query(query, org=INFLUXDB_ORG)
        valores = []
        for table in tables:
            for record in table.records:
                v = record.get_value()
                if v is not None:
                    valores.append(float(v))
        return valores
    except Exception as e:
        print(f"Erro ao buscar valores: {e}")
        return []
    finally:
        client.close()


def fetch_hourly_campos(sensor: str, start: str, stop: str, campos: list) -> list:
    """Return list of {'time': datetime, 'field': str, 'value': float} with hourly mean per field."""
    field_filter = ' or '.join([f'r["_field"] == "{c}"' for c in campos])
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => {field_filter})
      |> aggregateWindow(every: 1h, fn: mean, createEmpty: false, timeSrc: "_start")
    '''
    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        tables = client.query_api().query(query, org=INFLUXDB_ORG)
        result = []
        for table in tables:
            for record in table.records:
                v = record.get_value()
                t = record.get_time()
                f = record.get_field()
                if v is not None:
                    result.append({'time': t, 'field': f, 'value': float(v)})
        return result
    except Exception as e:
        print(f"Erro ao buscar campos horários: {e}")
        return []
    finally:
        client.close()


def fetch_event_intervals_by_hour(sensor: str, start: str, stop: str) -> dict:
    """
    Replicates the grouping logic from eventos.js:
    consecutive EventDetect>0 records with gap <=5s = one event.
    Returns {(day_str, hour): count} of distinct event intervals per hour.
    """
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "EventDetect")
      |> filter(fn: (r) => r["_value"] > 0)
      |> sort(columns: ["_time"])
    '''
    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        tables = client.query_api().query(query, org=INFLUXDB_ORG)
        times = sorted(
            record.get_time()
            for table in tables
            for record in table.records
            if record.get_time() is not None
        )

        if not times:
            return {}

        # Group by 5-second gap — same rule as eventos.js
        interval_starts = [times[0]]
        for i in range(1, len(times)):
            if (times[i] - times[i - 1]).total_seconds() > 5:
                interval_starts.append(times[i])

        # Count intervals per (day_str, hour) using interval start time
        counts = {}
        for t in interval_starts:
            key = (t.strftime('%Y-%m-%d'), t.hour)
            counts[key] = counts.get(key, 0) + 1

        return counts
    except Exception as e:
        print(f"Erro ao buscar event intervals: {e}")
        return {}
    finally:
        client.close()


def fetch_laeq_horario(sensor: str, start: str, stop: str) -> list:
    """Return list of {'time': datetime, 'value': float} with hourly LAeq."""
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}" and r["_field"] == "LAEA")
      |> aggregateWindow(every: 1h, fn: mean, createEmpty: false, timeSrc: "_start")
    '''
    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        tables = client.query_api().query(query, org=INFLUXDB_ORG)
        result = []
        for table in tables:
            for record in table.records:
                v = record.get_value()
                t = record.get_time()
                if v is not None:
                    result.append({'time': t, 'value': float(v)})
        return result
    except Exception as e:
        print(f"Erro ao buscar LAeq horário: {e}")
        return []
    finally:
        client.close()


def load_class_labels(filepath: str) -> dict:
    df = pd.read_csv(filepath)
    return dict(zip(df["index"], df["display_name"]))
