from datetime import datetime, timedelta, timezone
from influxdb_client import InfluxDBClient
from app.config import (
    INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, LOCAL_TZ,
    INFLUXDB_BUCKET, INFLUXDB_BUCKET_1M, INFLUXDB_BUCKET_1H
)

"""
Este ficheiro serve para encapsular a lógica de acesso ao InfluxDB, 
incluindo a criação do cliente, conversão de datas e 
verificação de campos agregados.
é chamado/executado em 
"""

CAMPOS_AGREGADOS = [
    "LAEA", "LAEC", "LAEZ",
    "00025_Hz", "00031.5_Hz", "00040_Hz",
    "00050_Hz", "00063_Hz", "00080_Hz", "00100_Hz", "00125_Hz",
    "00160_Hz", "00200_Hz", "00250_Hz", "00315_Hz", "00400_Hz",
    "00500_Hz", "00630_Hz", "00800_Hz", "01000_Hz", "01250_Hz",
    "01600_Hz", "02000_Hz", "02500_Hz", "03150_Hz", "04000_Hz",
    "05000_Hz", "06300_Hz", "08000_Hz", "10000_Hz", "12500_Hz",
    "16000_Hz", "20000_Hz"
]

# Todos os campos que as tasks guardam nos buckets agregados (CAMPOS_AGREGADOS em escala linear)
CAMPOS_NOS_BUCKETS_AGREGADOS = set(CAMPOS_AGREGADOS) | {
    "n", "LCpeak", "LAFmax", "LAFmin", "EventDetect", *[f"EventType{i}" for i in range(1, 11)]
}


def get_client():
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)


def to_rfc3339(dt: datetime) -> str:
    return dt.isoformat("T") + "Z"


def local_to_rfc3339(dt: datetime) -> str:
    """Interpreta uma data sem fuso como hora de Lisboa e devolve RFC3339 em UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def to_local(dt: datetime) -> datetime:
    """Converte um datetime UTC (vindo do InfluxDB) para hora de Lisboa."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def parse_interval_to_days(interval_str: str) -> float:
    if not interval_str or not interval_str.startswith('-'):
        return 0
    try:
        value = int(interval_str[1:-1])
        unit  = interval_str[-1]
        if unit == 'm':
            return value / (60 * 24)
        elif unit == 'h':
            return value / 24
        elif unit == 'd':
            return value
        return 0
    except Exception:
        return 0


# Escolha dos dados conforme a duração pedida (mesmos limites das queries do Grafana)
LIMITE_RAW = timedelta(hours=12)
LIMITE_1M  = timedelta(days=31)


def escolher_bucket(duracao: timedelta) -> str:
    """raw até 12 h, médias por minuto até 31 dias, médias por hora acima disso."""
    if duracao <= LIMITE_RAW:
        return INFLUXDB_BUCKET
    if duracao <= LIMITE_1M:
        return INFLUXDB_BUCKET_1M
    return INFLUXDB_BUCKET_1H
