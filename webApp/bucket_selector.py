# bucket_selector.py
"""
Módulo para escolher bucket apropriado baseado no intervalo de tempo
Usar com InfluxDB para otimizar queries

Integração no webAppGrafana.py:
    from bucket_selector import get_appropriate_bucket, parse_duration_to_seconds
"""

def parse_duration_to_seconds(duration_str):
    """
    Converte string de duração para segundos
    
    Args:
        duration_str: String no formato '-Xu' onde X é número e u é unidade
                     Exemplos: '-5m', '-1h', '-7d', '-30d'
    
    Returns:
        int: Duração em segundos
    
    Examples:
        >>> parse_duration_to_seconds('-5m')
        300
        >>> parse_duration_to_seconds('-1h')
        3600
        >>> parse_duration_to_seconds('-7d')
        604800
    """
    if not duration_str or not duration_str.startswith('-'):
        return 300  # default: 5 minutos
    
    try:
        # Extrair valor numérico e unidade
        value = int(duration_str[1:-1])
        unit = duration_str[-1]
        
        # Converter para segundos
        conversions = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400,
            'w': 604800
        }
        
        return value * conversions.get(unit, 60)  # default: minutos
        
    except (ValueError, IndexError):
        return 300  # default: 5 minutos


def get_appropriate_bucket(start_str, stop_str=None):
    """
    Escolhe bucket e agregação apropriados baseado no intervalo de tempo
    
    Estratégia:
    - Intervalo < 1h:    Bucket principal, dados raw (1s)
    - Intervalo 1h-24h:  Bucket principal, agregação 1min
    - Intervalo 24h-7d:  Bucket principal, agregação 10min
    - Intervalo > 7d:    Bucket agregado (dados já em 1h)
    
    Args:
        start_str: String de início no formato '-Xu' (ex: '-5m', '-24h')
        stop_str: String de fim (opcional, default: 'now()')
    
    Returns:
        dict: {
            'bucket': nome do bucket a usar,
            'measurement': measurement a filtrar,
            'use_aggregation': agregação extra ou None,
            'description': descrição da estratégia
        }
    
    Examples:
        >>> get_appropriate_bucket('-5m')
        {
            'bucket': 'SoundDashHosp',
            'measurement': 'sound_levels',
            'use_aggregation': None,
            'description': 'Raw data (1 point/second)'
        }
        
        >>> get_appropriate_bucket('-30d')
        {
            'bucket': 'SoundDashHosp_hourly',
            'measurement': 'sound_levels_hourly',
            'use_aggregation': None,
            'description': 'Pre-aggregated hourly data'
        }
    """
    duration_seconds = parse_duration_to_seconds(start_str)
    
    # Decisão baseada no intervalo
    if duration_seconds > 604800:  # > 7 dias
        return {
            'bucket': 'SoundDashHosp_hourly',
            'measurement': 'sound_levels_hourly',
            'use_aggregation': None,
            'description': 'Pre-aggregated hourly data'
        }
    
    elif duration_seconds > 86400:  # 24h - 7 dias
        return {
            'bucket': 'SoundDashHosp',
            'measurement': 'sound_levels',
            'use_aggregation': '10m',
            'description': 'Raw data aggregated to 10min windows'
        }
    
    elif duration_seconds > 3600:  # 1h - 24h
        return {
            'bucket': 'SoundDashHosp',
            'measurement': 'sound_levels',
            'use_aggregation': '1m',
            'description': 'Raw data aggregated to 1min windows'
        }
    
    else:  # < 1h
        return {
            'bucket': 'SoundDashHosp',
            'measurement': 'sound_levels',
            'use_aggregation': None,
            'description': 'Raw data (1 point/second)'
        }


