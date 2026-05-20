from flask import Flask, request, jsonify, render_template, Response, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from influxdb_client import InfluxDBClient
from datetime import datetime, timezone
from collections import defaultdict
from io import StringIO
import csv
import threading
import json
from werkzeug.security import check_password_hash
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
from time import perf_counter
import pandas as pd
import math
from tqdm import tqdm

import requests


mensagem_recebida = None
mensagem_evento = threading.Event()

app = Flask(__name__, template_folder='templates')
app.secret_key = 'uma_chave_muito_secreta'  # muda para algo mais seguro


MQTT_BROKER = '10.64.137.6'
MQTT_PORT = 1881
# Configurações do InfluxDB
url = "http://10.64.137.6:8086"
token = "LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA=="
org = "ISEL"
bucket = "SoundDashHosp"

# Configuração do sistema (Grafana URL, etc.) - Adicionado 18 Abril 26
SYSTEM_CONFIG_FILE = "system_config.json"

def load_system_config():
    try:
        with open(SYSTEM_CONFIG_FILE) as f:
            return json.load(f)
    except:
        return {"grafana_url": "http://10.64.137.6:3000"}

def save_system_config(config):
    with open(SYSTEM_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

# ======================================================
# FUNÇÕES PARA CÁLCULOS ACÚSTICOS CORRETOS (em linear)
# ======================================================
"""
Os valores dos sensores estão em dB (escala logarítmica).
Nunca se pode fazer médias, percentis ou qualquer cálculo estatístico
diretamente em dB, é matematicamente errado.
A conversão correta para pressão sonora é:
  dB → linear:  10^(val/10)     ← expoente 10, não 20
  linear → dB:  10 * log10(val)
O expoente 20 seria correto apenas para amplitude elétrica/tensão.
"""

def db_to_linear(db_value: float) -> float:
    """Converte dB para escala linear de pressão sonora."""
    return 10 ** (db_value / 10.0)

def linear_to_db(linear_value: float) -> float:
    """Converte escala linear de pressão sonora para dB."""
    if linear_value <= 0:
        return None
    return 10 * math.log10(linear_value)

def calcular_media_db(valores_db: list) -> float:
    """
    Calcula a média correta de valores em dB.
    ERRADO:  mean([40, 50, 60]) = 50 dB  ← média aritmética direta
    CORRETO: converter para linear → média → voltar a dB
    """
    if not valores_db:
        return None
    lineares = [db_to_linear(v) for v in valores_db if v is not None]
    if not lineares:
        return None
    return linear_to_db(sum(lineares) / len(lineares))

def calcular_percentil_db(valores_db: list, percentil: float) -> float:
    """
    Calcula percentil correto de valores em dB.
    Ex: percentil=0.95 → P95
    Converte para linear, ordena, calcula percentil, volta a dB.
    """
    if not valores_db:
        return None
    lineares = sorted([db_to_linear(v) for v in valores_db if v is not None])
    if not lineares:
        return None
    idx = int(len(lineares) * percentil)
    idx = min(idx, len(lineares) - 1)
    return linear_to_db(lineares[idx])

def calcular_lden_db(Lday: float, Levening: float, Lnight: float) -> float:
    """
    Calcula o Lden corretamente em dB.
    Fórmula oficial europeia:
      Lden = 10 * log10(
        (12 * 10^(Lday/10) + 4 * 10^((Levening+5)/10) + 8 * 10^((Lnight+10)/10)) / 24
      )
    """
    if None in (Lday, Levening, Lnight):
        return None
    num = (
        12 * db_to_linear(Lday) +
         4 * db_to_linear(Levening + 5) +
         8 * db_to_linear(Lnight + 10)
    )
    return linear_to_db(num / 24)

def fetch_valores_db(sensor: str, campo: str, start: str, stop: str) -> list:
    """
    Vai buscar todos os valores de um campo ao InfluxDB e devolve lista em dB.
    Usado pelas funções de cálculo acima.
    """
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: {start}, stop: {stop})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "{campo}")
    '''
    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        tables = client.query_api().query(query, org=org)
        valores = []
        for table in tables:
            for record in table.records:
                v = record.get_value()
                if v is not None:
                    valores.append(float(v))
        return valores
    except Exception as e:
        print(f"Erro ao buscar valores: {e}")
        return []
    finally:
        client.close()

# FIM DE --> FUNÇÕES PARA CÁLCULOS ACÚSTICOS CORRETOS (em linear)
# ======================================================


# ======================================================
# FUNÇÕES PARA ESCOLHA AUTOMÁTICA DE BUCKET
# ======================================================

def parse_interval_to_days(interval_str):
    """
    Converte string de intervalo para dias
    Exemplos: -5m → 0.003, -1h → 0.04, -24h → 1, -7d → 7
    """
    if not interval_str or not interval_str.startswith('-'):
        return 0
    
    try:
        value = int(interval_str[1:-1])
        unit = interval_str[-1]
        
        if unit == 'm':  # minutos
            return value / (60 * 24)
        elif unit == 'h':  # horas
            return value / 24
        elif unit == 'd':  # dias
            return value
        elif unit == 'w':  # semanas
            return value * 7
        else:
            return 0
    except (ValueError, IndexError):
        return 0


# FIM DE --> FUNÇÕES PARA ESCOLHA AUTOMÁTICA DE BUCKET
# ======================================================


# --- Flask-Login setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # rota para login se não autenticado

def load_users():
    with open('users.json') as f:
        return json.load(f)

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        return User(user_id)
    return None

# --- Rotas Auth ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        if username in users and check_password_hash(users[username]['password'], password):
            user = User(username)
            login_user(user, remember=remember)
            flash('Login efetuado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('controlo'))
        else:
            flash('Credenciais inválidas.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sessão terminada.', 'info')
    return redirect(url_for('homepage'))

# --- Rota protegida para o painel técnico ---
@app.route('/controlo')
@login_required
def controlo():
    config = load_system_config()
    return render_template('controlo.html', 
                         username=current_user.id,
                         grafana_url=config.get("grafana_url", ""))
#def controlo():
    #return render_template('controlo.html', username=current_user.id)


# --- Funções auxiliares de query -------------------------
def to_rfc3339(dt: datetime) -> str: #rfc3339 ex: "2024-06-01T12:00:00Z"
    """Converte datetime para string RFC3339"""
    return dt.isoformat("T") + "Z"

def fetch_avg(client, start: datetime, stop: datetime, sensor, window):
    """Procura valores de LAEA e calcula a média em dB corretamente (linear → média → dB)"""
    print(f'''start: {to_rfc3339(start)}, stop: {to_rfc3339(stop)}''')
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: {to_rfc3339(start)}, stop: {to_rfc3339(stop)})
      |> filter(fn: (r) => r["_measurement"] == "{sensor}")
      |> filter(fn: (r) => r["_field"] == "LAEA")
      |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
    '''
    #deleted -->        |> filter(fn: (r) => r["_measurement"] == "{Sensor}")
    tables = client.query_api().query(query, org=org)

    values = []
    for table in tables:
        for record in table.records:
            val = record.get_value()
            if val is not None:
                # converter dB → linear
                #values.append( 10 ** (float(val) / 20))
                values.append(db_to_linear(float(val)))

    if not values:
        return None

    # média linear → voltar a dB
    #mean_linear = sum(values) / len(values)
    #return 20 * math.log10(mean_linear)
    return linear_to_db(sum(values) / len(values))

