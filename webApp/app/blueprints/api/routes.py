from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required
from datetime import datetime, timedelta
from collections import defaultdict
from io import StringIO
import csv
import json
import re

from influxdb_client import InfluxDBClient
from app.config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET
from app.services.influx import (
    get_client, local_to_rfc3339, to_local, parse_interval_to_days, pode_usar_bucket_agregado
)
from app.services.acoustics import (
    fetch_event_intervals_by_hour, flux_media_energetica,
    fetch_horas_agregadas, calcular_indicadores_dias, fetch_indicadores_intervalo,
    AcumuladorEnergia, dia_atribuido, turno_da_hora, TURNO_INICIO_DIA, INDICADORES_DIA
)
from app.services.system_config import load_system_config, save_system_config

api_bp = Blueprint('api', __name__, url_prefix='/api')


def sensor_valido(nome: str) -> bool:
    """Nome de measurement seguro para usar dentro de queries Flux."""
    return bool(re.fullmatch(r'[A-Za-z0-9_\-]+', nome or ''))


# Ordem das colunas do CSV gerado no sensor (SoundMeterSemaf_ver3_class.py)
_BANDAS = ['25', '31_5', '40', '50', '63', '80', '100', '125', '160', '200', '250', '315',
           '400', '500', '630', '800', '1000', '1250', '1600', '2000', '2500', '3150',
           '4000', '5000', '6300', '8000', '10000', '12500', '16000', '20000']

CSV_COLUNAS_SENSOR = (
    ['TimeStamp', 'SensorID', 'LAEZ', 'LAEC', 'LAEA', 'LZpeak', 'LZpeakT', 'LCpeak', 'LCpeakT',
     'LApeak', 'LApeakT', 'LAFmax', 'LAFmaxT', 'LAFmin', 'LAFminT', 'LZeq', 'LCeq', 'LAeq']
    + [f'BT{b}' for b in _BANDAS]
    + ['LAEA_SLOW_Event', 'EventDetect'] + [f'EventType{i}' for i in range(1, 11)]
    + ['Class1ID', 'Class1Score', 'Class2ID', 'Class2Score', 'Class3ID', 'Class3Score']
)

# Nome da coluna do sensor -> nome do campo no InfluxDB (bandas: BT40 -> 00040_Hz, BT31_5 -> 00031.5_Hz)
CSV_CAMPO_INFLUX = {
    f'BT{b}': ('00031.5_Hz' if b == '31_5' else f'{int(b):05d}_Hz') for b in _BANDAS
}


@api_bp.route('/lden')
def get_lden():
    """Indicadores de um dia: turnos (dia de turnos 08h->08h) e Ld/Le/Ln/Lden (ciclo 07h->07h)."""
    start_str = request.args.get('start')
    sensor    = request.args.get('sensor_id')

    if not start_str or not sensor:
        return jsonify({'error': "Parâmetros 'start' e 'sensor_id' são obrigatórios"}), 400
    if not sensor_valido(sensor):
        return jsonify({'error': 'Nome de sensor inválido.'}), 400

    # 'start' identifica o dia (hora local de Lisboa); só a parte da data conta
    try:
        dia = datetime.fromisoformat(start_str[:10])
    except Exception:
        return jsonify({'error': 'Formato de data inválido'}), 400

    # Até às 08:00 do dia seguinte: o T3 (00-08h) e o Ln (23-07h) pertencem a este dia
    horas = fetch_horas_agregadas(sensor, local_to_rfc3339(dia),
                                  local_to_rfc3339(dia + timedelta(days=1, hours=TURNO_INICIO_DIA)))
    por_dia, _ = calcular_indicadores_dias(horas, [dia.date()])
    v = por_dia[dia.date()]

    if all(v[k] is None for k in ('turno1', 'turno2', 'turno3', 'ld', 'le', 'ln')):
        return jsonify({'error': 'Sem dados suficientes'}), 404

    def r(x): return round(x, 2) if x is not None else None

    return jsonify({
        'turno1': r(v['turno1']),
        'turno2': r(v['turno2']),
        'turno3': r(v['turno3']),
        'ld':     r(v['ld']),
        'le':     r(v['le']),
        'ln':     r(v['ln']),
        'lden':   r(v['lden']),
    })