def build_influx_query(start, stop, sensor_id, field, bucket_config):
    """
    Constrói query Flux otimizada baseado na configuração do bucket
    
    Args:
        start: String de início (ex: '-5m')
        stop: String de fim (ex: 'now()')
        sensor_id: ID do sensor (ex: '2')
        field: Campo a filtrar (ex: 'LAeq')
        bucket_config: Dict retornado por get_appropriate_bucket()
    
    Returns:
        str: Query Flux pronta para executar
    
    Example:
        >>> config = get_appropriate_bucket('-5m')
        >>> query = build_influx_query('-5m', 'now()', '2', 'LAeq', config)
        >>> print(query)
        from(bucket: "SoundDashHosp")
          |> range(start: -5m, stop: now())
          |> filter(fn: (r) => r["_measurement"] == "sound_levels")
          |> filter(fn: (r) => r["sensor_id"] == "2")
          |> filter(fn: (r) => r["_field"] == "LAeq")
    """
    # Query base
    query = f'''
from(bucket: "{bucket_config['bucket']}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r["_measurement"] == "{bucket_config['measurement']}")
  |> filter(fn: (r) => r["sensor_id"] == "{sensor_id}")
  |> filter(fn: (r) => r["_field"] == "{field}")
    '''.strip()
    
    # Adicionar agregação se necessário
    if bucket_config.get('use_aggregation'):
        query += f'''
  |> aggregateWindow(every: {bucket_config['use_aggregation']}, fn: mean, createEmpty: false)
        '''.strip()
    
    return query


# ===== INTEGRAÇÃO NO FLASK =====

def flask_integration_example():
    """
    Exemplo de como integrar no webAppGrafana.py
    """
    example_code = '''
# No webAppGrafana.py

from bucket_selector import get_appropriate_bucket, build_influx_query

@app.route('/api/data')
def get_data():
    try:
        # Parâmetros
        start = request.args.get('start', '-5m')
        stop = request.args.get('stop', 'now()')
        sensor_id = request.args.get('sensor_id')
        field = request.args.get('field', 'LAeq')
        
        # Validar
        if not sensor_id:
            return jsonify({'error': 'Missing sensor_id'}), 400
        
        # Escolher bucket apropriado
        bucket_config = get_appropriate_bucket(start, stop)
        
        # Log da estratégia
        print(f"[Query] start={start}, sensor={sensor_id}, field={field}")
        print(f"[Query] Strategy: {bucket_config['description']}")
        print(f"[Query] Bucket: {bucket_config['bucket']}")
        
        # Construir query
        query = build_influx_query(start, stop, sensor_id, field, bucket_config)
        
        # Executar
        result = query_api.query(query)
        
        # Processar resultado
        data = process_influx_result(result)
        
        return jsonify({
            'success': True,
            'data': data,
            'meta': {
                'bucket': bucket_config['bucket'],
                'points': len(data),
                'aggregation': bucket_config.get('use_aggregation', 'raw'),
                'strategy': bucket_config['description']
            }
        })
        
    except Exception as e:
        print(f"[ERROR] /api/data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    '''
    
    return example_code


# ===== HELPER PARA PROCESSAR RESULTADO INFLUX =====

def process_influx_result(result):
    """
    Processa resultado da query InfluxDB para formato JSON
    
    Args:
        result: Resultado do query_api.query()
    
    Returns:
        list: [{time: str, value: float}, ...]
    
    Example:
        >>> result = query_api.query(query)
        >>> data = process_influx_result(result)
        >>> print(data[0])
        {'time': '2024-05-08T00:30:00Z', 'value': 65.4}
    """
    data = []
    
    for table in result:
        for record in table.records:
            data.append({
                'time': record.get_time().isoformat(),
                'value': record.get_value(),
                'sensor_id': record.values.get('sensor_id'),
                'field': record.get_field()
            })
    
    return data


# ===== TESTES =====

if __name__ == '__main__':
    """
    Testes das funções
    """
    print("=== TESTES ===\n")
    
    # Teste 1: Parse durations
    print("Teste 1: Parse Durations")
    durations = ['-5m', '-1h', '-24h', '-7d', '-30d', '-365d']
    for d in durations:
        seconds = parse_duration_to_seconds(d)
        hours = seconds / 3600
        print(f"  {d:6s} → {seconds:7d}s ({hours:.1f}h)")
    
    print("\nTeste 2: Bucket Selection")
    for d in durations:
        config = get_appropriate_bucket(d)
        print(f"  {d:6s} → {config['bucket']:25s} | {config['description']}")
    
    print("\nTeste 3: Query Building")
    config = get_appropriate_bucket('-24h')
    query = build_influx_query('-24h', 'now()', '2', 'LAeq', config)
    print(query)
    
    print("\n=== FIM DOS TESTES ===")