# --- API para cálculo do Lden (usando as funções corretas de conversão linear) ---
@app.route("/api/lden")
def getLden():
    start_str = request.args.get("start")
    end_str = request.args.get("end")
    sensor = request.args.get("sensor_id")

    if not start_str or not end_str or not sensor:
        return jsonify({"error": "Parâmetros 'start', 'end' e 'sensor_id' são obrigatórios"}), 400

    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", ""))
        end_dt = datetime.fromisoformat(end_str.replace("Z", ""))
    except Exception:
        return jsonify({"error": "Formato de data inválido"}), 400

    # Períodos Lden — norma europeia
    # Dia     08h–20h (12 horas, sem penalização)
    # Tarde   20h–23h (4 horas, +5 dB)
    # Noite   00h–08h + 23h–24h (8 horas, +10 dB)
    d0  = start_dt.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    d8  = start_dt.replace(hour=8,  minute=0,  second=0,  microsecond=0)
    d20 = start_dt.replace(hour=20, minute=0,  second=0,  microsecond=0)
    d23 = start_dt.replace(hour=23, minute=0,  second=0,  microsecond=0)
    d24 = start_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    with InfluxDBClient(url=url, token=token, org=org) as client:
        # procura valores raw e calcula média em linear
        valores_dia     = fetch_valores_db(sensor, "LAEA", to_rfc3339(d8),  to_rfc3339(d20))
        valores_tarde   = fetch_valores_db(sensor, "LAEA", to_rfc3339(d20), to_rfc3339(d23))
        valores_noite1  = fetch_valores_db(sensor, "LAEA", to_rfc3339(d0),  to_rfc3339(d8))
        valores_noite2  = fetch_valores_db(sensor, "LAEA", to_rfc3339(d23), to_rfc3339(d24))

    Lday     = calcular_media_db(valores_dia)
    Levening  = calcular_media_db(valores_tarde)
    # Noite = dois segmentos combinados
    Lnight   = calcular_media_db(valores_noite1 + valores_noite2)

    if None in (Lday, Levening, Lnight):
        return jsonify({"error": "Sem dados suficientes"}), 404

    Lden = calcular_lden_db(Lday, Levening, Lnight)

    return jsonify({
        "laeq_night":   round(Lnight, 2),
        "laeq_day":     round(Lday, 2),
        "laeq_evening": round(Levening, 2),
        "lden":         round(Lden, 2)
    })
