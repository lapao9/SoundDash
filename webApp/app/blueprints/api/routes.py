from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required
from datetime import datetime, timedelta
from collections import defaultdict
from io import StringIO
import csv
import json
from tqdm import tqdm

from influxdb_client import InfluxDBClient
from app.config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET
from app.services.influx import (
    get_client, to_rfc3339, parse_interval_to_days, pode_usar_bucket_agregado
)
from app.services.acoustics import (
    calcular_media_db, calcular_lden_db, fetch_valores_db, fetch_laeq_horario,
    fetch_hourly_campos, fetch_event_intervals_by_hour
)
from app.services.system_config import load_system_config, save_system_config

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/lden')
def get_lden():
    start_str  = request.args.get('start')
    end_str    = request.args.get('end')
    sensor     = request.args.get('sensor_id')

    if not start_str or not end_str or not sensor:
        return jsonify({'error': "Parâmetros 'start', 'end' e 'sensor_id' são obrigatórios"}), 400

    try:
        start_dt = datetime.fromisoformat(start_str.replace('Z', ''))
        end_dt   = datetime.fromisoformat(end_str.replace('Z', ''))
    except Exception:
        return jsonify({'error': 'Formato de data inválido'}), 400

    d_start = start_dt.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    d7      = start_dt.replace(hour=7,  minute=0,  second=0,  microsecond=0)
    d8      = start_dt.replace(hour=8,  minute=0,  second=0,  microsecond=0)
    d16     = start_dt.replace(hour=16, minute=0,  second=0,  microsecond=0)
    d19     = start_dt.replace(hour=19, minute=0,  second=0,  microsecond=0)
    d23     = start_dt.replace(hour=23, minute=0,  second=0,  microsecond=0)
    d_end   = start_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Hospital shifts: T1=00-08h, T2=08-16h, T3=16-00h
    v_t1 = fetch_valores_db(sensor, 'LAEA', to_rfc3339(d_start), to_rfc3339(d8))
    v_t2 = fetch_valores_db(sensor, 'LAEA', to_rfc3339(d8),      to_rfc3339(d16))
    v_t3 = fetch_valores_db(sensor, 'LAEA', to_rfc3339(d16),     to_rfc3339(d_end))

    # Official Lden periods (EU 2002/49/EC): Ld=07-19h, Le=19-23h, Ln=23-07h
    v_ld = fetch_valores_db(sensor, 'LAEA', to_rfc3339(d7),      to_rfc3339(d19))
    v_le = fetch_valores_db(sensor, 'LAEA', to_rfc3339(d19),     to_rfc3339(d23))
    v_ln = fetch_valores_db(sensor, 'LAEA', to_rfc3339(d_start), to_rfc3339(d7)) + \
           fetch_valores_db(sensor, 'LAEA', to_rfc3339(d23),     to_rfc3339(d_end))

    Lturno1 = calcular_media_db(v_t1)
    Lturno2 = calcular_media_db(v_t2)
    Lturno3 = calcular_media_db(v_t3)
    Ld      = calcular_media_db(v_ld)
    Le      = calcular_media_db(v_le)
    Ln      = calcular_media_db(v_ln)

    if None in (Ld, Le, Ln):
        return jsonify({'error': 'Sem dados suficientes'}), 404

    Lden = calcular_lden_db(Ld, Le, Ln)

    def r(v): return round(v, 2) if v is not None else None

    return jsonify({
        'turno1': r(Lturno1),
        'turno2': r(Lturno2),
        'turno3': r(Lturno3),
        'ld':     r(Ld),
        'le':     r(Le),
        'ln':     r(Ln),
        'lden':   r(Lden),
        # aliases kept for backwards compat with any existing callers
        'laeq_day':     r(Ld),
        'laeq_evening': r(Le),
        'laeq_night':   r(Ln),
    })


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
            from(bucket: "{b_laea}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{m_laea}")
              |> filter(fn: (r) => r["_field"] == "LAEA")
              |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
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


