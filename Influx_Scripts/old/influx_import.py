"""
influx_import.py
Importa o CSV real do sensor para o InfluxDB.
Uso: python3 influx_import.py <ficheiro.csv>
"""

import csv
import sys
import math
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS

# ─── Configurações — ───────────────────────────────────
INFLUX_URL = "http://localhost:8086"
TOKEN      = "zn7AgCy9Eb8U2wSXUfYcKR3snX81byyHDapRBGeisbJ-HfUzkyTp3MM5NMyFdvY2R9oV78xtJP3Fhs5N7_yOnQ=="
ORG        = "myorg"          # nome da organização, InfluxDB
BUCKET     = "sounddash"    
BATCH_SIZE = 500              # pontos enviados por lote
# ─────────────────────────────────────────────────────────────────────────────

# Campos numéricos do CSV (todos exceto TimeStamp e SensorID)
NUMERIC_FIELDS = [
    "LAEZ","LAEC","LAEA","LZpeak","LZpeakT","LCpeak","LCpeakT",
    "LApeak","LApeakT","LAFmax","LAFmaxT","LAFmin","LAFminT",
    "LZeq","LCeq","LAeq",
    "BT25","BT31_5","BT40","BT50","BT63","BT80","BT100","BT125",
    "BT160","BT200","BT250","BT315","BT400","BT500","BT630","BT800",
    "BT1000","BT1250","BT1600","BT2000","BT2500","BT3150","BT4000",
    "BT5000","BT6300","BT8000","BT10000","BT12500","BT16000","BT20000",
    "LAEA_SLOW_Event","EventDetect",
    "EventType1","EventType2","EventType3","EventType4","EventType5",
    "EventType6","EventType7","EventType8","EventType9","EventType10",
    "Class1ID","Class1Score","Class2ID","Class2Score","Class3ID","Class3Score"
]

def sensor_id_to_name(sensor_id: float) -> str:
    """Converte o SensorID numérico para nome tipo 'Sensor3'."""
    return f"Sensor{int(sensor_id)}"

def build_line_protocol(measurement: str, timestamp_ns: int, fields: dict) -> str:
    """Constrói uma linha no formato InfluxDB Line Protocol."""
    field_parts = []
    for k, v in fields.items():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        field_parts.append(f"{k}={v}")
    if not field_parts:
        return None
    return f"{measurement} {','.join(field_parts)} {timestamp_ns}"

def import_csv(filepath: str):
    print(f"\n A ler ficheiro: {filepath}")

    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        write_api = client.write_api(write_options=WriteOptions(
            batch_size=BATCH_SIZE,
            flush_interval=5000,
            write_type=SYNCHRONOUS
        ))

        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            batch = []
            total = 0
            skipped = 0

            for row in reader:
                try:
                    ts = float(row["TimeStamp"])
                    sensor_name = sensor_id_to_name(float(row["SensorID"]))
                    timestamp_ns = int(ts * 1_000_000_000)

                    fields = {} #fiels vai ter os dados do csv, exceto timestamp e sensorid, e é do tipo { "LAEZ": 45.2, "LAEC": 40.1, ... }
                    for field in NUMERIC_FIELDS:
                        val = row.get(field, "").strip()
                        if val == "" or val is None:
                            continue
                        try:
                            fields[field] = float(val)
                        except ValueError:
                            continue

                    line = build_line_protocol(sensor_name, timestamp_ns, fields)
                    if line:
                        batch.append(line)
                        total += 1
                    else:
                        skipped += 1

                    # Enviar em lotes
                    if len(batch) >= BATCH_SIZE:
                        write_api.write(bucket=BUCKET, org=ORG, record=batch,
                                        write_precision="ns")
                        batch = []
                        print(f"  ✅ {total} pontos enviados...", end="\r")

                except Exception as e:
                    skipped += 1
                    continue

            # Enviar restantes
            if batch:
                write_api.write(bucket=BUCKET, org=ORG, record=batch,
                                write_precision="ns")

        print(f"\n✅ Importação concluída!")
        print(f"   Pontos inseridos : {total}")
        print(f"   Linhas ignoradas : {skipped}")
        print(f"   Measurement      : Sensor{int(float(open(filepath).readlines()[1].split(',')[1]))}")
        print(f"   Bucket           : {BUCKET}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 influx_import.py <ficheiro.csv>")
        sys.exit(1)
    import_csv(sys.argv[1])