"""
def getLden():
    
    start_str = request.args.get("start")
    end_str = request.args.get("end")
    sensor = request.args.get("sensor_id")
    window = request.args.get("window", "1m")

    if not start_str or not end_str or not sensor:
        return jsonify({"error": "Parâmetros 'start', 'end' e 'sensor_id' são obrigatórios"}), 400

    try:
        # Remover o "Z" do final se existir (para usar fromisoformat)
        start_dt = datetime.fromisoformat(start_str.replace("Z", ""))
        end_dt = datetime.fromisoformat(end_str.replace("Z", ""))
    except Exception:
        return jsonify({"error": "Formato de data inválido"}), 400

    # Quebrar o período do start em blocos
    d0 = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    d7 = start_dt.replace(hour=7, minute=59, second=59, microsecond=999999)
    d8 = start_dt.replace(hour=8, minute=0, second=0, microsecond=0)
    d15 = start_dt.replace(hour=15, minute=59, second=59, microsecond=999999)
    d16 = start_dt.replace(hour=16, minute=0, second=0, microsecond=0)
    d23 = start_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    with InfluxDBClient(url=url, token=token, org=org) as client:
        Lnight = fetch_avg(client, d0, d7, sensor, window)      # 00h–08h
        Lday = fetch_avg(client, d8, d15, sensor, window)       # 08h–16h
        Levening = fetch_avg(client, d16, d23, sensor, window)  # 16h–24h

    if None in (Lnight, Lday, Levening):
        return jsonify({"error": "Sem dados suficientes"}), 404

    # cálculo do Lden
    #num = (
    #    8 * (10 ** (Lday / 10))
    #    + 8 * (10 ** ((Levening) / 10))
    #    + 8 * (10 ** ((Lnight) / 10))
    #)
    #Lden = 10 * math.log10(num / 24)

    Lden = calcular_lden_db(Lday, Levening, Lnight)

    dados = {
        "laeq_night": Lnight,
        "laeq_day": Lday,
        "laeq_evening": Levening,
        "lden": Lden
    }


    print(dados)
    return jsonify(dados)
"""