@api_bp.route('/indicadores')
def get_indicadores():
    """
    Indicadores de um intervalo (página Monitorização por Período), calculados no InfluxDB
    sobre as amostras raw: LAeq, LCpeak, LAFmax, LAFmin, LA10, LA50, LA95.
    """
    start  = request.args.get('start')
    end    = request.args.get('end')
    sensor = request.args.get('sensor_id')

    if not start or not end or not sensor:
        return jsonify({'error': "Parâmetros 'start', 'end' e 'sensor_id' são obrigatórios."}), 400
    if not sensor_valido(sensor):
        return jsonify({'error': 'Nome de sensor inválido.'}), 400
    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt   = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Formato de data inválido.'}), 400
    if end_dt <= start_dt:
        return jsonify({'error': 'A data de fim tem de ser posterior à de início.'}), 400

    try:
        v = fetch_indicadores_intervalo(sensor, local_to_rfc3339(start_dt), local_to_rfc3339(end_dt))
    except Exception as e:
        return jsonify({'error': f'Erro ao consultar o InfluxDB: {e}'}), 500

    return jsonify({k: (round(x, 2) if isinstance(x, float) else x) for k, x in v.items()})


@api_bp.route('/eventos')
def get_eventos():
    sensor    = request.args.get('sensor')
    start_raw = request.args.get('start')
    end_raw   = request.args.get('end')

    if not sensor:
        return jsonify({'erro': 'Sensor não especificado'}), 400
    if not start_raw or not end_raw:
        return jsonify({'erro': "Parâmetros 'start' e 'end' são obrigatórios"}), 400

    try:
        start_dt = datetime.strptime(start_raw, '%Y-%m-%dT%H:%M')
        end_dt   = datetime.strptime(end_raw,   '%Y-%m-%dT%H:%M')
        start    = start_dt.isoformat() + 'Z'
        end      = end_dt.isoformat()   + 'Z'
    except ValueError as e:
        return jsonify({'erro': f'Formato inválido de data. Use YYYY-MM-DDTHH:MM. Detalhes: {str(e)}'}), 400

    fields = ['EventDetect'] + [f'EventType{i}' for i in range(1, 11)]
    field_filter = ' or '.join([f'r["_field"] == "{f}"' for f in fields])

    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
        |> range(start: {start}, stop: {end})
        |> filter(fn: (r) => r["_measurement"] == "{sensor}" and ({field_filter}))
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> filter(fn: (r) => r["EventDetect"] > 0)
        |> sort(columns: ["_time"])
    '''

    try:
        client = InfluxDBClient(url=INFLUXDB_URL, timeout=35000, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        tables = client.query_api().query(query)
    except Exception as e:
        return jsonify({'erro': f'Erro ao consultar o InfluxDB: {str(e)}'}), 500

    dados = []
    for table in tables:
        for row in table.records:
            valores = row.values
            registro = {
                'time': row.get_time().isoformat(),
                'sensor': valores.get('sensor_id'),
                'EventDetect': valores.get('EventDetect'),
            }
            for i in range(1, 11):
                registro[f'EventType{i}'] = valores.get(f'EventType{i}', 0)
            dados.append(registro)
    return jsonify(dados)


@api_bp.route('/classes')
def get_classes():
    sensor = request.args.get('sensor_id')
    query = f"""
from(bucket: "SoundDashHosp")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "{sensor}")
  |> filter(fn: (r) =>
    r["_field"] == "Class1Score" or r["_field"] == "Class1ID" or
    r["_field"] == "Class2Score" or r["_field"] == "Class2ID" or
    r["_field"] == "Class3Score" or r["_field"] == "Class3ID"
  )
  |> last()
  |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
"""
    client = get_client()
    try:
        tables = client.query_api().query_data_frame(query)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if tables.empty:
        return jsonify([])

    id_to_name = current_app.id_to_name
    results = []
    for i in [1, 2, 3]:
        class_id = int(tables[f'Class{i}ID'][0])
        score    = float(tables[f'Class{i}Score'][0])
        results.append({
            'ClassID':    class_id,
            'ClassName':  id_to_name.get(class_id, 'Unknown'),
            'ClassScore': score
        })
    return jsonify(results)


@api_bp.route('/stats')
def get_stats():
    start       = request.args.get('start')
    end         = request.args.get('end')
    measurement = request.args.get('sensor_id')
    window      = request.args.get('window', '1m')

    if not start or not end or not measurement:
        return jsonify({'error': "Parâmetros 'start', 'end' e 'measurement' são obrigatórios."}), 400

    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt   = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Formato de data inválido.'}), 400

    duration_days = (end_dt - start_dt).total_seconds() / (3600 * 24)
    client    = get_client()
    query_api = client.query_api()
    limit     = 10000

    if pode_usar_bucket_agregado(duration_days, 'LAEA'):
        b_laea = 'SoundDashHosp_hourly'
        m_laea = f'{measurement}_hourly'
    else:
        b_laea = INFLUXDB_BUCKET
        m_laea = measurement

    queries = {
        'laea': f'''
            import "math"
            from(bucket: "{b_laea}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{m_laea}")
              |> filter(fn: (r) => r["_field"] == "LAEA"){flux_media_energetica(window)}
              |> limit(n: {limit})
        ''',
        'lcpeak': f'''
            from(bucket: "{INFLUXDB_BUCKET}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{measurement}")
              |> filter(fn: (r) => r["_field"] == "LCpeak")
              |> aggregateWindow(every: {window}, fn: max, createEmpty: false)
              |> limit(n: {limit})
        ''',
        'lafmax': f'''
            from(bucket: "{INFLUXDB_BUCKET}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{measurement}")
              |> filter(fn: (r) => r["_field"] == "LAFmax")
              |> aggregateWindow(every: {window}, fn: max, createEmpty: false)
              |> limit(n: {limit})
        ''',
        'lafmin': f'''
            from(bucket: "{INFLUXDB_BUCKET}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{measurement}")
              |> filter(fn: (r) => r["_field"] == "LAFmin")
              |> aggregateWindow(every: {window}, fn: min, createEmpty: false)
              |> limit(n: {limit})
        '''
    }

    def process_query(query):
        tables  = query_api.query(query, org=INFLUXDB_ORG)
        results = []
        for table in tables:
            for record in table.records:
                if record.get_value() is not None:
                    results.append({'time': record.get_time().isoformat(), 'value': record.get_value()})
        return results

    try:
        data = {key: process_query(q) for key, q in queries.items()}
        data['warning'] = f'Dados limitados a {limit} pontos por série devido ao volume'
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Erro ao processar dados: {str(e)}'}), 500
    finally:
        client.close()


@api_bp.route('/stats/stream')
def get_stats_stream():
    start       = request.args.get('start')
    end         = request.args.get('end')
    measurement = request.args.get('sensor_id')

    if not start or not end or not measurement:
        return jsonify({'error': 'Parâmetros obrigatórios em falta'}), 400

    def generate():
        client    = get_client()
        query_api = client.query_api()
        query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak")
          |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        yield '{"data": ['
        first = True
        try:
            tables = query_api.query(query, org=INFLUXDB_ORG)
            for table in tables:
                for record in table.records:
                    if not first:
                        yield ','
                    else:
                        first = False
                    yield json.dumps({
                        'time':   record.get_time().isoformat(),
                        'laea':   record.values.get('LAEA'),
                        'lcpeak': record.values.get('LCpeak')
                    })
        except Exception as e:
            if not first:
                yield ','
            yield json.dumps({'error': str(e)})
        finally:
            client.close()
        yield ']}'

    return Response(generate(), mimetype='application/json')


# Download CSV: enviado em streaming, em blocos, para não esgotar a memória do servidor
DOWNLOAD_MAX_HORAS = 72                      # intervalo máximo por download (≈1M linhas, limite do Excel)
DOWNLOAD_BLOCO     = timedelta(minutes=30)   # tamanho de cada consulta ao InfluxDB
DOWNLOAD_LINHAS_POR_ENVIO = 500              # linhas acumuladas antes de enviar ao browser


@api_bp.route('/download')
def download_csv():
    start       = request.args.get('start')
    end         = request.args.get('end')
    measurement = request.args.get('sensor_id')

    if not start or not end or not measurement:
        return jsonify({'error': "Parâmetros 'start', 'end' e 'sensor_id' são obrigatórios."}), 400

    if not sensor_valido(measurement):
        return jsonify({'error': 'Nome de sensor inválido.'}), 400

    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt   = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Formato de data inválido.'}), 400

    if end_dt <= start_dt:
        return jsonify({'error': 'A data de fim tem de ser posterior à de início.'}), 400
    if end_dt - start_dt > timedelta(hours=DOWNLOAD_MAX_HORAS):
        return jsonify({'error': f'O intervalo máximo para download é de {DOWNLOAD_MAX_HORAS} horas.'}), 400

    client    = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=120000)
    query_api = client.query_api()

    # Lista de campos do sensor no intervalo (para montar o cabeçalho antes de enviar dados)
    try:
        tabelas = query_api.query(f'''
        import "influxdata/influxdb/schema"
        schema.measurementFieldKeys(bucket: "{INFLUXDB_BUCKET}", measurement: "{measurement}",
                                    start: {local_to_rfc3339(start_dt)}, stop: {local_to_rfc3339(end_dt)})
        ''', org=INFLUXDB_ORG)
        fields = {rec.get_value() for t in tabelas for rec in t.records}
    except Exception as e:
        client.close()
        return jsonify({'error': f'Erro ao consultar o InfluxDB: {e}'}), 500

    # Colunas pela ordem do CSV gerado no sensor; campos desconhecidos vão no fim
    # (as bandas podem estar no InfluxDB como 00040_Hz — via Node-RED — ou como BT40 — via influx_import.py)
    known  = [c for c in CSV_COLUNAS_SENSOR if c not in ('TimeStamp', 'SensorID')]
    usados = set(known) | set(CSV_CAMPO_INFLUX.values()) | {'TimeStamp', 'SensorID'}
    extras = sorted(f for f in fields if f not in usados)

    def valor(row_data, coluna):
        v = row_data.get(CSV_CAMPO_INFLUX.get(coluna, coluna))
        if v is None:
            v = row_data.get(coluna)
        return '' if v is None else v

    # SensorID: tag do InfluxDB ou, em alternativa, o número no nome (Sensor5 -> 5.0)
    m = re.search(r'(\d+)$', measurement)
    sensor_id_default = float(m.group(1)) if m else measurement

    def fmt_sensor_id(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return sensor_id_default

    def linhas_csv(rows):
        buf = StringIO()
        csv.writer(buf).writerows(rows)
        return buf.getvalue()

    def generate():
        try:
            yield linhas_csv([CSV_COLUNAS_SENSOR + extras + ['DataHora_Lisboa']])
            bloco_ini = start_dt
            while bloco_ini < end_dt:
                bloco_fim = min(bloco_ini + DOWNLOAD_BLOCO, end_dt)
                # pivot: uma linha por instante com todos os campos (em vez de um registo por valor)
                query = f'''
                from(bucket: "{INFLUXDB_BUCKET}")
                  |> range(start: {local_to_rfc3339(bloco_ini)}, stop: {local_to_rfc3339(bloco_fim)})
                  |> filter(fn: (r) => r["_measurement"] == "{measurement}")
                  |> drop(columns: ["_start", "_stop"])
                  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
                  |> group()
                  |> sort(columns: ["_time"])
                '''
                rows = []
                for rec in query_api.query_stream(query, org=INFLUXDB_ORG):
                    v = rec.values
                    t = rec.get_time()
                    rows.append(
                        [f'{t.timestamp():.2f}', fmt_sensor_id(v.get('sensor_id'))]
                        + [valor(v, c) for c in known]
                        + [v.get(f, '') if v.get(f) is not None else '' for f in extras]
                        + [to_local(t).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]]
                    )
                    if len(rows) >= DOWNLOAD_LINHAS_POR_ENVIO:
                        yield linhas_csv(rows)
                        rows = []
                if rows:
                    yield linhas_csv(rows)
                bloco_ini = bloco_fim
        except Exception as e:
            # O cabeçalho HTTP já foi enviado: assinala o erro no próprio ficheiro
            yield f'# ERRO: download interrompido ({e})\n'
        finally:
            client.close()

    fmt_nome = lambda d: to_local(d).strftime('%Y%m%d_%H%M')
    filename = f'SoundData_{measurement}_{fmt_nome(start_dt)}_{fmt_nome(end_dt)}.csv'

    return Response(
        generate(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment;filename={filename}',
            'X-Download-Start': f'{start_dt.timestamp():.0f}',
            'X-Download-End':   f'{end_dt.timestamp():.0f}',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',   # Nginx: não acumular a resposta (permite progresso em tempo real)
        }
    )


@api_bp.route('/calendario')
def get_calendario():
    start_str = request.args.get('start')
    end_str   = request.args.get('end')
    sensor    = request.args.get('sensor_id')

    if not all([start_str, end_str, sensor]):
        return jsonify({'error': "Parâmetros obrigatórios: start, end, sensor_id"}), 400
    if not sensor_valido(sensor):
        return jsonify({'error': 'Nome de sensor inválido.'}), 400

    try:
        start_dt = datetime.fromisoformat(start_str[:10])
        end_dt   = datetime.fromisoformat(end_str[:10])
    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use YYYY-MM-DD'}), 400

    dias = [(start_dt + timedelta(days=i)).date() for i in range((end_dt - start_dt).days + 1)]

    # Hora local; vai até às 08:00 do dia seguinte ao último (T3 e Ln do último dia)
    horas = fetch_horas_agregadas(sensor, local_to_rfc3339(start_dt),
                                  local_to_rfc3339(end_dt + timedelta(days=1, hours=TURNO_INICIO_DIA)))
    ev_counts = fetch_event_intervals_by_hour(sensor, local_to_rfc3339(start_dt),
                                              local_to_rfc3339(end_dt + timedelta(days=1)))

    por_dia, total = calcular_indicadores_dias(horas, dias)

    def r(x): return round(x, 1) if x is not None else None

    result = []
    for d in dias:
        v = por_dia[d]
        day_str = d.strftime('%Y-%m-%d')
        item = {'date': day_str}
        item.update({k: r(v[k]) for k in INDICADORES_DIA})
        item['eventos']  = sum(ev_counts.get((day_str, h), 0) for h in range(24))
        item['has_data'] = any(item[k] is not None for k in INDICADORES_DIA)
        result.append(item)

    # Indicadores do conjunto do mês, calculados diretamente sobre todas as amostras
    mes = {k: r(total[k]) for k in INDICADORES_DIA}

    return jsonify({'dias': result, 'mes': mes})


@api_bp.route('/semanal')
def get_semanal():
    date_str = request.args.get('start')
    sensor   = request.args.get('sensor_id')

    if not all([date_str, sensor]):
        return jsonify({'error': "Parâmetros obrigatórios: start (YYYY-MM-DD), sensor_id"}), 400
    if not sensor_valido(sensor):
        return jsonify({'error': 'Nome de sensor inválido.'}), 400

    try:
        ref = datetime.fromisoformat(date_str[:10])
    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use YYYY-MM-DD'}), 400

    # Calculate Sunday–Saturday week
    week_start = ref - timedelta(days=(ref.weekday() + 1) % 7)
    week_end   = week_start + timedelta(days=6)

    # Hora local; vai até às 08:00 do domingo seguinte (T3 do sábado)
    stop_rfc = local_to_rfc3339(week_start + timedelta(days=7, hours=TURNO_INICIO_DIA))
    horas = fetch_horas_agregadas(sensor, local_to_rfc3339(week_start), stop_rfc)
    ev_counts = fetch_event_intervals_by_hour(sensor, local_to_rfc3339(week_start), stop_rfc)

    dias = [(week_start + timedelta(days=i)).date() for i in range(7)]
    days = [d.strftime('%Y-%m-%d') for d in dias]

    # Acumula por (dia de calendário, hora) e por (dia de turnos, turno).
    # As duas horas repetidas na mudança para a hora de inverno ficam juntas na mesma linha.
    def nova_entrada():
        return {'acc': AcumuladorEnergia(), 'lcpeak': None}

    por_hora  = defaultdict(nova_entrada)
    por_turno = defaultdict(nova_entrada)
    for t, h in horas.items():
        soma, n, pico = h.get('soma'), int(h.get('n', 0)), h.get('LCpeak')
        for destino, chave in ((por_hora,  (t.date(), t.hour)),
                               (por_turno, (dia_atribuido(t, TURNO_INICIO_DIA), turno_da_hora(t.hour)))):
            entrada = destino[chave]
            entrada['acc'].add(soma, n)
            if pico is not None:
                entrada['lcpeak'] = pico if entrada['lcpeak'] is None else max(entrada['lcpeak'], pico)

    def r(x): return round(x, 1) if x is not None else None

    def cell(entrada, events):
        if entrada is None:
            return {'laeq': None, 'lcpeak': None, 'events': events}
        return {'laeq': r(entrada['acc'].laeq()), 'lcpeak': r(entrada['lcpeak']), 'events': events}

    # Hourly rows (dia de calendário)
    horas_rows = []
    for hr in range(24):
        row = {'hour': hr, 'label': f'{hr:02d}:00', 'data': {}}
        for d, ds in zip(dias, days):
            row['data'][ds] = cell(por_hora.get((d, hr)), ev_counts.get((ds, hr), 0))
        horas_rows.append(row)

    # Shift rows (dia de turnos: 08:00 -> 08:00; o T3 é a madrugada seguinte)
    TURNOS = [
        ('t1', 'turno1', 'Turno 1 — 08:00–16:00h', [(0, h) for h in range(8, 16)]),
        ('t2', 'turno2', 'Turno 2 — 16:00–00:00h', [(0, h) for h in range(16, 24)]),
        ('t3', 'turno3', 'Turno 3 — 00:00–08:00h (madrugada seguinte)', [(1, h) for h in range(0, 8)]),
    ]
    turnos = []
    for tid, chave, label, horas_turno in TURNOS:
        row = {'id': tid, 'label': label, 'data': {}}
        for d, ds in zip(dias, days):
            ev_total = sum(ev_counts.get(((d + timedelta(days=off)).strftime('%Y-%m-%d'), h), 0)
                           for off, h in horas_turno)
            row['data'][ds] = cell(por_turno.get((d, chave)), ev_total)
        turnos.append(row)

    return jsonify({
        'week_start': week_start.strftime('%Y-%m-%d'),
        'week_end':   week_end.strftime('%Y-%m-%d'),
        'days':       days,
        'horas':      horas_rows,
        'turnos':     turnos
    })


@api_bp.route('/sensores')
def get_sensores():
    try:
        client = get_client()
        query = f'''
        import "influxdata/influxdb/schema"
        schema.measurements(bucket: "{INFLUXDB_BUCKET}")
        '''
        tables  = client.query_api().query(query, org=INFLUXDB_ORG)
        sensores = []
        for table in tables:
            for record in table.records:
                nome = record.get_value()
                if nome and (nome.startswith('sensor') or nome.startswith('Sensor')):
                    sensores.append(nome)
        return jsonify(sorted(set(sensores)))
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@api_bp.route('/reboot', methods=['POST'])
def reboot_sensor():
    data      = request.get_json()
    sensor_id = (data or {}).get('sensor_id')
    if not sensor_id:
        return jsonify({'success': False, 'erro': 'sensor_id obrigatório'}), 400
    ok, msg = current_app.config_mgr.reboot_sensor(sensor_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'erro': msg}), 500


@api_bp.route('/parametros/<sensor_id>', methods=['GET'])
def get_parametros(sensor_id):
    return current_app.config_mgr.get_config(sensor_id)


@api_bp.route('/parametros', methods=['POST'])
def update_parametros():
    return current_app.config_mgr.update_config()


@api_bp.route('/system_config', methods=['POST'])
@login_required
def update_system_config():
    try:
        data = request.get_json()
        grafana_url = data.get('grafana_url', '').strip()
        if not grafana_url:
            return jsonify({'erro': 'URL do Grafana não pode ser vazio'}), 400
        config = load_system_config()
        config['grafana_url'] = grafana_url
        save_system_config(config)
        return jsonify({'mensagem': 'Configuração guardada com sucesso!'})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@api_bp.route('/data')
def get_data():
    try:
        start     = request.args.get('start', '-5m')
        stop      = request.args.get('stop', 'now()')
        sensor_id = request.args.get('sensor_id')
        field     = request.args.get('field', 'LAEA')

        if not sensor_id:
            return jsonify({'error': 'Missing sensor_id parameter'}), 400

        duration_days = parse_interval_to_days(start)

        if pode_usar_bucket_agregado(duration_days, field):
            bucket_name = 'SoundDashHosp_hourly'
            measurement = f'sensor{sensor_id}_hourly'
            strategy    = f"pre-aggregated hourly (field '{field}' available)"
        else:
            bucket_name = INFLUXDB_BUCKET
            measurement = f'sensor{sensor_id}'
            strategy    = 'raw data (1s resolution)' if duration_days <= 7 else f"raw data (field '{field}' not aggregated)"

        query = f'''
        from(bucket: "{bucket_name}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["_field"] == "{field}")
        '''

        client = get_client()
        result = client.query_api().query(query, org=INFLUXDB_ORG)

        data = [
            {'time': record.get_time().isoformat(), 'value': round(record.get_value(), 2)}
            for table in result for record in table.records
        ]

        return jsonify({
            'success': True,
            'data': data,
            'meta': {
                'sensor_id':    sensor_id,
                'field':        field,
                'interval':     start,
                'duration_days': round(duration_days, 2),
                'bucket':       bucket_name,
                'measurement':  measurement,
                'points':       len(data),
                'strategy':     strategy
            }
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'client' in locals():
            client.close()
