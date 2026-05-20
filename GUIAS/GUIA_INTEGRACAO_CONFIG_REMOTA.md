# Guia de Integração - Sistema de Gestão Remota de Configurações

## 📋 Visão Geral

Sistema completo para gerir configurações das estações SoundDashHosp remotamente via MQTT.

**Componentes:**
1. **config_manager.py** → Backend Flask (roda no servidor)
2. **station_config_receiver.py** → Cliente (roda em cada Raspberry Pi)
3. **controlo_updated.html** → Frontend web
4. **SoundMeterSemaf_config_v2.json** → Estrutura JSON atualizada

**Fluxo:**
```
User seleciona sensor → Flask pede config via MQTT → RPi responde → Frontend popula formulário
User edita e salva → Flask envia update via MQTT → RPi aplica → RPi envia ACK
```

---

## 🔧 Instalação

### 1. No Servidor Flask (VM ISEL)

#### 1.1. Instalar dependências
```bash
pip install paho-mqtt --break-system-packages
```

#### 1.2. Adicionar config_manager.py ao projeto
```bash
# Copiar config_manager.py para o diretório da aplicação Flask
cp config_manager.py /caminho/do/projeto/
```

#### 1.3. Modificar webAppGrafana.py

Adicionar no INÍCIO do ficheiro (depois dos outros imports):
```python
from config_manager import ConfigManager
```

Adicionar DEPOIS de criar a app Flask (`app = Flask(__name__)`):
```python
# Inicializar gestor de configurações
config_mgr = ConfigManager(mqtt_broker='10.64.137.6', mqtt_port=1884)
config_mgr.start()
print("[Flask] ConfigManager iniciado")
```

Adicionar as ROTAS (antes do `if __name__ == '__main__':`):
```python
# === ROTAS DE GESTÃO DE CONFIGURAÇÕES ===

@app.route('/api/parametros/<sensor_id>', methods=['GET'])
def get_parametros(sensor_id):
    """Obter configuração atual de um sensor"""
    return config_mgr.get_config(sensor_id)

@app.route('/api/parametros', methods=['POST'])
def update_parametros():
    """Atualizar configuração de um sensor"""
    return config_mgr.update_config()
```

#### 1.4. Substituir controlo.html
```bash
# Backup do antigo
cp templates/controlo.html templates/controlo.html.backup

# Copiar novo
cp controlo_updated.html templates/controlo.html
```

#### 1.5. Atualizar rota /controlo no webAppGrafana.py

Modificar a rota para passar `grafana_url` ao template:
```python
@app.route('/controlo')
@login_required
def controlo():
    config = load_system_config()
    return render_template('controlo.html', grafana_url=config['grafana_url'])
```

#### 1.6. Reiniciar Flask
```bash
# Parar o Flask se estiver a correr
# Ctrl+C se estiver em foreground
# Ou: pkill -f webAppGrafana.py

# Arrancar novamente
python webAppGrafana.py
```

**Verificar logs:**
```
[Flask] ConfigManager iniciado
[ConfigManager] Conectado ao MQTT broker 10.64.137.6:1884
[ConfigManager] Subscrito a sound/config/response/# e sound/config/ack/#
[ConfigManager] Thread MQTT iniciada
```

---

### 2. Em Cada Estação (Raspberry Pi)

#### 2.1. Instalar dependências
```bash
pip3 install paho-mqtt
```

#### 2.2. Copiar station_config_receiver.py
```bash
# Copiar para o diretório do projeto da estação
scp station_config_receiver.py laa@10.64.137.X:/home/laa/soundmeter/
```

#### 2.3. Atualizar JSON de configuração

Abrir o ficheiro `config.json` da estação e:
- ✅ Adicionar campo `"tipo"` dentro de `"station"`
- ❌ Remover secção `"output"` completa

Exemplo (ver `SoundMeterSemaf_config_v2.json` para estrutura completa):
```json
{
  "station": {
    "sensor_ID": 2,
    "local_Info": "CampoGrandeLx",
    "tipo": "urban_monitoring",   ← NOVO
    ...
  },
  "audio": { ... },
  ...
  // REMOVER esta secção:
  // "output": { ... }  ← APAGAR
}
```

#### 2.4. Testar o receiver standalone
```bash
cd /home/laa/soundmeter/
python3 station_config_receiver.py --sensor-id 2 --config-file config.json
```

**Output esperado:**
```
[StationConfig] Inicializado para sensor 2
[StationConfig] Config file: config.json
[StationConfig] Config carregada de config.json
[StationConfig] A conectar a 10.64.137.6:1884...
[StationConfig] Conectado ao broker 10.64.137.6:1884
[StationConfig] Subscrito a sound/config/request/2
[StationConfig] Subscrito a sound/config/update/2
[StationConfig] Pronto para receber comandos de configuração
```