# --- API para obter eventos detectados (EventDetect > 0) e seus tipos ---
@app.route("/api/eventos")
def obter_dados_brutos():
    sensor = request.args.get("sensor")
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")
    
    if not sensor:
        return jsonify({"erro": "Sensor não especificado"}), 400
    if not start_raw or not end_raw:
        return jsonify({"erro": "Parâmetros 'start' e 'end' são obrigatórios"}), 400

    # Converter para formato RFC3339 aceito pelo InfluxDB
    try:
        start_dt = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M")
        end_dt = datetime.strptime(end_raw, "%Y-%m-%dT%H:%M")
        start = start_dt.isoformat() + "Z"
        end = end_dt.isoformat() + "Z"
    except ValueError as e:
        return jsonify({"erro": f"Formato inválido de data. Use YYYY-MM-DDTHH:MM. Detalhes: {str(e)}"}), 400

    # ===== ESCOLHA AUTOMÁTICA DE BUCKET =====
    # Calcular duração em dias
    duration = end_dt - start_dt
    duration_days = duration.total_seconds() / (24 * 3600)
    
    # Escolher bucket e measurement
    if duration_days > 7:
        bucket_name = "SoundDashHosp_hourly"
        measurement = f"{sensor}_hourly"
        print(f"[/api/eventos] Query {duration_days:.1f} dias → bucket agregado")
    else:
        bucket_name = bucket  # SoundDashHosp
        measurement = sensor
        print(f"[/api/eventos] Query {duration_days:.1f} dias → bucket raw")

    # Campos a procurar:
    """CORRIGIDO: range(1, 11) em vez de range(0, 10)
    Os campos reais são EventType1 a EventType10, não EventType0 a EventType9"""
    fields = ['EventDetect'] + [f'EventType{i}' for i in range(1, 11)]
    field_filter = " or ".join([f'r["_field"] == "{f}"' for f in fields])

    query = f'''
    from(bucket: "{bucket_name}")
        |> range(start: {start}, stop: {end})
        |> filter(fn: (r) => r["_measurement"] == "{measurement}" and ({field_filter}))
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> filter(fn: (r) => r["EventDetect"] > 0)
        |> sort(columns: ["_time"])
    '''

    try:
        client = InfluxDBClient(url=url, timeout=35000, token=token, org=org)
        query_api = client.query_api()
        tables = query_api.query(query)
    except Exception as e:
        print(e)
        return jsonify({"erro": f"Erro ao consultar o InfluxDB: {str(e)}"}), 500

    dados = []
    for table in tables:
        for row in table.records:
            valores = row.values
            registro = {
                "time": row.get_time().isoformat(),
                "sensor": valores.get("sensor_id"),
                "EventDetect": valores.get("EventDetect"),
            }
            for i in range(1, 11):
                registro[f"EventType{i}"] = valores.get(f"EventType{i}", 0)
            dados.append(registro)
    #elapsed = perf_counter() - start_perf
    #print(elapsed)        
    return jsonify(dados)

#--- API para obter as classes mais recentes (Class1ID, Class1Score, etc.) e seus nomes legíveis
#//////////////////////////////////////////////#
# Carregar o CSV e criar mapping ID → Nome
labels_df = pd.read_csv("class_labels_indices.csv")
id_to_name = dict(zip(labels_df["index"], labels_df["display_name"]))

@app.route("/api/classes")
def get_classes():
    sensor = request.args.get("sensor_id")
    query = f"""
from(bucket: "SoundDashHosp")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "{sensor}")
  |> filter(fn: (r) =>  r["_field"] == "Class1Score" or
    r["_field"] == "Class1ID" or
    r["_field"] == "Class2Score" or
    r["_field"] == "Class2ID" or
    r["_field"] == "Class3Score" or
    r["_field"] == "Class3ID"
  )
  |> last()
  |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
"""
# eliminei ->> r["_measurement"] == "sensor1") , estava hardcoded - joão

    #print(query)
    client = InfluxDBClient(url=url, token=token, org=org)
    try:
        tables = client.query_api().query_data_frame(query)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if tables.empty:
        return jsonify([])

    results = []
    for i in [1, 2, 3]:
        class_id = int(tables[f"Class{i}ID"][0])
        score = float(tables[f"Class{i}Score"][0])
        results.append({
            "ClassID": class_id,
            "ClassName": id_to_name.get(class_id, "Unknown"),
            "ClassScore": score
        })

    return jsonify(results)

