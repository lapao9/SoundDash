import math
from datetime import datetime, timedelta, timezone
import pandas as pd
from influxdb_client import InfluxDBClient
from app.config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET, INFLUXDB_BUCKET_1H
from app.services.influx import to_local


def db_to_linear(db_value: float) -> float:
    return 10 ** (db_value / 10.0)


def linear_to_db(linear_value: float) -> float:
    if linear_value <= 0:
        return None
    return 10 * math.log10(linear_value)


def calcular_lden_db(Lday: float, Levening: float, Lnight: float) -> float:
    """
    Lden (Regulamento Geral do Ruído, DL 9/2007):
    Ld = 07-20h (13 h), Le = 20-23h (3 h, +5 dB), Ln = 23-07h (8 h, +10 dB).
    """
    if None in (Lday, Levening, Lnight):
        return None
    num = (
        13 * db_to_linear(Lday) +
        3  * db_to_linear(Levening + 5) +
        8  * db_to_linear(Lnight + 10)
    )
    return linear_to_db(num / 24)


# ── Turnos e períodos (hora local de Lisboa) ──────────────────────────────────
# Turnos hospitalares: o "dia de turnos" começa às 08:00. O T3 (00-08h) pertence
# ao dia anterior.  T1 = 08-16h, T2 = 16-24h, T3 = 00-08h (do dia seguinte).
TURNO_INICIO_DIA = 8
# Períodos do Lden: o ciclo começa às 07:00 (Ln = 23-07h fica no mesmo ciclo).
LDEN_INICIO_DIA = 7


def turno_da_hora(hora: int) -> str:
    if 8 <= hora < 16:
        return 'turno1'
    if hora >= 16:
        return 'turno2'
    return 'turno3'


def periodo_da_hora(hora: int) -> str:
    if 7 <= hora < 20:
        return 'ld'
    if 20 <= hora < 23:
        return 'le'
    return 'ln'


def dia_atribuido(t, inicio: int):
    """Data a que pertence o instante t (hora local) num ciclo diário que começa às `inicio` horas."""
    d = t.date()
    return d - timedelta(days=1) if t.hour < inicio else d


class AcumuladorEnergia:
    """
    Junta somas horárias de 10^(L/10) e contagens. O LAeq resultante é idêntico à
    média energética calculada diretamente sobre todas as amostras.
    """
    __slots__ = ('soma', 'n')

    def __init__(self):
        self.soma = 0.0
        self.n = 0

    def add(self, soma, n):
        if soma is not None and n:
            self.soma += soma
            self.n += n

    def laeq(self):
        return linear_to_db(self.soma / self.n) if self.n else None


def _max(a, b):
    return b if a is None else (a if b is None else max(a, b))


def _min(a, b):
    return b if a is None else (a if b is None else min(a, b))


def flux_media_energetica(every: str, time_src: str = '_stop') -> str:
    """
    Pipeline Flux para média energética numa janela (a query tem de fazer import "math").
    dB -> linear com o operador ^ e não com math.pow: o Flux calcula o ^ em bloco (~90x mais rápido
    sobre milhões de amostras); o log10 final só corre sobre os pontos já agregados.
    """
    return f'''
      |> map(fn: (r) => ({{r with _value: 10.0 ^ (float(v: r._value) / 10.0)}}))
      |> aggregateWindow(every: {every}, fn: mean, createEmpty: false, timeSrc: "{time_src}")
      |> map(fn: (r) => ({{r with _value: 10.0 * math.log10(x: r._value)}}))'''


