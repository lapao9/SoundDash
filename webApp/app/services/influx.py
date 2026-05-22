from datetime import datetime
from influxdb_client import InfluxDBClient
from app.config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG


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


def get_client():
    return InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)


def to_rfc3339(dt: datetime) -> str:
    return dt.isoformat("T") + "Z"


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


def pode_usar_bucket_agregado(duration_days: float, field: str = None) -> bool:
    if duration_days < 7:
        return False
    if field is None:
        return False
    return field in CAMPOS_AGREGADOS