# --- API para obter dados brutos (LAEA, LCpeak, LAFmax, LAFmin) para um período e sensor específicos ---
@app.route("/api/stats")
def get_raw_data():
    start = request.args.get("start")
    end = request.args.get("end")
    measurement = request.args.get("sensor_id")
    window = request.args.get("window", "1m")  # Agregação opcional

    if not start or not end or not measurement:
        return jsonify({"error": "Parâmetros 'start', 'end' e 'measurement' são obrigatórios."}), 400

    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Formato de data inválido."}), 400

    # ===== ESCOLHA AUTOMÁTICA DE BUCKET =====
    # Calcular duração em dias
    duration = end_dt - start_dt
    duration_days = duration.total_seconds() / (24 * 3600)
    
    # Escolher bucket e measurement
    if duration_days > 7:
        bucket_name = "SoundDashHosp_hourly"
        measurement_name = f"{measurement}_hourly"
        print(f"[/api/stats] Query {duration_days:.1f} dias → bucket agregado")
    else:
        bucket_name = bucket  # SoundDashHosp
        measurement_name = measurement
        print(f"[/api/stats] Query {duration_days:.1f} dias → bucket raw")

    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()
    limit = 10000

    queries = {
        "laea": f'''
            from(bucket: "{bucket_name}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
              |> filter(fn: (r) => r["_field"] == "LAEA")
              |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
              |> limit(n: {limit})
        ''',
        "lcpeak": f'''
            from(bucket: "{bucket_name}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
              |> filter(fn: (r) => r["_field"] == "LCpeak")
              |> aggregateWindow(every: {window}, fn: max, createEmpty: false)
              |> limit(n: {limit})
        ''',
        "lafmax": f'''
            from(bucket: "{bucket_name}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
              |> filter(fn: (r) => r["_field"] == "LAFmax")
              |> aggregateWindow(every: {window}, fn: max, createEmpty: false)
              |> limit(n: {limit})
        ''',
        "lafmin": f'''
            from(bucket: "{bucket_name}")
              |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
              |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
              |> filter(fn: (r) => r["_field"] == "LAFmin")
              |> aggregateWindow(every: {window}, fn: min, createEmpty: false)
              |> limit(n: {limit})
        '''
    }

    def process_query(query, batch_size=1000):
        tables = query_api.query(query, org=org)
        results = []
        batch = []
        for table in tables:
            for record in table.records:
                if record.get_value() is not None:
                    batch.append({
                        "time": record.get_time().isoformat(),
                        "value": record.get_value()
                    })
                    if len(batch) >= batch_size:
                        results.extend(batch)
                        batch = []
        if batch:
            results.extend(batch)
        return results

    try:
        data = {key: process_query(q) for key, q in queries.items()}
        data["warning"] = f"Dados limitados a {limit} pontos por série devido ao volume"
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Erro ao processar dados: {str(e)}"}), 500
    finally:
        client.close()

