"""
Preenche os buckets agregados (SoundDashHosp_1m e SoundDashHosp_1h) com os dados antigos.

As tasks só processam dados novos. Este script corre uma vez, de hora a hora, da mais recente
para a mais antiga (os meses recentes ficam disponíveis primeiro), usando EXATAMENTE as
mesmas queries das tasks (lê os ficheiros Tasks/task_agregar_1m.flux e task_agregar_1h.flux).

Pode ser interrompido (Ctrl+C) e retomado: o progresso fica em preencher_agregados_estado.txt.
Voltar a processar uma hora não estraga nada (os pontos são reescritos com os mesmos valores).

Uso (na VM, na pasta do projeto):
    python Influx_Scripts\\preencher_agregados.py                 # todo o histórico
    python Influx_Scripts\\preencher_agregados.py --desde 2026-06-01 --pausa 2
    python Influx_Scripts\\preencher_agregados.py --verificar 2026-10-20 --sensor sensor1
"""
import argparse
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from influxdb_client import InfluxDBClient

PASTA = os.path.dirname(os.path.abspath(__file__))
ESTADO = os.path.join(PASTA, 'preencher_agregados_estado.txt')
TASKS = [os.path.join(PASTA, 'Tasks', 'task_agregar_1m.flux'),
         os.path.join(PASTA, 'Tasks', 'task_agregar_1h.flux')]
BUCKET_RAW = 'SoundDashHosp'


def config_por_omissao():
    """URL/token/org da webapp (webApp/app/config.py)."""
    sys.path.insert(0, os.path.join(PASTA, '..', 'webApp'))
    try:
        from app.config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG
        return INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG
    except Exception:
        return None, None, None


def flux_da_task(caminho: str) -> str:
    """Texto da task com o range relativo (ex. range(start: -5m)) substituído por marcadores."""
    texto = open(caminho, encoding='utf-8').read()
    texto = re.sub(r'^option task\s*=.*$', '', texto, flags=re.M)
    texto, n = re.subn(r'range\(start: -\w+\)', 'range(start: {INICIO}, stop: {FIM})', texto)
    if not n:
        raise ValueError(f'{caminho}: não encontrei "range(start: -...)"')
    return texto


def rfc(d: datetime) -> str:
    return d.strftime('%Y-%m-%dT%H:%M:%SZ')


def primeiro_dado(query_api, org) -> datetime:
    tabelas = query_api.query(f'''
    from(bucket: "{BUCKET_RAW}")
      |> range(start: 0)
      |> filter(fn: (r) => r._field == "LAEA")
      |> first()
    ''', org=org)
    tempos = [rec.get_time() for t in tabelas for rec in t.records]
    if not tempos:
        raise SystemExit('Não há dados LAEA no bucket raw.')
    return min(tempos)


def hora_cheia(d: datetime) -> datetime:
    return d.replace(minute=0, second=0, microsecond=0)