@api_bp.route('/download')
def download_csv():
    start       = request.args.get('start')
    end         = request.args.get('end')
    measurement = request.args.get('sensor_id')

    if not start or not end or not measurement:
        return jsonify({'error': "Parâmetros 'start', 'end' e 'measurement' são obrigatórios."}), 400

    try:
        datetime.fromisoformat(start.replace('Z', '+00:00'))
        datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Formato de data inválido.'}), 400

    client    = get_client()
    query_api = client.query_api()
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
    '''
    tables = query_api.query(query, org=INFLUXDB_ORG)

    data_by_time = defaultdict(dict)
    fields = set()
    for table in tables:
        for record in table.records:
            timestamp = record.get_time().isoformat()
            field     = record.get_field()
            value     = record.get_value()
            data_by_time[timestamp][field] = value
            fields.add(field)

    fields = list(fields)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['timestamp'] + fields)
    for timestamp in tqdm(sorted(data_by_time.keys()), desc='A Processar: '):
        writer.writerow([timestamp] + [data_by_time[timestamp].get(f, '') for f in fields])

    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=SoundData_{start}_{end}.csv'}
    )


@api_bp.route('/calendario')
def get_calendario():
    start_str = request.args.get('start')
    end_str   = request.args.get('end')
    sensor    = request.args.get('sensor_id')

    if not all([start_str, end_str, sensor]):
        return jsonify({'error': "Parâmetros obrigatórios: start, end, sensor_id"}), 400

    try:
        start_dt = datetime.fromisoformat(start_str)
        end_dt   = datetime.fromisoformat(end_str).replace(hour=23, minute=59, second=59)
    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use YYYY-MM-DD'}), 400

    raw = fetch_hourly_campos(sensor, to_rfc3339(start_dt), to_rfc3339(end_dt),
                              ['LAEA', 'LCpeak', 'LAFmax', 'LAFmin'])

    by_day = defaultdict(lambda: defaultdict(list))
    for item in raw:
        t = item['time']
        by_day[t.strftime('%Y-%m-%d')][item['field']].append({'hour': t.hour, 'value': item['value']})

    result = []
    current = start_dt.date()
    end_date = end_dt.date()

    while current <= end_date:
        day_str    = current.strftime('%Y-%m-%d')
        fields_day = by_day.get(day_str, {})
        laea_hours = fields_day.get('LAEA', [])

        if laea_hours:
            all_vals = [h['value'] for h in laea_hours]
            # Hospital shifts (T1/T2/T3)
            t1_vals  = [h['value'] for h in laea_hours if h['hour'] < 8]
            t2_vals  = [h['value'] for h in laea_hours if 8  <= h['hour'] < 16]
            t3_vals  = [h['value'] for h in laea_hours if 16 <= h['hour'] < 24]
            # Official Lden periods: Ld=07-19h, Le=19-23h, Ln=23-07h
            ld_vals  = [h['value'] for h in laea_hours if 7  <= h['hour'] < 19]
            le_vals  = [h['value'] for h in laea_hours if 19 <= h['hour'] < 23]
            ln_vals  = [h['value'] for h in laea_hours if h['hour'] >= 23 or h['hour'] < 7]

            laeq   = calcular_media_db(all_vals)
            turno1 = calcular_media_db(t1_vals)
            turno2 = calcular_media_db(t2_vals)
            turno3 = calcular_media_db(t3_vals)
            ld     = calcular_media_db(ld_vals)
            le     = calcular_media_db(le_vals)
            ln     = calcular_media_db(ln_vals)
            lden   = calcular_lden_db(ld, le, ln)

            lcpeak_vals = [h['value'] for h in fields_day.get('LCpeak', [])]
            lafmax_vals = [h['value'] for h in fields_day.get('LAFmax', [])]
            lafmin_vals = [h['value'] for h in fields_day.get('LAFmin', [])]

            lcpeak = max(lcpeak_vals) if lcpeak_vals else None
            lmax   = max(lafmax_vals) if lafmax_vals else None
            lmin   = min(lafmin_vals) if lafmin_vals else None

            result.append({
                'date':   day_str,
                'laeq':   round(laeq,   1) if laeq   is not None else None,
                'turno1': round(turno1, 1) if turno1 is not None else None,
                'turno2': round(turno2, 1) if turno2 is not None else None,
                'turno3': round(turno3, 1) if turno3 is not None else None,
                'ld':     round(ld,     1) if ld     is not None else None,
                'le':     round(le,     1) if le     is not None else None,
                'ln':     round(ln,     1) if ln     is not None else None,
                'lden':   round(lden,   1) if lden   is not None else None,
                'lcpeak': round(lcpeak, 1) if lcpeak is not None else None,
                'lmax':   round(lmax,   1) if lmax   is not None else None,
                'lmin':   round(lmin,   1) if lmin   is not None else None,
                'has_data': True
            })
        else:
            result.append({'date': day_str, 'laeq': None, 'turno1': None, 'turno2': None,
                           'turno3': None, 'ld': None, 'le': None, 'ln': None,
                           'lden': None, 'lcpeak': None, 'lmax': None,
                           'lmin': None, 'has_data': False})
        current += timedelta(days=1)

    return jsonify({'dias': result})


@api_bp.route('/semanal')
def get_semanal():
    date_str = request.args.get('start')
    sensor   = request.args.get('sensor_id')

    if not all([date_str, sensor]):
        return jsonify({'error': "Parâmetros obrigatórios: start (YYYY-MM-DD), sensor_id"}), 400

    try:
        ref = datetime.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use YYYY-MM-DD'}), 400

    # Calculate Sunday–Saturday week
    week_start = ref - timedelta(days=ref.weekday() + 1) if ref.weekday() != 6 else ref
    if ref.weekday() == 6:
        week_start = ref
    else:
        week_start = ref - timedelta(days=(ref.weekday() + 1) % 7)
    week_end = week_start + timedelta(days=6)

    start_rfc = to_rfc3339(week_start.replace(hour=0,  minute=0,  second=0))
    end_rfc   = to_rfc3339(week_end.replace(  hour=23, minute=59, second=59))

    raw      = fetch_hourly_campos(sensor, start_rfc, end_rfc, ['LAEA', 'LCpeak'])
    ev_counts = fetch_event_intervals_by_hour(sensor, start_rfc, end_rfc)

    # Index by (day_str, hour, field)
    idx = defaultdict(lambda: defaultdict(dict))
    for item in raw:
        t       = item['time']
        day_str = t.strftime('%Y-%m-%d')
        idx[day_str][t.hour][item['field']] = item['value']

    days = [(week_start + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

    def cell(day, hour_vals, events=None):
        laea   = hour_vals.get('LAEA')
        lcpeak = hour_vals.get('LCpeak')
        return {
            'laeq':   round(laea,   1) if laea   is not None else None,
            'lcpeak': round(lcpeak, 1) if lcpeak is not None else None,
            'events': events if events else 0
        }

    # Hourly rows
    horas = []
    for h in range(24):
        row = {'hour': h, 'label': f'{h:02d}:00', 'data': {}}
        for d in days:
            hv = idx[d].get(h, {})
            row['data'][d] = cell(d, hv, ev_counts.get((d, h), 0))
        horas.append(row)

    # Shift rows — aggregate hours per shift
    TURNOS = [
        ('t1', 'Turno 1 — 00:00–08:00h', range(0,  8)),
        ('t2', 'Turno 2 — 08:00–16:00h', range(8,  16)),
        ('t3', 'Turno 3 — 16:00–00:00h', range(16, 24)),
    ]
    turnos = []
    for tid, label, hours in TURNOS:
        row = {'id': tid, 'label': label, 'data': {}}
        for d in days:
            laea_vals   = [idx[d][h]['LAEA']   for h in hours if 'LAEA'   in idx[d].get(h, {})]
            lcpeak_vals = [idx[d][h]['LCpeak'] for h in hours if 'LCpeak' in idx[d].get(h, {})]
            ev_total    = sum(ev_counts.get((d, h), 0) for h in hours)
            laeq   = calcular_media_db(laea_vals)
            lcpeak = calcular_media_db(lcpeak_vals)
            row['data'][d] = {
                'laeq':   round(laeq,   1) if laeq   is not None else None,
                'lcpeak': round(lcpeak, 1) if lcpeak is not None else None,
                'events': ev_total
            }
        turnos.append(row)

    return jsonify({
        'week_start': week_start.strftime('%Y-%m-%d'),
        'week_end':   week_end.strftime('%Y-%m-%d'),
        'days':       days,
        'horas':      horas,
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
@login_required
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
