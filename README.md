# SoundDash

Sistema de monitorização acústica em tempo real para ambientes hospitalares.
Desenvolvido no âmbito de projeto no ISEL --> captura, processa e visualiza níveis sonoros de múltiplos sensores distribuídos, com classificação automática de eventos de áudio e cálculo de indicadores acústicos normalizados (LAeq, LAFmax, Lden).

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│  SENSORES  (Raspberry Pi)                                           │
│  sensor_side.py ──── MQTT sound/levels ────────────────────────┐   │
│                 ◄─── MQTT sound/config/request/{id} ───────┐   │   │
│                 ───► MQTT sound/config/response/{id} ──┐   │   │   │
└────────────────────────────────────────────────────────│───│───│───┘
                                                         │   │   │
┌─────────────────────────────────────┐                  │   │   │
│  MOSQUITTO  :1881 / :1884           │◄─────────────────┘   │   │
└────────────────────┬────────────────┘                      │   │
                     │ sound/levels                           │   │
┌────────────────────▼────────────────┐                      │   │
│  NODE-RED  :1880                    │                      │   │
│  MQTT In ──► InfluxDB Out           │                      │   │
└────────────────────┬────────────────┘                      │   │
                     │ Line Protocol                          │   │
┌────────────────────▼────────────────┐                      │   │
│  INFLUXDB  :8086                    │                      │   │
│  bucket: SoundDashHosp  (raw)       │                      │   │
│  bucket: SoundDashHosp_hourly       │                      │   │
└──────────┬──────────────────────────┘                      │   │
           │ Flux queries                                     │   │
