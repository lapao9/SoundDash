"""
rename_sensor.py
Copia todos os dados de um measurement para outro nome, sem perder dados.
Uso: python rename_sensor.py <nome_antigo> <nome_novo>
Exemplo: python rename_sensor.py Sensor2 Sensor100

Após verificar que os dados foram copiados, apaga o measurement original.
"""

import sys
from datetime import timezone
from influxdb_client import InfluxDBClient, WriteOptions, Point
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUX_URL = "http://10.64.137.6:8086"
TOKEN      = "LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA=="
ORG        = "ISEL"
BUCKET     = "SoundDashHosp"
BATCH_SIZE = 500


def contar_pontos(query_api, measurement):
    q = f'''
    from(bucket: "{BUCKET}")
      |> range(start: 0)
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
      |> count()
      |> sum()
    '''
    try:
        tables = query_api.query(q, org=ORG)
        total = sum(r.get_value() for t in tables for r in t.records)
        return total
    except Exception:
        return -1


def migrar(nome_antigo, nome_novo):
    print(f"\n🔄  A migrar: {nome_antigo}  →  {nome_novo}")
    print(f"    Bucket: {BUCKET}  |  URL: {INFLUX_URL}\n")

    with InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG) as client:
        query_api = client.query_api()
        write_api = client.write_api(write_options=WriteOptions(
            batch_size=BATCH_SIZE,
            flush_interval=5000,
            write_type=SYNCHRONOUS
        ))

        # Contar pontos originais
        total_orig = contar_pontos(query_api, nome_antigo)
        print(f"📊  Pontos em '{nome_antigo}': {total_orig}")

        # Ler todos os dados do measurement antigo
        query = f'''
        from(bucket: "{BUCKET}")
          |> range(start: 0)
          |> filter(fn: (r) => r["_measurement"] == "{nome_antigo}")
        '''

        print("⏳  A ler dados...")
        tables = query_api.query(query, org=ORG)

        batch = []
        total_escritos = 0
        total_erros = 0

        for table in tables:
            for record in table.records:
                try:
                    field = record.get_field()
                    value = record.get_value()
                    time  = record.get_time()

                    if field is None or value is None or time is None:
                        continue

                    # Criar Point com o novo measurement name
                    p = (
                        Point(nome_novo)
                        .field(field, value)
                        .time(time.astimezone(timezone.utc))
                    )

                    # Copiar tags (exceto as internas _*)
                    for k, v in record.values.items():
                        if not k.startswith('_') and k not in ('result', 'table') and v is not None:
                            p = p.tag(k, str(v))

                    batch.append(p)
                    total_escritos += 1

                    if len(batch) >= BATCH_SIZE:
                        write_api.write(bucket=BUCKET, org=ORG, record=batch)
                        batch = []
                        print(f"  ✅  {total_escritos} pontos copiados...", end="\r")

                except Exception as e:
                    total_erros += 1
                    continue

        # Enviar restantes
        if batch:
            write_api.write(bucket=BUCKET, org=ORG, record=batch)

        print(f"\n\n✅  Cópia concluída!")
        print(f"    Pontos copiados : {total_escritos}")
        print(f"    Erros ignorados : {total_erros}")

        # Verificar contagem no novo measurement
        total_novo = contar_pontos(query_api, nome_novo)
        print(f"    Pontos em '{nome_novo}': {total_novo}")

        if total_novo >= total_escritos and total_escritos > 0:
            print(f"\n⚠️   Os dados estão copiados. Para apagar '{nome_antigo}', corre:")
            print(f"     influx delete --bucket {BUCKET} --org {ORG} \\")
            print(f'       --predicate \'_measurement="{nome_antigo}"\' \\')
            print(f"       --start 1970-01-01T00:00:00Z --stop 2099-01-01T00:00:00Z")
            print(f"\n    Ou apaga pela UI do InfluxDB em: http://10.64.137.6:8086")
            print(f"    Data → Buckets → {BUCKET} → Delete Data → _measurement = {nome_antigo}")
        else:
            print(f"\n❌  Contagem não bate certo. Verifica antes de apagar o original.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python rename_sensor.py <nome_antigo> <nome_novo>")
        print("Ex:  python rename_sensor.py Sensor2 Sensor100")
        sys.exit(1)

    migrar(sys.argv[1], sys.argv[2])