def fetch_event_intervals_by_hour(sensor: str, start: str, stop: str) -> dict:
    """
    Replicates the grouping logic from eventos.js:
    consecutive EventDetect>0 records with gap <=5s = one event.
    Returns {(day_str, hour): count} of distinct event intervals per local hour.
    """
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "EventDetect")
      |> filter(fn: (r) => r["_value"] > 0)
      |> sort(columns: ["_time"])
    '''
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=60000)
    try:
        tables = client.query_api().query(query, org=INFLUXDB_ORG)
        times = sorted(
            record.get_time()
            for table in tables
            for record in table.records
            if record.get_time() is not None
        )

        if not times:
            return {}

        # Group by 5-second gap — same rule as eventos.js
        interval_starts = [times[0]]
        for i in range(1, len(times)):
            if (times[i] - times[i - 1]).total_seconds() > 5:
                interval_starts.append(times[i])

        # Count intervals per (day_str, hour) in local time, using interval start time
        counts = {}
        for t in interval_starts:
            t = to_local(t)
            key = (t.strftime('%Y-%m-%d'), t.hour)
            counts[key] = counts.get(key, 0) + 1

        return counts
    except Exception as e:
        print(f"Erro ao buscar event intervals: {e}")
        return {}
    finally:
        client.close()


def _juntar_hora(horas: dict, t, soma=None, n=None, lcpeak=None, lafmax=None, lafmin=None):
    h = horas.setdefault(to_local(t), {})
    if soma is not None and n:
        h['soma'] = h.get('soma', 0.0) + float(soma)
        h['n']    = h.get('n', 0.0) + float(n)
    if lcpeak is not None:
        h['LCpeak'] = _max(h.get('LCpeak'), float(lcpeak))
    if lafmax is not None:
        h['LAFmax'] = _max(h.get('LAFmax'), float(lafmax))
    if lafmin is not None:
        h['LAFmin'] = _min(h.get('LAFmin'), float(lafmin))


def _horas_do_bucket(query_api, sensor: str, start: str, stop: str, horas: dict):
    """Horas já agregadas pela task (bucket 1h): LAEA = média linear, n = nº de amostras -> soma = LAEA·n."""
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET_1H}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "n" or r["_field"] == "LCpeak"
                           or r["_field"] == "LAFmax" or r["_field"] == "LAFmin")
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    for table in query_api.query(query, org=INFLUXDB_ORG):
        for rec in table.records:
            v = rec.values
            laea, n = v.get('LAEA'), v.get('n')
            _juntar_hora(horas, rec.get_time(),
                         soma=laea * n if laea is not None and n else None, n=n,
                         lcpeak=v.get('LCpeak'), lafmax=v.get('LAFmax'), lafmin=v.get('LAFmin'))


def _horas_do_raw(query_api, sensor: str, start: str, stop: str, horas: dict):
    """Horas ainda não agregadas (a mais recente): calculadas sobre as amostras raw."""
    # Cada ramo com o seu filtro completo e escrito por extenso (ver fetch_indicadores_intervalo):
    # passar o filtro como função também impede o InfluxDB de o aplicar na leitura.
    rng = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: {start}, stop: {stop})'
    m = f'r["_measurement"] == "{sensor}"'
    query = f'''
    lin = {rng}
      |> filter(fn: (r) => {m} and r["_field"] == "LAEA")
      |> map(fn: (r) => ({{r with _value: 10.0 ^ (float(v: r._value) / 10.0)}}))
    soma = lin
      |> aggregateWindow(every: 1h, fn: sum, createEmpty: false, timeSrc: "_start")
      |> map(fn: (r) => ({{r with _field: "soma"}}))
    n = {rng}
      |> filter(fn: (r) => {m} and r["_field"] == "LAEA")
      |> aggregateWindow(every: 1h, fn: count, createEmpty: false, timeSrc: "_start")
      |> map(fn: (r) => ({{r with _field: "n", _value: float(v: r._value)}}))
    mx = {rng}
      |> filter(fn: (r) => {m} and (r["_field"] == "LCpeak" or r["_field"] == "LAFmax"))
      |> aggregateWindow(every: 1h, fn: max, createEmpty: false, timeSrc: "_start")
      |> map(fn: (r) => ({{r with _value: float(v: r._value)}}))
    mn = {rng}
      |> filter(fn: (r) => {m} and r["_field"] == "LAFmin")
      |> aggregateWindow(every: 1h, fn: min, createEmpty: false, timeSrc: "_start")
      |> map(fn: (r) => ({{r with _value: float(v: r._value)}}))
    union(tables: [soma, n, mx, mn])
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    for table in query_api.query(query, org=INFLUXDB_ORG):
        for rec in table.records:
            v = rec.values
            _juntar_hora(horas, rec.get_time(), soma=v.get('soma'), n=v.get('n'),
                         lcpeak=v.get('LCpeak'), lafmax=v.get('LAFmax'), lafmin=v.get('LAFmin'))


