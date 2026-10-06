import math
import pandas as pd
from influxdb_client import InfluxDBClient
from app.config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET
from app.services.influx import to_local


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


# Campos em dB cuja média tem de ser energética (dB -> linear -> média -> dB)
CAMPOS_ENERGIA = {'LAEA', 'LAEC', 'LAEZ', 'LZeq', 'LCeq', 'LAeq', 'LAEA_SLOW_Event'}
# Campos de pico/máximo e mínimo: agregam-se com max / min, nunca com média
CAMPOS_MAX = {'LCpeak', 'LCpeakT', 'LApeak', 'LApeakT', 'LZpeak', 'LZpeakT', 'LAFmax', 'LAFmaxT'}
CAMPOS_MIN = {'LAFmin', 'LAFminT'}


def flux_media_energetica(every: str, time_src: str = '_stop') -> str:
    """Pipeline Flux para média energética numa janela (a query tem de fazer import "math")."""
    return f'''
      |> map(fn: (r) => ({{r with _value: math.pow(x: 10.0, y: float(v: r._value) / 10.0)}}))
      |> aggregateWindow(every: {every}, fn: mean, createEmpty: false, timeSrc: "{time_src}")
      |> map(fn: (r) => ({{r with _value: 10.0 * math.log10(x: r._value)}}))'''


def _field_filter(campos) -> str:
    return ' or '.join([f'r["_field"] == "{c}"' for c in campos])


def fetch_serie_db(sensor: str, campo: str, start: str, stop: str) -> list:
    """Valores raw de um campo: lista de (datetime em hora local, valor)."""
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "{campo}")
    '''
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=60000)
    try:
        tables = client.query_api().query(query, org=INFLUXDB_ORG)
        serie = []
        for table in tables:
            for record in table.records:
                v = record.get_value()
                if v is not None:
                    serie.append((to_local(record.get_time()), float(v)))
        return serie
    except Exception as e:
        print(f"Erro ao buscar valores: {e}")
        return []
    finally:
        client.close()


def fetch_hourly_campos(sensor: str, start: str, stop: str, campos: list) -> list:
    """
    Agregação horária por campo: média energética para níveis equivalentes (LAEA...),
    max para picos/máximos, min para mínimos.
    Devolve [{'time': datetime em hora local (início da hora), 'field': str, 'value': float}].
    """
    base = f'''from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")'''

    grupos = {
        'energia': [c for c in campos if c in CAMPOS_ENERGIA],
        'max':     [c for c in campos if c in CAMPOS_MAX],
        'min':     [c for c in campos if c in CAMPOS_MIN],
    }
    grupos['mean'] = [c for c in campos if not any(c in g for g in grupos.values())]

    streams = []
    for nome, lista in grupos.items():
        if not lista:
            continue
        s = f'{base}\n      |> filter(fn: (r) => {_field_filter(lista)})'
        if nome == 'energia':
            s += flux_media_energetica('1h', '_start')
        else:
            s += f'\n      |> aggregateWindow(every: 1h, fn: {nome}, createEmpty: false, timeSrc: "_start")'
        streams.append(s)

    if not streams:
        return []
    if len(streams) == 1:
        query = 'import "math"\n' + streams[0]
    else:
        query = 'import "math"\nunion(tables: [\n' + ',\n'.join(streams) + '\n])'

    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=60000)
    try:
        tables = client.query_api().query(query, org=INFLUXDB_ORG)
        result = []
        for table in tables:
            for record in table.records:
                v = record.get_value()
                if v is not None:
                    result.append({'time': to_local(record.get_time()),
                                   'field': record.get_field(),
                                   'value': float(v)})
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
    Returns {(day_str, hour): count} of distinct event intervals per local hour.
    """
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "EventDetect")
      |> filter(fn: (r) => r["_value"] > 0)
      |> sort(columns: ["_time"])
    '''
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=60000)
    try:
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

        # Count intervals per (day_str, hour) in local time, using interval start time
        counts = {}
        for t in interval_starts:
            t = to_local(t)
            key = (t.strftime('%Y-%m-%d'), t.hour)
            counts[key] = counts.get(key, 0) + 1

        return counts
    except Exception as e:
        print(f"Erro ao buscar event intervals: {e}")
        return {}
    finally:
        client.close()


def load_class_labels(filepath: str) -> dict:
    df = pd.read_csv(filepath)
    return dict(zip(df["index"], df["display_name"]))
