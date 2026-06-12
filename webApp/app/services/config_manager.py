"""
config_manager.py
Sistema de gestão de configurações remotas das estações via MQTT

Adicionar ao webAppGrafana.py:
    from config_manager import ConfigManager
    config_mgr = ConfigManager(mqtt_broker='10.64.137.6', mqtt_port=1884)
    config_mgr.start()
    
    # Registar rotas
    app.route('/api/parametros/<sensor_id>', methods=['GET'])(config_mgr.get_config)
    app.route('/api/parametros', methods=['POST'])(config_mgr.update_config)
"""

import json
import time
import hashlib
import threading
from datetime import datetime
from flask import request, jsonify
import paho.mqtt.client as mqtt
import time


class ConfigManager:
    def __init__(self, mqtt_broker='10.64.137.6', mqtt_port=1884): 
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.client = mqtt.Client(client_id="flask_config_manager", clean_session=True)
        
        # Cache de configurações em memória {sensor_id: {config, timestamp, status}}
        self.config_cache = {}
        
        # Locks para sincronização
        self.locks = {}
        
        # Timeouts (segundos)
        self.request_timeout = 10
        self.update_timeout = 15
        
        # Setup MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback quando conecta ao broker MQTT"""
        if rc == 0:
            print(f"[ConfigManager] Conectado ao MQTT broker {self.mqtt_broker}:{self.mqtt_port}")
            # Subscrever aos tópicos de response e ACK (wildcard para todos os sensores)
            client.subscribe("sound/config/response/#")
            client.subscribe("sound/config/ack/#")
            print("[ConfigManager] Subscrito a sound/config/response/# e sound/config/ack/#")
        else:
            print(f"[ConfigManager] ERRO ao conectar: código {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Callback quando recebe mensagem MQTT"""
        topic_parts = msg.topic.split('/')
        
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            
            if len(topic_parts) >= 4:
                msg_type = topic_parts[2]  # 'response' ou 'ack'
                sensor_id = topic_parts[3]
                
                if msg_type == 'response':
                    # Estação enviou a config atual
                    print(f"[ConfigManager] Config recebida do sensor {sensor_id}")
                    self.config_cache[sensor_id] = {
                        'config': payload,
                        'timestamp': datetime.now().isoformat(),
                        'status': 'loaded'
                    }
                    
                elif msg_type == 'ack':
                    # Estação confirmou update
                    print(f"[ConfigManager] ACK recebido do sensor {sensor_id}: {payload}")
                    if sensor_id in self.config_cache:
                        self.config_cache[sensor_id]['status'] = payload.get('status', 'unknown')
                        self.config_cache[sensor_id]['ack_timestamp'] = datetime.now().isoformat()
                        
        except json.JSONDecodeError as e:
            print(f"[ConfigManager] Erro ao decodificar JSON: {e}")
        except Exception as e:
            print(f"[ConfigManager] Erro ao processar mensagem: {e}")
    
    def start(self):
        """Inicia a conexão MQTT em thread separada"""
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            thread = threading.Thread(target=self.client.loop_forever, daemon=True)
            thread.start()
            print("[ConfigManager] Thread MQTT iniciada")
        except Exception as e:
            print(f"[ConfigManager] ERRO ao iniciar MQTT: {e}")
    
    def request_config(self, sensor_id):
        """
        Pede à estação que envie a sua configuração atual
        Retorna True se publicou o request com sucesso
        """
        import time

        print(f"[ConfigManager] ----- REQUEST CONFIG -----")
        print(f"[ConfigManager] sensor_id: {sensor_id}")
        
        topic = f"sound/config/request/{sensor_id}"
        payload = {
            'timestamp': datetime.now().isoformat(),
            'requester': 'flask_app'
        }
        print(f"[ConfigManager] Topic: {topic}")
        print(f"[ConfigManager] Payload: {payload}")
        
        try:
            # Aguardar conexão (até 5 segundos)
            max_wait = 5
            waited = 0
            while not self.client.is_connected() and waited < max_wait:
                print(f"[ConfigManager] Aguardando conexão MQTT... ({waited}s)")
                time.sleep(0.5)
                waited += 0.5
            
            if not self.client.is_connected():
                print(f"[ConfigManager] ✗ Timeout aguardando conexão MQTT!")
                return False
            
            print(f"[ConfigManager] ✓ Cliente MQTT conectado")
            print(f"[ConfigManager] A publicar mensagem...")
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            print(f"[ConfigManager] Publish result code: {result.rc}")      
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"[ConfigManager] Request enviado para sensor {sensor_id}")
                return True
            else:
                print(f"[ConfigManager] ERRO ao enviar request: {result.rc}")
                return False
        except Exception as e:
            print(f"[ConfigManager] ERRO: {e}")
            return False
    
    def wait_for_config(self, sensor_id, timeout=None):
        """
        Aguarda pela config da estação (polling no cache)
        Retorna a config ou None se timeout
        """
        if timeout is None:
            timeout = self.request_timeout
            
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if sensor_id in self.config_cache and self.config_cache[sensor_id]['status'] == 'loaded':
                return self.config_cache[sensor_id]['config']
            time.sleep(0.1)  # Poll a cada 100ms
        
        return None
    
    def get_config(self, sensor_id):
        """
        Rota GET /api/parametros/<sensor_id>
        Retorna a configuração atual da estação
        """
        print(f"[ConfigManager] ===== GET CONFIG START =====")
        print(f"[ConfigManager] sensor_id: {sensor_id}")

        # Verificar se está em cache e é recente (< 5 min)
        if sensor_id in self.config_cache:
            cache_entry = self.config_cache[sensor_id]
            cache_time = datetime.fromisoformat(cache_entry['timestamp'])
            age_seconds = (datetime.now() - cache_time).total_seconds()
            
            if age_seconds < 300:  # 5 minutos
                print(f"[ConfigManager] Usando config em cache para sensor {sensor_id} (idade: {age_seconds:.1f}s)")
                return jsonify({
                    'success': True,
                    'sensor_id': sensor_id,
                    'config': cache_entry['config'],
                    'cached': True,
                    'cache_age_seconds': age_seconds
                })
        
        # Cache expirado ou inexistente - pedir à estação
        print(f"[ConfigManager] Pedindo config à estação {sensor_id}...")
        
        if not self.request_config(sensor_id):
            print(f"[ConfigManager] ERRO: request_config retornou False")
            return jsonify({'success': False, 'erro': 'Erro ao comunicar com broker MQTT'}), 500
        
        print(f"[ConfigManager] Request enviado, aguardando resposta...")
        # Aguardar resposta
        config = self.wait_for_config(sensor_id)
        
        if config:
            print(f"[ConfigManager] Config recebida com sucesso!")
            return jsonify({
                'success': True,
                'sensor_id': sensor_id,
                'config': config,
                'cached': False
            })
        else:
            print(f"[ConfigManager] TIMEOUT: sem resposta da estação")
            return jsonify({
                'success': False,
                'erro': f'Timeout ao aguardar resposta da estação {sensor_id}. Verifique se a estação está online.'
            }), 504
    
    def reboot_sensor(self, sensor_id):
        """Envia comando de reboot para a estação via MQTT."""
        if not self.client.is_connected():
            return False, 'Não conectado ao broker MQTT'
        topic   = f"sound/control/reboot/{sensor_id}"
        payload = {'timestamp': datetime.now().isoformat(), 'source': 'flask_app'}
        result  = self.client.publish(topic, json.dumps(payload), qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[ConfigManager] Reboot enviado para sensor {sensor_id}")
            return True, 'Comando de reboot enviado'
        return False, f'Erro MQTT: {result.rc}'

    def update_config(self):
        """
        Rota POST /api/parametros
        Envia nova configuração para a estação
        
        Espera JSON:
        {
            "sensor_id": "2",
            "config": { ... },
            "checksum": "sha256_hash"
        }
        """
        try:
            data = request.get_json()
            print(f"[ConfigManager] Data Recebida para update_config: {data}")
            print(f"[ConfigManager] Type: {type(data)}")

            if data:
                print(f"[ConfigManager] keys: {list(data.keys())}")
                print(f"[ConfigManager] sensor_id: {data.get('sensor_id')}")
                print(f"[ConfigManager] config: {data.get('config') is not None}")

            if not data:
                return jsonify({'success': False, 'erro': 'JSON inválido ou ausente'}), 400

            
            sensor_id = data.get('sensor_id')
            config = data.get('config')
            checksum_frontend = data.get('checksum')
            
            if not sensor_id or not config:
                return jsonify({'success': False, 'erro': 'sensor_id e config são obrigatórios'}), 400
            
            # Validar checksum
            #if checksum_frontend:
            config_str = json.dumps(config, sort_keys=True)
            checksum_backend = hashlib.sha256(config_str.encode('utf-8')).hexdigest()
            
            if checksum_frontend and checksum_frontend != checksum_backend:
                print(f"[ConfigManager] AVISO: Checksum mismatch!")
                print(f"  Frontend: {checksum_frontend}")
                print(f"  Backend:  {checksum_backend}")
                # Continuar mesmo assim (frontend pode ter ordenado diferente)
            #else:
                config_str = json.dumps(config, sort_keys=True)
                checksum_backend = hashlib.sha256(config_str.encode('utf-8')).hexdigest()
                print(f"[ConfigManager] Checksum calculado (sem frontend): {checksum_backend}")

            # Publicar no MQTT

            max_wait = 5
            waited = 0
            while not self.client.is_connected() and waited < max_wait:
                print(f"[ConfigManager] Aguardando conexão MQTT... ({waited}s)")
                time.sleep(0.5)
                waited += 0.5

            if not self.client.is_connected():
                print(f"[ConfigManager] Timeout aguardando conexão MQTT!")
                return jsonify({'success': False, 'erro': 'Não conectado ao broker MQTT'}), 500
            
            print(f"[ConfigManager] Cliente MQTT conectado")
            topic = f"sound/config/update/{sensor_id}"
            payload = {
                'config': config,
                'checksum': checksum_backend,
                'timestamp': datetime.now().isoformat(),
                'source': 'flask_app'
            }
            
            print(f"[ConfigManager] A publicar update para {topic}")
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            print(f"[ConfigManager] Código de resultado do publish: {result.rc}")
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[ConfigManager] ERRO ao publicar update: {result.rc}")
                return jsonify({'success': False, 'erro': f'Erro MQTT: {result.rc}'}), 500
            
            print(f"[ConfigManager] Config update enviado para sensor {sensor_id}")
            
            # Aguardar ACK da estação
            time.sleep(0.5)  # Pequeno delay para dar tempo ao ACK chegar
            
            ack_received = False
            start_time = time.time()
            
            while time.time() - start_time < self.update_timeout:
                if sensor_id in self.config_cache and 'ack_timestamp' in self.config_cache[sensor_id]:
                    ack_time = datetime.fromisoformat(self.config_cache[sensor_id]['ack_timestamp'])
                    if (datetime.now() - ack_time).total_seconds() < 2:  # ACK recente
                        ack_received = True
                        break
                time.sleep(0.1)
            
            if ack_received:
                status = self.config_cache[sensor_id]['status']
                return jsonify({
                    'success': True,
                    'sensor_id': sensor_id,
                    'status': status,
                    'message': 'Configuração atualizada com sucesso'
                })
            else:
                # Timeout - mas pode ter sido aplicada mesmo assim
                return jsonify({
                    'success': True,
                    'sensor_id': sensor_id,
                    'status': 'unknown',
                    'message': 'Configuração enviada mas ACK não recebido (pode ter sido aplicada)'
                }), 202
                
        except Exception as e:
            print(f"[ConfigManager] ERRO: {e}")
            return jsonify({'success': False, 'erro': str(e)}), 500