def _fim_horas_agregadas() -> datetime:
    """Início da hora mais recente que a task horária pode ainda não ter processado (corre às HH:02)."""
    agora = datetime.now(timezone.utc) - timedelta(minutes=15)
    return agora.replace(minute=0, second=0, microsecond=0)


def fetch_horas_agregadas(sensor: str, start: str, stop: str) -> dict:
    """
    Agregação horária exata:
      soma = Σ 10^(LAEA/10) e n = nº de amostras LAEA (permitem LAeq exato de qualquer conjunto de horas),
      LCpeak/LAFmax = máximo, LAFmin = mínimo.
    As horas já processadas pela task vêm do bucket 1h (rápido); só a hora mais recente é
    calculada sobre o raw. `start`/`stop` em RFC3339 UTC.
    Devolve {datetime local (início da hora): {'soma', 'n', 'LCpeak', 'LAFmax', 'LAFmin'}}.
    """
    ini = datetime.fromisoformat(start.replace('Z', '+00:00'))
    fim = datetime.fromisoformat(stop.replace('Z', '+00:00'))
    corte = max(ini, min(fim, _fim_horas_agregadas()))
    fmt = lambda d: d.strftime('%Y-%m-%dT%H:%M:%SZ')

    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=120000)
    try:
        query_api = client.query_api()
        horas = {}
        if corte > ini:
            _horas_do_bucket(query_api, sensor, fmt(ini), fmt(corte), horas)
        if fim > corte:
            _horas_do_raw(query_api, sensor, fmt(corte), fmt(fim), horas)
        return horas
    except Exception as e:
        print(f"Erro ao buscar agregação horária: {e}")
        return {}
    finally:
        client.close()


INDICADORES_DIA = ('laeq', 'lcpeak', 'lmax', 'lmin',
                   'turno1', 'turno2', 'turno3', 'ld', 'le', 'ln', 'lden')


def _novo_acumulado():
    return {
        'laeq': AcumuladorEnergia(), 'lcpeak': None, 'lmax': None, 'lmin': None,
        'turno1': AcumuladorEnergia(), 'turno2': AcumuladorEnergia(), 'turno3': AcumuladorEnergia(),
        'ld': AcumuladorEnergia(), 'le': AcumuladorEnergia(), 'ln': AcumuladorEnergia(),
    }


def _fechar(acc):
    r = {k: (v.laeq() if isinstance(v, AcumuladorEnergia) else v) for k, v in acc.items()}
    r['lden'] = calcular_lden_db(r['ld'], r['le'], r['ln'])
    return r