Deixar a correr em background:
```bash
# Ctrl+Z para pausar
# bg para mandar para background
# disown para desassociar do terminal

# Ou usar screen/tmux:
screen -S config_receiver
python3 station_config_receiver.py --sensor-id 2 --config-file config.json
# Ctrl+A, D para detach
```

#### 2.5. [OPCIONAL] Integrar no código principal da estação

Se preferires integrar no código principal em vez de correr standalone:

No ficheiro principal da estação (ex: `soundmeter_main.py`), adicionar:
```python
from station_config_receiver import StationConfigReceiver
import threading

# No início do programa, depois de carregar a config:
config_receiver = StationConfigReceiver(
    sensor_id=2,  # ou ler de config['station']['sensor_ID']
    config_file_path='config.json',
    mqtt_broker='10.64.137.6',
    mqtt_port=1884
)

# Arrancar em thread separada
config_thread = threading.Thread(target=config_receiver.start, daemon=True)
config_thread.start()

# Resto do código da estação continua normalmente...
```

---

## 🧪 Testes

### Teste 1: Carregar configuração

1. Abrir browser: `http://10.64.137.6/controlo`
2. Login (admin)
3. Selecionar sensor no dropdown (ex: "Campo Grande")
4. Aguardar 2-5 segundos
5. ✅ Formulário deve preencher automaticamente
6. ✅ Badge "Online" deve aparecer

**Troubleshooting:**
- Se aparecer "Offline": verificar se `station_config_receiver.py` está a correr no RPi
- Se ficar em "Loading" eternamente: verificar firewall/rede entre servidor e RPi

### Teste 2: Atualizar configuração

1. Alterar um valor (ex: mudar `level_led_green` de 50 para 55)
2. Clicar "Guardar Configurações do Sensor"
3. Aguardar 3-10 segundos
4. ✅ Deve aparecer "Parâmetros enviados com sucesso!"
5. ✅ Mensagem pode dizer "(Reinício necessário)" se mudou flags críticas

**Verificar no RPi:**
```bash
# Ver logs do receiver
# Deve mostrar:
[StationConfig] Config update recebido
[StationConfig] ✓ Config aplicada com sucesso
[StationConfig] ✓ Mudanças aplicadas (sem reinício necessário)
[StationConfig] ACK enviado: ok - Config updated successfully

# Verificar que ficheiro foi atualizado
cat config.json | grep level_led_green
# Deve mostrar o novo valor: 55
```

### Teste 3: Mudanças críticas (reboot necessário)

1. Mudar `sample_rate` de 48000 para 44100
2. Guardar
3. ✅ Deve avisar "(Reinício necessário na estação)"

**No RPi:**
```
[StationConfig] Mudança crítica detectada: audio.sample_rate (48000 → 44100)
[StationConfig] ⚠ Mudanças requerem reinício da aplicação
[StationConfig] ACK enviado: ok - Config updated - restart required
```

---

## 📊 Tópicos MQTT Utilizados

| Tópico | Direção | Descrição |
|--------|---------|-----------|
| `sound/config/request/<sensor_id>` | Flask → RPi | Flask pede config atual |
| `sound/config/response/<sensor_id>` | RPi → Flask | RPi envia config atual |
| `sound/config/update/<sensor_id>` | Flask → RPi | Flask envia nova config |
| `sound/config/ack/<sensor_id>` | RPi → Flask | RPi confirma aplicação |

**Exemplos:**
- `sound/config/request/2` → Pedir config do sensor 2
- `sound/config/response/2` → Resposta com config do sensor 2
- `sound/config/update/2` → Atualizar sensor 2
- `sound/config/ack/2` → ACK do sensor 2

---

## 🔍 Logs e Debug

### Ver logs do Flask (servidor)
```bash
# Se correr em foreground, aparece no terminal
# Procurar por:
[ConfigManager] Config recebida do sensor 2
[ConfigManager] ACK recebido do sensor 2: {'status': 'ok', ...}
[ConfigManager] Request enviado para sensor 2
[ConfigManager] Config update enviado para sensor 2
```

### Ver logs do RPi (estação)
```bash
# Se correr standalone
python3 station_config_receiver.py --sensor-id 2 --config-file config.json

# Procurar por:
[StationConfig] Config request recebido de flask_app
[StationConfig] Config enviada via sound/config/response/2
[StationConfig] Config update recebido
[StationConfig] ✓ Config aplicada com sucesso
[StationConfig] ACK enviado: ok
```

