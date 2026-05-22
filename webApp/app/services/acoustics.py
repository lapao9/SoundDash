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
    if None in (Lday, Levening, Lnight):
        return None
    num = (
        12 * db_to_linear(Lday) +
         4 * db_to_linear(Levening + 5) +
         8 * db_to_linear(Lnight + 10)
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


def load_class_labels(filepath: str) -> dict:
    df = pd.read_csv(filepath)
    return dict(zip(df["index"], df["display_name"]))