def calcular_indicadores_dias(horas: dict, dias: list):
    """
    Indicadores por dia e do conjunto dos dias, a partir de fetch_horas_agregadas().
    Cada indicador usa o seu "dia":
      laeq, lcpeak, lmax, lmin  -> dia de calendário (00:00 -> 24:00)
      turno1, turno2, turno3    -> dia de turnos (08:00 -> 08:00 do dia seguinte)
      ld, le, ln, lden          -> ciclo do Lden  (07:00 -> 07:00 do dia seguinte)
    Para cobrir o último dia, `horas` tem de ir até às 08:00 do dia seguinte.
    Devolve ({date: {indicador: valor}}, {indicador: valor do conjunto}).
    """
    por_dia = {d: _novo_acumulado() for d in dias}
    total = _novo_acumulado()

    for t, h in horas.items():
        soma, n = h.get('soma'), int(h.get('n', 0))

        d = t.date()
        if d in por_dia:
            for acc in (por_dia[d], total):
                acc['laeq'].add(soma, n)
                acc['lcpeak'] = _max(acc['lcpeak'], h.get('LCpeak'))
                acc['lmax']   = _max(acc['lmax'],   h.get('LAFmax'))
                acc['lmin']   = _min(acc['lmin'],   h.get('LAFmin'))

        d = dia_atribuido(t, TURNO_INICIO_DIA)
        if d in por_dia:
            turno = turno_da_hora(t.hour)
            por_dia[d][turno].add(soma, n)
            total[turno].add(soma, n)

        d = dia_atribuido(t, LDEN_INICIO_DIA)
        if d in por_dia:
            periodo = periodo_da_hora(t.hour)
            por_dia[d][periodo].add(soma, n)
            total[periodo].add(soma, n)

    return {d: _fechar(acc) for d, acc in por_dia.items()}, _fechar(total)


def fetch_indicadores_intervalo(sensor: str, start: str, stop: str, percentis_exatos: bool = True) -> dict:
    """
    Indicadores de um intervalo qualquer, calculados no InfluxDB sobre as amostras raw:
    LAeq (média energética), LCpeak/LAFmax (máximo), LAFmin (mínimo),
    LA10/LA50/LA95 (percentis 90/50/5 das amostras LAEA).
    Percentis exatos obrigam o InfluxDB a ordenar todas as amostras; para intervalos longos
    usa-se a estimativa t-digest (erro tipicamente < 0,1 dB) para não sobrecarregar o servidor.
    """
    metodo = "exact_mean" if percentis_exatos else "estimate_tdigest"
    # Cada ramo tem o seu from/range/filter completo: com uma variável "base" partilhada,
    # o InfluxDB lia todos os campos do sensor em cada ramo (~100x mais lento).
    query = f'''
    campo = (f) => from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}" and r["_field"] == f)
      |> group()
    k = (tables=<-, nome) => tables |> map(fn: (r) => ({{k: nome, _value: float(v: r._value)}}))
    union(tables: [
      campo(f: "LAEA") |> map(fn: (r) => ({{r with _value: 10.0 ^ (float(v: r._value) / 10.0)}})) |> sum() |> k(nome: "soma"),
      campo(f: "LAEA") |> count() |> k(nome: "n"),
      campo(f: "LAEA") |> quantile(q: 0.9, method: "{metodo}") |> k(nome: "la10"),
      campo(f: "LAEA") |> quantile(q: 0.5, method: "{metodo}") |> k(nome: "la50"),
      campo(f: "LAEA") |> quantile(q: 0.05, method: "{metodo}") |> k(nome: "la95"),
      campo(f: "LCpeak") |> max() |> k(nome: "lcpeak"),
      campo(f: "LAFmax") |> max() |> k(nome: "lafmax"),
      campo(f: "LAFmin") |> min() |> k(nome: "lafmin"),
    ])
    '''
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=120000)
    try:
        valores = {}
        for table in client.query_api().query(query, org=INFLUXDB_ORG):
            for record in table.records:
                if record.get_value() is not None:
                    valores[record.values.get('k')] = float(record.get_value())
        n = valores.pop('n', 0)
        soma = valores.pop('soma', None)
        valores['laeq'] = linear_to_db(soma / n) if n and soma else None
        valores['n_amostras'] = int(n)
        return valores
    finally:
        client.close()


def load_class_labels(filepath: str) -> dict:
    df = pd.read_csv(filepath)
    return dict(zip(df["index"], df["display_name"]))
