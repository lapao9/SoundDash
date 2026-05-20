from influxdb_client import InfluxDBClient
from datetime import datetime, timedelta
import math

# Configurações do InfluxDB
INFLUX_URL = "http://localhost:8086"
ORG = "ISEL"
TOKEN = "JkclBe0fO1-Wx6sHXahvdFd_W1YOS1Y3Vn8RgkUH5d4U4MMb24-YDtHjhZpihw9amEbdJYISAmW3yiy-NO5tCg=="
BUCKET = "SoundDashHosp"

# Data de teste -> 29/09/2025 08:00
end_date = datetime(2025, 9, 29, 8, 0, 0)
start_date = end_date - timedelta(days=1)  # 28/09/2025 00:00


def to_rfc3339(dt: datetime) -> str:
    """Converte datetime para string RFC3339"""
    return dt.isoformat("T") + "Z"


def fetch_avg(client, start: datetime, stop: datetime):
    """Busca valores de LAEA e calcula a média em dB corretamente (linear → média → dB)"""
    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {to_rfc3339(start)}, stop: {to_rfc3339(stop)})
      |> filter(fn: (r) => r["_measurement"] == "sensor1")
      |> filter(fn: (r) => r["_field"] == "LAEA")
    '''
    tables = client.query_api().query(query, org=ORG)

    values = []
    for table in tables:
        for record in table.records:
            val = record.get_value()
            if val is not None:
                # converter dB → linear
                values.append(10 ** (float(val) / 10))

    if not values:
        return None

    # média linear → voltar a dB
    mean_linear = sum(values) / len(values)
    return 10 * math.log10(mean_linear)



def calcular_lden(Lday: float, Levening: float, Lnight: float) -> float:
    """Calcula o Lden em dB"""
    num = (
        12 * (10 ** (Lday / 10))
        + 4 * (10 ** ((Levening + 5) / 10))
        + 8 * (10 ** ((Lnight + 10) / 10))
    )
    return 10 * math.log10(num / 24)


def main():
    d0 = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    d8 = start_date.replace(hour=8, minute=0, second=0, microsecond=0)
    d16 = start_date.replace(hour=16, minute=0, second=0, microsecond=0)
    d24 = start_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        Lnight = fetch_avg(client, d0, d8)      # 00h–08h
        Lday = fetch_avg(client, d8, d16)       # 08h–16h
        Levening = fetch_avg(client, d16, d24)  # 16h–24h

    print("Médias LAEA:")
    print("  Noite  (00–07h59):", Lnight)
    print("  Dia    (08–15h59):", Lday)
    print("  Tarde  (16–23h59):", Levening)

    if None not in (Lday, Levening, Lnight):
        Lden = calcular_lden(Lday, Levening, Lnight)
        print(f"\n➡️  Lden calculado: {Lden:.2f} dB")
    else:
        print("\n❌ Erro: não foi possível obter todas as médias de LAEA.")


if __name__ == "__main__":
    main()