def preencher(client, org, desde, ate, pausa, recomecar):
    query_api = client.query_api()
    modelos = [flux_da_task(c) for c in TASKS]

    if desde is None:
        desde = primeiro_dado(query_api, org)
    desde = hora_cheia(desde)

    # Retoma de onde ficou (o estado guarda a hora mais antiga já processada)
    if not recomecar and os.path.exists(ESTADO):
        feito = datetime.fromisoformat(open(ESTADO).read().strip())
        if feito <= ate:
            print(f'A retomar: já processado até {feito:%Y-%m-%d %H:%M} UTC (use --recomecar para ignorar).')
            ate = feito

    total = int((ate - desde).total_seconds() // 3600)
    print(f'A processar {total} horas: de {ate:%Y-%m-%d %H:%M} para trás até {desde:%Y-%m-%d %H:%M} UTC.')
    t0 = time.time()
    hora = ate
    feitas = 0
    while hora > desde:
        ini = hora - timedelta(hours=1)
        for modelo in modelos:
            query_api.query(modelo.replace('{INICIO}', rfc(ini)).replace('{FIM}', rfc(hora)), org=org)
        hora = ini
        feitas += 1
        with open(ESTADO, 'w') as f:
            f.write(hora.isoformat())
        decorrido = time.time() - t0
        falta = decorrido / feitas * (total - feitas)
        print(f'\r{feitas}/{total} horas ({hora:%Y-%m-%d %H:%M} UTC) — falta ~{falta / 60:.0f} min   ',
              end='', flush=True)
        time.sleep(pausa)
    print('\nConcluído.')


def verificar(client, org, dia: str, sensor: str):
    """Compara o LAeq de um dia (UTC) calculado sobre o raw com o dos buckets 1m e 1h."""
    query_api = client.query_api()
    ini = datetime.fromisoformat(dia).replace(tzinfo=timezone.utc)
    rng = f'range(start: {rfc(ini)}, stop: {rfc(ini + timedelta(days=1))})'

    raw = query_api.query(f'''
    import "math"
    lin = from(bucket: "{BUCKET_RAW}") |> {rng}
      |> filter(fn: (r) => r._measurement == "{sensor}" and r._field == "LAEA") |> group()
      |> map(fn: (r) => ({{r with _value: math.pow(x: 10.0, y: float(v: r._value) / 10.0)}}))
    union(tables: [lin |> sum() |> set(key: "k", value: "soma"),
                   lin |> count() |> map(fn: (r) => ({{r with _value: float(v: r._value)}})) |> set(key: "k", value: "n")])
    ''', org=org)
    v = {rec.values['k']: rec.get_value() for t in raw for rec in t.records}
    if not v.get('n'):
        print('Sem dados raw nesse dia.')
        return
    laeq_raw = 10 * math.log10(v['soma'] / v['n'])
    print(f'Raw:       LAeq = {laeq_raw:.3f} dB  ({int(v["n"])} amostras)')

    for bucket in ('SoundDashHosp_1m', 'SoundDashHosp_1h'):
        tabelas = query_api.query(f'''
        from(bucket: "{bucket}") |> {rng}
          |> filter(fn: (r) => r._measurement == "{sensor}" and (r._field == "LAEA" or r._field == "n"))
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        ''', org=org)
        soma = n = 0.0
        for t in tabelas:
            for rec in t.records:
                if rec.values.get('LAEA') is not None and rec.values.get('n'):
                    soma += rec.values['LAEA'] * rec.values['n']
                    n += rec.values['n']
        if not n:
            print(f'{bucket}: sem dados (ainda não preenchido?)')
            continue
        laeq = 10 * math.log10(soma / n)
        print(f'{bucket}: LAeq = {laeq:.3f} dB  ({int(n)} amostras)  diferença = {laeq - laeq_raw:+.4f} dB')


def main():
    url0, token0, org0 = config_por_omissao()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--desde', help='primeiro dia a processar (AAAA-MM-DD); por omissão, o 1.º dado do raw')
    p.add_argument('--ate', help='processar até este dia/hora (AAAA-MM-DD[THH]); por omissão, a hora atual')
    p.add_argument('--pausa', type=float, default=1.0, help='segundos de pausa entre horas (alivia a VM)')
    p.add_argument('--recomecar', action='store_true', help='ignorar o progresso guardado')
    p.add_argument('--verificar', metavar='DIA', help='comparar o LAeq de um dia (UTC) raw vs buckets')
    p.add_argument('--sensor', default='sensor1', help='sensor para --verificar')
    p.add_argument('--url', default=url0)
    p.add_argument('--token', default=token0)
    p.add_argument('--org', default=org0)
    a = p.parse_args()
    if not (a.url and a.token and a.org):
        p.error('não consegui ler webApp/app/config.py: indique --url, --token e --org')

    with InfluxDBClient(url=a.url, token=a.token, org=a.org, timeout=600000) as client:
        if a.verificar:
            verificar(client, a.org, a.verificar, a.sensor)
            return
        utc = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        desde = utc(a.desde) if a.desde else None
        ate = hora_cheia(utc(a.ate)) if a.ate else hora_cheia(datetime.now(timezone.utc))
        try:
            preencher(client, a.org, desde, ate, a.pausa, a.recomecar)
        except KeyboardInterrupt:
            print('\nInterrompido. Volte a correr o mesmo comando para continuar.')


if __name__ == '__main__':
    main()