# --- API para obter dados brutos com streaming (para evitar sobrecarga de memória em volumes muito grandes) ---
# Versão alternativa com streaming para volumes muito grandes
@app.route("/api/stats/stream")
def get_raw_data_stream():
    start = request.args.get("start")
    end = request.args.get("end")
    measurement = request.args.get("sensor_id")
    
    if not start or not end or not measurement:
        return jsonify({"error": "Parâmetros obrigatórios em falta"}), 400
    
    def generate():
        client = InfluxDBClient(url=url, token=token, org=org)
        query_api = client.query_api()
        
        query = f'''
        from(bucket: "{bucket}")
          |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["_field"] == "LAEA" or r["_field"] == "LCpeak")
          |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        yield '{"data": ['
        first = True
        
        try:
            tables = query_api.query(query, org=org)
            for table in tables:
                for record in table.records:
                    if not first:
                        yield ','
                    else:
                        first = False
                    
                    data_point = {
                        "time": record.get_time().isoformat(),
                        "laea": record.values.get("LAEA"),
                        "lcpeak": record.values.get("LCpeak")
                    }
                    yield json.dumps(data_point)
        except Exception as e:
            if not first:
                yield ','
            yield json.dumps({"error": str(e)})
        finally:
            client.close()
        
        yield ']}'
    
    return Response(generate(), mimetype='application/json')

@app.route("/api/download")
def download_csv():
    start = request.args.get("start")
    end = request.args.get("end")
    measurement = request.args.get("sensor_id")
    if not start or not end or not measurement:
        return jsonify({"error": "Parâmetros 'start' , 'end' e 'measurement' são obrigatórios."}), 400
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Formato de data inválido."}), 400

    # ===== ESCOLHA AUTOMÁTICA DE BUCKET =====
    # Calcular duração em dias
    duration = end_dt - start_dt
    duration_days = duration.total_seconds() / (24 * 3600)
    
    # Escolher bucket e measurement
    if duration_days > 7:
        bucket_name = "SoundDashHosp_hourly"
        measurement_name = f"{measurement}_hourly"
        print(f"[/api/download] Query {duration_days:.1f} dias → bucket agregado")
    else:
        bucket_name = bucket  # SoundDashHosp
        measurement_name = measurement
        print(f"[/api/download] Query {duration_days:.1f} dias → bucket raw")

    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    query = f'''
    from(bucket: "{bucket_name}")
      |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
      |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
    '''
    tables = query_api.query(query, org=org)

    data_by_time = defaultdict(dict)
    fields = set()

    for table in tables:
        for record in table.records:
            timestamp = record.get_time().isoformat()
            field = record.get_field()
            value = record.get_value()
            data_by_time[timestamp][field] = value
            fields.add(field)

    fields = list(fields)
    print("A iniciar formaçao de CSV...\n")
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp"] + fields)

    # for i, timestamp in enumerate(sorted(data_by_time.keys()), 1):
    #     row = [timestamp] + [data_by_time[timestamp].get(f, "") for f in fields]
    #     writer.writerow(row)
    #     print(f"\rProcessando {i}/{len(data_by_time)}...", end="", flush=True)

    for timestamp in tqdm(sorted(data_by_time.keys()), desc="A Processar: "):
        row = [timestamp] + [data_by_time[timestamp].get(f, "") for f in fields]
        writer.writerow(row)

    print("\nConcluído!")

    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=SoundData_{start}_{end}.csv"}
    )
    
    
@app.route('/api/parametros', methods=['POST'])
def receber_parametros():
    try:
        req = request.get_json()
        sensor = req.get("sensor")
        config = req.get("config")

        if not sensor or not config:
            return jsonify({'erro': 'Parâmetros ausentes'}), 400

        topic = f"{sensor}/update"
        payload = json.dumps(config)
        print(f'Mensagem publicada em: {topic}\n')
        print(f'{payload}\n')
        publish.single(
            topic=topic,
            payload=payload,
            hostname=MQTT_BROKER,
            port=MQTT_PORT
        )

        return jsonify({'mensagem': f'Parâmetros enviados para {topic}'}), 200

    except Exception as e:
        print(f"[ERRO] {e}")
        return jsonify({'erro': 'Erro interno ao processar os dados'}), 500

#ADICIONADA PARA NÃO TER QUE ABRIR OUTROS PORTOS PARA O GRAFANA, POR EXEMPLO PARA O IFRAME DO ATUAL.HTML
@app.route('/grafana/<path:path>', methods=["GET", "POST", "PUT", "DELETE"])
def grafana_proxy(path):
    url = f"http://localhost:3000/{path}"

    headers = dict(request.headers)
    headers["Host"] = "localhost:3000"

    resp = requests.request(
        method=request.method,
        url=url,
        headers=headers,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False
    )

    excluded = ["content-encoding", "content-length", "transfer-encoding", "connection"]

    response_headers = [
        (k, v) for k, v in resp.headers.items()
        if k.lower() not in excluded
    ]

    return Response(resp.content, resp.status_code, response_headers)


@app.route('/')
def home():
    config = load_system_config()
    return render_template('homepage.html', grafana_url=config.get("grafana_url", ""))

@app.route('/atual')
def atual():
    config = load_system_config()
    return render_template('atual.html', grafana_url=config.get("grafana_url", ""))

@app.route('/tempo')
def tempo():
    config = load_system_config()
    return render_template('tempo.html', grafana_url=config.get("grafana_url", ""))

@app.route('/mapa')
def mapa():
    config = load_system_config()
    return render_template('mapa.html', grafana_url=config.get("grafana_url", ""))

@app.route('/display')
def display():
    config = load_system_config()
    return render_template('display.html', grafana_url=config.get("grafana_url", ""))

@app.route('/eventos')
def eventos():
    config = load_system_config()
    return render_template('eventos.html', grafana_url=config.get("grafana_url", ""))

@app.route('/guia')
def guia():
    config = load_system_config()
    return render_template('guia.html', grafana_url=config.get("grafana_url", ""))

# --- API: guardar configuração do sistema (URL do Grafana) ---------------
"""Adicionado por João para permitir atualizar a URL do Grafana sem ter que editar o código"""
@app.route('/api/system_config', methods=['POST'])
@login_required
def update_system_config():
    try:
        data = request.get_json()
        grafana_url = data.get("grafana_url", "").strip()
        if not grafana_url:
            return jsonify({"erro": "URL do Grafana não pode ser vazio"}), 400
        config = load_system_config()
        config["grafana_url"] = grafana_url
        save_system_config(config)
        return jsonify({"mensagem": "Configuração guardada com sucesso!"})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
        
# --- API: listar sensores disponíveis no bucket ---------------
"""Adicionado por João para listar os sensores disponíveis no bucket, para popular os dropdowns dinamicamente"""
@app.route('/api/sensores')
def get_sensores():
    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        query = f'''
        import "influxdata/influxdb/schema"
        schema.measurements(bucket: "{bucket}")
        '''
        tables = client.query_api().query(query, org=org)
        sensores = []
        for table in tables:
            for record in table.records:
                nome = record.get_value()
                if nome and (nome.startswith("sensor") or nome.startswith("Sensor")):

                    sensores.append(nome)
        sensores = sorted(set(sensores))
        return jsonify(sensores)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500






# ======================================================
# API: Dados de Sensores com Escolha Automática de Bucket
# ======================================================
"""
Rota inteligente que escolhe automaticamente entre bucket raw ou agregado
baseado no intervalo de tempo solicitado.

Estratégia:
- Intervalos ≤ 7 dias: usa SoundDashHosp (dados raw)
- Intervalos > 7 dias: usa SoundDashHosp_hourly (dados pré-agregados)
"""

@app.route('/api/data')
def get_data():
    """
    Endpoint para obter dados de sensores
    Escolhe automaticamente bucket apropriado baseado no intervalo temporal
    
    Query params:
        start (str): Intervalo inicial (ex: -5m, -1h, -24h, -30d)
        stop (str): Intervalo final (default: now())
        sensor_id (str): ID do sensor (ex: "2" para sensor2)
        field (str): Campo a filtrar (default: "LAEA")
    
    Returns:
        JSON: {
            success: bool,
            data: [{time: str, value: float}, ...],
            meta: {bucket, measurement, points, strategy, ...}
        }
    """
    try:
        # Parâmetros
        start = request.args.get('start', '-5m')
        stop = request.args.get('stop', 'now()')
        sensor_id = request.args.get('sensor_id')
        field = request.args.get('field', 'LAEA')
        
        # Validação
        if not sensor_id:
            return jsonify({'error': 'Missing sensor_id parameter'}), 400
        
        # Calcular duração em dias
        duration_days = parse_interval_to_days(start)
        
        # Escolher bucket e measurement baseado no intervalo
        if duration_days > 7:  # Threshold: 7 dias
            bucket_name = "SoundDashHosp_hourly"
            measurement = f"sensor{sensor_id}_hourly"
            strategy = "pre-aggregated hourly (dB avg correct)"
        else:
            bucket_name = "SoundDashHosp"
            measurement = f"sensor{sensor_id}"
            strategy = "raw data (1s resolution)"
        
        # Log da estratégia
        print(f"[Query] sensor={sensor_id}, field={field}, interval={start} ({duration_days:.2f} days)")
        print(f"[Query] Strategy: {strategy}")
        print(f"[Query] Using: {bucket_name}/{measurement}")
        
        # Construir query Flux
        query = f'''
        from(bucket: "{bucket_name}")
          |> range(start: {start}, stop: {stop})
          |> filter(fn: (r) => r["_measurement"] == "{measurement}")
          |> filter(fn: (r) => r["_field"] == "{field}")
        '''
        
        # Executar query
        print(f"[Query] Executing query...")
        client = InfluxDBClient(url=url, token=token, org=org)
        result = client.query_api().query(query, org=org)
        
        # Processar resultado
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    'time': record.get_time().isoformat(),
                    'value': round(record.get_value(), 2)  # Arredondar para 2 decimais
                })
        
        print(f"[Query] Returned {len(data)} points")
        
        # Resposta
        return jsonify({
            'success': True,
            'data': data,
            'meta': {
                'sensor_id': sensor_id,
                'field': field,
                'interval': start,
                'duration_days': round(duration_days, 2),
                'bucket': bucket_name,
                'measurement': measurement,
                'points': len(data),
                'strategy': strategy
            }
        })
        
    except Exception as e:
        print(f"[ERROR] /api/data failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        if 'client' in locals():
            client.close()


if __name__ == '__main__':
    # app.run(debug=True, host='0.0.0.0', port=80)
    app.run(host="0.0.0.0", port=5000, debug=True)