┌──────────▼──────────────────────────┐                      │   │
│  FLASK  :5000                       │──── ConfigManager ───┘   │
│  app/blueprints/                    │     MQTT :1884            │
│    api/      → /api/*               │◄──────────────────────────┘
│    pages/    → páginas web          │
│    auth/     → login/logout         │
│    proxy/    → /grafana/*           │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│  NGINX  :80                         │
│  / → Flask :5000                    │
│  /grafana → Grafana :3000           │
└─────────────────────────────────────┘

                    ┌────────────────────┐
                    │  GRAFANA  :3000    │
                    │  Dashboards embed. │
                    │  via iframes Flask │
                    └────────────────────┘
```

---

## Estrutura do Repositório

```
SoundDash/
│
├── webApp/                        # Aplicação Flask
│   ├── run.py                     # Entry point  →  python run.py
│   ├── app/
│   │   ├── __init__.py            # App factory create_app()
│   │   ├── config.py              # Constantes (URLs, tokens, paths)
│   │   ├── blueprints/
│   │   │   ├── api/routes.py      # GET/POST /api/*
│   │   │   ├── auth/routes.py     # /acesso-tecnico, /app-logout
│   │   │   ├── pages/routes.py    # Páginas web
│   │   │   └── proxy/routes.py    # /grafana/<path> (proxy reverso)
│   │   ├── services/
│   │   │   ├── acoustics.py       # Cálculos dB ↔ linear, Lden
│   │   │   ├── auth_service.py    # Flask-Login, users.json
│   │   │   ├── config_manager.py  # Configuração remota via MQTT
│   │   │   ├── influx.py          # Cliente InfluxDB, dual-bucket
│   │   │   └── system_config.py   # system_config.json (URL Grafana)
│   │   ├── templates/             # Jinja2 (extends base.html)
│   │   └── static/
│   │       ├── css/               # base.css + CSS por página
│   │       ├── js/                # utils.js, grafana-iframes.js + JS por página
│   │       └── images/
│   ├── tests/                     # Scripts de benchmark InfluxDB
│   ├── users.json                 # Credenciais (hash bcrypt)
│   ├── system_config.json         # URL do Grafana (editável em /controlo)
│   └── class_labels_indices.csv   # 521 classes YAMNet
│
├── sensor/                        # Código para Raspberry Pi
│   ├── sensor_side.py             # Listener MQTT + config receiver
│   ├── CSVtoJSON_MQTT.py          # Simular dados via CSV
│   └── config.json                # Configuração local do sensor
│
├── Influx_Scripts/                # Scripts de gestão InfluxDB
│   ├── influx_import.py           # CSV → InfluxDB (batch de 500 pontos)
│   ├── influx_importDIR.py        # Import de diretório completo
│   ├── task_downsampling.flux     # Tarefa horária: raw → 1min médias
│   ├── task_lden_diario.flux      # Tarefa diária: cálculo Lden
│   └── task_stats_horarias.flux   # Tarefa horária: LAeq, LAFmax, P95
│
├── grafana/                       # Exports de dashboards Grafana (.json)
├── nodered/                       # Export dos flows Node-RED (flows.json)
├── data/                          # Dados de amostra / simulados
├── auth/                          # hashGenerator.py (gerar hashes para users.json)
├── archive/                       # Scripts obsoletos
├── GUIAS/                         # Documentação e guias
│   ├── nssmConfiguration.txt      # Comandos NSSM (instalar serviços Windows)
│   └── GUIA_INTEGRACAO_CONFIG_REMOTA.md
│
├── docker-compose.yml             # Stack alternativa (Mosquitto, Node-RED, InfluxDB, Grafana)
├── start-all.bat                  # Iniciar todos os serviços NSSM
├── stop-all.bat                   # Parar todos os serviços
└── status.bat                     # Estado de todos os serviços
```

---

## Pré-requisitos

| Componente | Versão testada | Notas                                                            |
| ---------- | --------------- | ---------------------------------------------------------------- |
| Python     | 3.11+           | `pip install flask flask-login influxdb-client paho-mqtt tqdm` |
| InfluxDB   | 2.7             | Org:`ISEL`, bucket: `SoundDashHosp`                          |
| Mosquitto  | 2.x             | Portas 1881 (dados) e 1884 (config remota)                       |
| Node-RED   | 3.x             | Flow MQTT In → InfluxDB Out                                     |
| Grafana    | 10.x            | Dashboards em `grafana/`                                       |
| Nginx      | 1.x             | Reverse proxy (opcional mas recomendado)                         |
| NSSM       | 2.24            | Gestão de serviços Windows                                     |

---

## Instalação dos Serviços (Windows / NSSM)

### Script automático (recomendado)

```powershell
# PowerShell como Administrador, na raiz do projecto:
.\instalar-servicos.ps1
```

O script detecta automaticamente os paths de Python, Node.js, Nginx, Mosquitto e InfluxDB.  
Se não encontrar algum componente, pede o path ao utilizador antes de instalar qualquer coisa.  
Funciona em qualquer PC independentemente de onde a pasta SoundDash está colocada.

### Instalação manual

> Executar **PowerShell como Administrador**.
> Substituir os paths abaixo pelos da máquina de destino.

```powershell
# ── InfluxDB ──────────────────────────────────────────────────────────
nssm install SoundDash-InfluxDB "C:\...\InfluxData\influxd.exe"
nssm set SoundDash-InfluxDB AppParameters "--bolt-path=C:\Users\laa\.influxdbv2\influxd.bolt --engine-path=C:\Users\laa\.influxdbv2\engine"
nssm set SoundDash-InfluxDB DisplayName "SoundDash InfluxDB"
nssm set SoundDash-InfluxDB Start SERVICE_AUTO_START

# ── Mosquitto ─────────────────────────────────────────────────────────
nssm install SoundDash-Mosquitto "C:\...\mosquitto\mosquitto.exe" "-c" "mosquittoV1.conf"
nssm set SoundDash-Mosquitto AppDirectory "C:\...\mosquitto"
nssm set SoundDash-Mosquitto DisplayName "SoundDash Mosquitto"
nssm set SoundDash-Mosquitto Start SERVICE_AUTO_START

# ── Node-RED ──────────────────────────────────────────────────────────
nssm install SoundDash-NodeRED "C:\Program Files\nodejs\node.exe" "C:\...\node_modules\node-red\red.js" "-u" "C:\Users\laa\.node-red"
nssm set SoundDash-NodeRED DisplayName "SoundDash NodeRED"
nssm set SoundDash-NodeRED Start SERVICE_AUTO_START

# ── Flask ─────────────────────────────────────────────────────────────
nssm install SoundDash-Flask "C:\...\python.exe" "run.py"
nssm set SoundDash-Flask AppDirectory "C:\...\SoundDash\webApp"
nssm set SoundDash-Flask DisplayName "SoundDash Flask Web"
nssm set SoundDash-Flask Start SERVICE_AUTO_START

# ── Nginx ─────────────────────────────────────────────────────────────
nssm install SoundDash-Nginx "C:\nginx\nginx.exe"
nssm set SoundDash-Nginx AppDirectory "C:\nginx\"
nssm set SoundDash-Nginx DisplayName "SoundDash Nginx"
nssm set SoundDash-Nginx Start SERVICE_AUTO_START
```

Para comandos completos e actualização de serviços existentes (uninstall + reinstall), ver `GUIAS/nssmConfiguration.txt`.

---

## Gestão Rápida de Serviços

```powershell
# Iniciar tudo (requer admin)
.\start-all.bat

# Parar tudo
.\stop-all.bat

# Ver estado
.\status.bat

# Controlo individual
nssm start  SoundDash-Flask
nssm stop   SoundDash-Flask
nssm restart SoundDash-Flask
```

---

## Páginas Web

| URL                 | Descrição                                   | Auth |
| ------------------- | --------------------------------------------- | ---- |
| `/`               | Homepage, visão geral do sistema            | —   |
| `/atual`          | Leituras em tempo real (LAeq, LAFmax, LCpeak) | —   |
| `/tempo`          | Séries temporais + distribuição KDE        | —   |
| `/mapa`           | Mapa do piso hospitalar com sensores          | —   |
| `/eventos`        | Eventos de áudio detectados (YAMNet)         | —   |
| `/display`        | Modo TV, ecrã completo, tema escuro         | —   |
| `/guia`           | Guia de interpretação dos indicadores       | —   |
| `/controlo`       | Painel de administração + config remota     | ✓   |
| `/acesso-tecnico` | Login                                         | —   |

---

## API Reference

Todos os endpoints estão prefixados em `/api/`.

### Sensores

```
GET /api/sensores
```

Devolve a lista de sensores com dados no InfluxDB.

```json
["Sensor1", "Sensor2", "Sensor3", ...]
```

---

### Dados em tempo real

```
GET /api/data?sensor_id=Sensor1&field=LAEA&start=-1h&stop=now()
```

| Parâmetro    | Tipo   | Descrição                                    |
| ------------- | ------ | ---------------------------------------------- |
| `sensor_id` | string | Nome da measurement no InfluxDB                |
| `field`     | string | `LAEA`, `LAFmax`, `LAFmin`, `LCpeak`   |
| `start`     | string | Offset relativo (`-1h`, `-30m`) ou ISO8601 |
| `stop`      | string | `now()` ou ISO8601                           |

Usa automaticamente o bucket horário (`SoundDashHosp_hourly`) para janelas superiores a 6 horas.

---

### Estatísticas agregadas

```
GET /api/stats?sensor_id=Sensor1&start=2025-01-01T00:00Z&end=2025-01-02T00:00Z&window=5m
```

Devolve séries de `laea`, `lcpeak`, `lafmax`, `lafmin` com agregação por janela temporal.

---

### Indicador Lden (Directiva Europeia)

```
GET /api/lden?sensor_id=Sensor1&start=2025-01-15T00:00Z&end=2025-01-15T23:59Z
```

Calcula o Lden do dia especificado com as ponderações normalizadas:

- Dia (08h–20h): +0 dB
- Tarde (20h–23h): +5 dB
- Noite (23h–08h): +10 dB

```json
{ "laeq_day": 58.3, "laeq_evening": 52.1, "laeq_night": 44.7, "lden": 59.2 }
```

---

### Eventos de áudio

```
GET /api/eventos?sensor=Sensor1&start=2025-01-15T08:00&end=2025-01-15T18:00
```

Devolve todos os instantes com `EventDetect > 0` e os tipos de evento classificados pelo modelo YAMNet.

---

### Classificação YAMNet (tempo real)

```
GET /api/classes?sensor_id=Sensor1
```

Top 3 classes de áudio detectadas nos últimos 5 minutos.

```json
[
  { "ClassID": 0,  "ClassName": "Speech",      "ClassScore": 0.87 },
  { "ClassID": 137,"ClassName": "Alarm",        "ClassScore": 0.06 },
  { "ClassID": 72, "ClassName": "Music",        "ClassScore": 0.03 }
]
```

---

### Download CSV

```
GET /api/download?sensor_id=Sensor1&start=2025-01-15T00:00Z&end=2025-01-16T00:00Z
```

Exporta todos os campos do sensor no intervalo especificado como ficheiro `.csv`.

---

### Configuração remota de sensores

```
GET  /api/parametros/<sensor_id>     # Obter configuração actual do sensor
POST /api/parametros                 # Enviar nova configuração
```

O `ConfigManager` publica via MQTT (`sound/config/update/{id}`) e aguarda ACK do sensor (timeout: 15s). Mantém cache com validade de 5 minutos.

---

### Configuração do sistema

```
POST /api/system_config              # Actualizar URL do Grafana (requer login)
```

```json
{ "grafana_url": "http://10.64.137.6/grafana" }
```

---

## Configuração dos Sensores (Raspberry Pi)

Copiar `sensor/sensor_side.py` para o RPi e criar/editar `sensor/config.json`:

```json
{
  "station": { "id": 1, "location": "Ala Norte", "tipo": "urban_monitoring" },
  "audio":   { "sample_rate": 48000, "channels": 1 },
  "mqtt":    { "broker": "10.64.137.6", "port": 1884, "topic": "sound/levels" }
}
```

```bash
pip3 install paho-mqtt
python3 sensor_side.py
```

O sensor subscreve `sound/config/request/{id}` e responde em `sound/config/response/{id}`, permitindo configuração remota via painel `/controlo`.

---

## InfluxDB — Buckets e Tarefas Automáticas

| Bucket                   | Retenção | Conteúdo                                 |
| ------------------------ | ---------- | ----------------------------------------- |
| `SoundDashHosp`        | ∞         | Dados raw (~4 Hz por sensor)              |
| `SoundDashHosp_hourly` | ∞         | Médias horárias (geradas por Flux task) |

Importar as tarefas em `Influx_Scripts/`:

| Ficheiro                     | Frequência | O que faz                                 |
| ---------------------------- | ----------- | ----------------------------------------- |
| `task_downsampling.flux`   | Cada hora   | Raw → médias de 1 minuto                |
| `task_stats_horarias.flux` | Cada hora   | LAeq, LAFmax, LAFmin, P50, P95 por sensor |
| `task_lden_diario.flux`    | Meia-noite  | Lden diário por sensor (EN ISO 1996)     |

Para importar dados históricos de CSV:

```bash
cd Influx_Scripts
python influx_import.py ../data/Levels_20250929_093735.csv Sensor1
```

---

## Grafana

Dashboards exportados em `grafana/`. Importar via **Dashboards → Import → Upload JSON**.

Os painéis Grafana são embutidos via iframe nas páginas `/atual`, `/tempo`, `/mapa` e `/display`.
O URL base do Grafana é configurável em `/controlo` → guardado em `webApp/system_config.json`.

---

## Desenvolvimento

```bash
cd webApp
python run.py          # Arranca em http://0.0.0.0:5000 (debug=True)
```

### Adicionar um endpoint API

1. Abrir [webApp/app/blueprints/api/routes.py](webApp/app/blueprints/api/routes.py)
2. Decorar com `@api_bp.route('/novo-endpoint')`
3. Aceder a InfluxDB via `get_client()` de `app.services.influx`
4. Aceder a recursos da app via `current_app.id_to_name` / `current_app.config_mgr`

### Adicionar uma página

1. Adicionar rota em [webApp/app/blueprints/pages/routes.py](webApp/app/blueprints/pages/routes.py)
2. Criar template em `app/templates/` estendendo `base.html`
3. Criar `app/static/css/{pagina}.css` e `app/static/js/{pagina}.js`
4. Adicionar link na nav de `app/templates/base.html`

### Adicionar um utilizador

```bash
cd auth
python hashGenerator.py   # editar a password hardcoded no ficheiro
```

Copiar o hash gerado para `webApp/users.json`:

```json
{ "admin": "pbkdf2:sha256:..." }
```

---

## Notas

- `debug=True` em `run.py` — desactivar em produção
- O token InfluxDB e a `SECRET_KEY` estão em `webApp/app/config.py` — não commitir credenciais reais
- Para simular dados de sensor sem RPi: `python sensor/CSVtoJSON_MQTT.py data/ficheiro.csv Sensor1`