### Debug MQTT (ver mensagens em tempo real)
```bash
# No servidor ou RPi, instalar mosquitto-clients:
sudo apt install mosquitto-clients

# Subscrever a todos os tópicos de config:
mosquitto_sub -h 10.64.137.6 -p 1884 -t 'sound/config/#' -v

# Deve mostrar:
sound/config/request/2 {"timestamp": "2025-05-05T...", "requester": "flask_app"}
sound/config/response/2 {"station": {...}, "audio": {...}, ...}
sound/config/update/2 {"config": {...}, "checksum": "abc123...", ...}
sound/config/ack/2 {"status": "ok", "message": "Config updated successfully", ...}
```

---

## ⚠️ Segurança & Validações

### Checksum SHA-256
- Frontend calcula checksum do JSON antes de enviar
- Backend recalcula e compara (avisa se diferentes)
- RPi valida novamente antes de aplicar

### Backup Automático
- Antes de salvar nova config, RPi cria backup:
  ```
  config.json.backup_20250505_143022
  ```
- Se algo correr mal, restaura automaticamente

### Flags Críticas (requerem reboot)
- `audio.sample_rate`, `audio.channels`, `audio.chunk_size`
- `mqtt.broker`, `mqtt.port`
- `sound_event_detect.model_path`

**Comportamento:** RPi aplica a config mas avisa que precisa de reinício manual.

---

## 📝 Mudanças no JSON de Configuração

### ✅ ADICIONADO
```json
{
  "station": {
    "tipo": "urban_monitoring"  ← NOVO CAMPO
  }
}
```

### ❌ REMOVIDO
```json
{
  // "output": {              ← SECÇÃO APAGADA
  //   "path": "...",
  //   "dir_csv": "...",
  //   "dir_waves": "..."
  // }
}
```

**Nota:** O campo `tipo` pode ser usado para classificar estações:
- `"urban_monitoring"` - Monitorização urbana
- `"hospital"` - Ambiente hospitalar
- `"airport"` - Proximidade aeroporto
- `"construction"` - Zona de obras
- etc.

---

## 🚀 Próximos Passos Opcionais

### 1. Persistência em Base de Dados
Atualmente as configs estão em cache memória. Para persistir:
```python
# Em config_manager.py, adicionar:
import sqlite3

class ConfigManager:
    def __init__(...):
        self.db = sqlite3.connect('configs.db')
        self._init_db()
    
    def _init_db(self):
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS configs (
                sensor_id TEXT PRIMARY KEY,
                config TEXT,
                timestamp TEXT
            )
        ''')
```

### 2. Histórico de Mudanças
Guardar log de todas as alterações:
```python
def log_change(sensor_id, old_config, new_config, user):
    changes = compare_configs(old_config, new_config)
    db.execute('''
        INSERT INTO config_history (sensor_id, changes, user, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (sensor_id, json.dumps(changes), user, datetime.now()))
```

### 3. Autenticação MQTT
Adicionar username/password ao broker:
```python
self.client.username_pw_set(username='flask_admin', password='***')
```

### 4. Validação de Valores
Antes de aplicar, validar ranges:
```python
def validate_config(config):
    if config['audio']['sample_rate'] not in [44100, 48000]:
        raise ValueError("Sample rate inválido")
    if config['leds_display']['level_led_green'] < 0 or > 120:
        raise ValueError("LED level fora do range 0-120 dB")
```

---

## 📞 Suporte

Se encontrares problemas:

1. **Verificar conexão MQTT:** `mosquitto_sub -h 10.64.137.6 -p 1884 -t '#'`
2. **Ver logs Flask:** procurar por `[ConfigManager]`
3. **Ver logs RPi:** procurar por `[StationConfig]`
4. **Testar manualmente:** publicar mensagem MQTT de teste
   ```bash
   mosquitto_pub -h 10.64.137.6 -p 1884 -t 'sound/config/request/2' -m '{"test": true}'
   ```

---

## ✅ Checklist de Implementação

### Servidor (VM ISEL)
- [ ] `pip install paho-mqtt` instalado
- [ ] `config_manager.py` copiado para o projeto
- [ ] `webAppGrafana.py` modificado (imports + ConfigManager + rotas)
- [ ] `controlo.html` substituído pelo novo
- [ ] Rota `/controlo` atualizada para passar `grafana_url`
- [ ] Flask reiniciado
- [ ] Logs mostram `[ConfigManager] Thread MQTT iniciada`

### Estação (RPi)
- [ ] `pip3 install paho-mqtt` instalado
- [ ] `station_config_receiver.py` copiado
- [ ] `config.json` atualizado (campo `tipo` adicionado, secção `output` removida)
- [ ] `station_config_receiver.py` a correr (standalone ou integrado)
- [ ] Logs mostram `[StationConfig] Pronto para receber comandos`

### Testes
- [ ] Teste 1: Carregar config - PASSOU
- [ ] Teste 2: Atualizar config - PASSOU
- [ ] Teste 3: Mudança crítica - PASSOU
- [ ] Verificar backup criado no RPi

---

**Boa sorte com a implementação! 🎉**
