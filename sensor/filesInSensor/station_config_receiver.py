"""
station_config_receiver.py
Código para correr nas estações (Raspberry Pi)
Recebe comandos de configuração via MQTT e aplica-os

INSTALAÇÃO:
    pip install paho-mqtt

USO:
    python station_config_receiver.py --sensor-id 2 --config-file config.json
    
    Ou integrar no código principal da estação importando StationConfigReceiver
"""

import json
import hashlib
import argparse
import os
import sys
import subprocess
from datetime import datetime
import paho.mqtt.client as mqtt

#para deep_merge
import copy


class StationConfigReceiver:
    def __init__(self, sensor_id, config_file_path, mqtt_broker='10.64.137.6', mqtt_port=1884,
                 mqtt_transport='tcp', mqtt_path='/mqtt'):
        """
        Inicializa o receiver de configurações

        Args:
            sensor_id: ID do sensor (ex: "2")
            config_file_path: Caminho para o ficheiro config.json local
            mqtt_broker: Endereço do broker MQTT
            mqtt_port: Porta do broker MQTT
            mqtt_transport: 'tcp' (local/Tailscale) ou 'websockets' (remoto via Nginx)
            mqtt_path: path WebSocket (ex: '/mqtt'), ignorado em modo tcp
        """
        self.sensor_id = str(sensor_id)
        self.config_file = config_file_path
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port

        # Verificar se ficheiro de config existe
        if not os.path.exists(self.config_file):
            print(f"[ERRO] Ficheiro de configuração não encontrado: {self.config_file}")
            sys.exit(1)

        # Carregar config atual
        self.current_config = self.load_config()

        # Setup MQTT
        client_id = f"station_{self.sensor_id}_config"
        if mqtt_transport == 'websockets':
            self.client = mqtt.Client(client_id=client_id, clean_session=True, transport="websockets")
            self.client.ws_set_options(path=mqtt_path)
        else:
            self.client = mqtt.Client(client_id=client_id, clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        print(f"[StationConfig] Inicializado para sensor {self.sensor_id}")
        print(f"[StationConfig] Config file: {self.config_file}")
    
    def load_config(self):
        """Carrega a configuração do ficheiro JSON"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            print(f"[StationConfig] Config carregada de {self.config_file}")
            return config
        except Exception as e:
            print(f"[ERRO] Não foi possível carregar config: {e}")
            return None
    
    def save_config(self, new_config):
        """
        Guarda nova configuração no ficheiro JSON
        Faz backup do ficheiro anterior
        """
        try:
            # Backup do ficheiro atual
            backup_file = f"{self.config_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if os.path.exists(self.config_file):
                os.rename(self.config_file, backup_file)
                print(f"[StationConfig] Backup criado: {backup_file}")
            
            # Guardar nova config
            with open(self.config_file, 'w') as f:
                json.dump(new_config, f, indent=2)
            
            print(f"[StationConfig] Nova config guardada em {self.config_file}")
            self.current_config = new_config
            return True
            
        except Exception as e:
            print(f"[ERRO] Não foi possível guardar config: {e}")
            # Restaurar backup se existir
            if os.path.exists(backup_file):
                os.rename(backup_file, self.config_file)
                print(f"[StationConfig] Config restaurada do backup")
            return False
    
    def deep_merge(self, base, updates):
        result = copy.deepcopy(base)
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.deep_merge(result[key], value)
            else:
                result[key] = value
        return result
        
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback quando conecta ao broker"""
        if rc == 0:
            print(f"[StationConfig] Conectado ao broker {self.mqtt_broker}:{self.mqtt_port}")
            # Subscrever aos tópicos deste sensor
            client.subscribe(f"sound/config/request/{self.sensor_id}")
            client.subscribe(f"sound/config/update/{self.sensor_id}")
            client.subscribe(f"sound/control/reboot/{self.sensor_id}")
            print(f"[StationConfig] Subscrito a sound/config/request/{self.sensor_id}")
            print(f"[StationConfig] Subscrito a sound/config/update/{self.sensor_id}")
            print(f"[StationConfig] Subscrito a sound/control/reboot/{self.sensor_id}")
        else:
            print(f"[ERRO] Falha na conexão MQTT: código {rc}")
            

    def _on_message(self, client, userdata, msg):
        """Callback quando recebe mensagem MQTT"""
        topic_parts = msg.topic.split('/')
        
        if len(topic_parts) < 4:
            return
        
        msg_type = topic_parts[2]  # 'request' ou 'update'
        sensor_id = topic_parts[3]
        
        # Verificar se é para este sensor
        if sensor_id != self.sensor_id:
            return
        
        try:
            payload = json.loads(msg.payload.decode('utf-8'))

            # Reboot command (sound/control/reboot/{sensor_id})
            if topic_parts[1] == 'control' and msg_type == 'reboot':
                print(f"[StationConfig] Comando de reboot recebido")
                self._send_ack('ok', 'Reboot agendado', needs_reboot=True)
                self._schedule_restart(delay=3)
                return

            if msg_type == 'request':
                # Alguém pediu a config atual
                self._handle_config_request(payload)

            elif msg_type == 'update':
                # Recebeu update de configuração
                self._handle_config_update(payload)
                
                
        except json.JSONDecodeError as e:
            print(f"[ERRO] JSON inválido: {e}")
        except Exception as e:
            print(f"[ERRO] Erro ao processar mensagem: {e}")
    
    def _handle_config_request(self, payload):
        """Responde a um pedido de configuração enviando a config atual"""
        print(f"[StationConfig] Config request recebido de {payload.get('requester', 'unknown')}")
        
        # Recarregar config do ficheiro (pode ter sido alterada manualmente)
        self.current_config = self.load_config()
        
        if self.current_config:
            # Enviar config atual
            topic = f"sound/config/response/{self.sensor_id}"
            response_payload = self.current_config
            
            self.client.publish(topic, json.dumps(response_payload), qos=1)
            print(f"[StationConfig] Config enviada via {topic}")
        else:
            print(f"[ERRO] Não foi possível enviar config (ficheiro inválido)")
    
    def _handle_config_update(self, payload):
        """Aplica um update de configuração"""
        print(f"[StationConfig] Config update recebido")
        
        new_config_partial = payload.get('config')
        checksum_received = payload.get('checksum')
        
        if not new_config_partial:
            print(f"[ERRO] Update sem campo 'config'")
            self._send_ack('error', 'Missing config field')
            return
        
        print(f"[StationConfig] A dar merge com config atual")
        print(f"[StationConfig] Campos Recebidos para update:")
        for section in new_config_partial.keys():
            print(f"    - {section}")
            
        #Merging:
        new_config_merged = self.deep_merge(self.current_config, new_config_partial)
        
        # Validar checksum
        config_str = json.dumps(new_config_partial, sort_keys=True)
        checksum_computed = hashlib.sha256(config_str.encode('utf-8')).hexdigest()
        
        if checksum_received and checksum_received != checksum_computed:
            print(f"[ERRO] Checksum mismatch!")
            print(f"  Recebido: {checksum_received}")
            print(f"  Calculado: {checksum_computed}")
            self._send_ack('error', 'Checksum validation failed')
            return

        #needs_reboot = self._check_if_needs_reboot(new_config_merged)
        # Guardar nova config
        if self.save_config(new_config_merged):
            print(f"[StationConfig]  Config aplicada com sucesso")
            
            # Verificar se precisa reboot (flags críticas mudaram)
            #needs_reboot = self._check_if_needs_reboot(new_config)
            
            #if needs_reboot:
            if True:
                print(f"[StationConfig]  Mudanças requerem reinício da aplicação")
                self._send_ack('ok', 'Config updated - restart required', needs_reboot=True)

                self._schedule_restart(delay=5)
            #else:
            if False:
                print(f"[StationConfig] Mudanças aplicadas (sem reinício necessário)")
                self._send_ack('ok', 'Config updated successfully', needs_reboot=False)
        else:
            self._send_ack('error', 'Failed to save config file')
    
    def _check_if_needs_reboot(self, new_config):
        """
        Verifica se mudanças na config requerem reinício da aplicação
        
        Flags críticas (mudanças requerem reboot):
        - audio.sample_rate, audio.channels, audio.chunk_size
        - mqtt.broker, mqtt.port
        - sound_event_detect (modelo de classificação)
        """
        if not self.current_config:
            return True
        
        critical_paths = [
            ['audio', 'sample_rate'],
            ['audio', 'channels'],
            ['audio', 'chunk_size'],
            ['mqtt', 'broker'],
            ['mqtt', 'port'],
            ['sound_event_detect', 'model_path']
        ]
        
        def get_nested(config, path):
            """Acede a valor nested no dict"""
            value = config
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return None
            return value
        
        for path in critical_paths:
            old_value = get_nested(self.current_config, path)
            new_value = get_nested(new_config, path)
            
            if old_value != new_value:
                path_str = '.'.join(path)
                print(f"[StationConfig] Mudança crítica detectada: {path_str} ({old_value} → {new_value})")
                return True
        
        return False
    
    def _send_ack(self, status, message='', needs_reboot=False):
        """Envia ACK para confirmar recepção e aplicação do update"""
        topic = f"sound/config/ack/{self.sensor_id}"
        payload = {
            'status': status,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'sensor_id': self.sensor_id,
            'needs_reboot': needs_reboot
        }
        
        self.client.publish(topic, json.dumps(payload), qos=1)
        print(f"[StationConfig] ACK enviado: {status} - {message}")
    
#    def _schedule_restart(self, delay=5):
#        """
#        Agenda reinício da aplicação após X segundos
#        """
#        import time
#        print(f"[StationConfig] Reinício agendado em {delay} segundos...")
#        
#        def delayed_restart():
#            time.sleep(delay)
#            print(f"[StationConfig] A reiniciar aplicação...")
#            # Opção 1: Reiniciar serviço systemd
#            # subprocess.run(['sudo', 'systemctl', 'restart', 'soundmeter.service'])
#            
#            # Opção 2: Exit e deixar systemd reiniciar automaticamente
#            sys.exit(0)
#        
#        import threading
#        thread = threading.Thread(target=delayed_restart, daemon=True)
#        thread.start()
    def _schedule_restart(self, delay=5):
        import time
        import threading
        import subprocess
        print(f"[StationConfig] Reboot agendado em {delay} segundos...")

        def delayed_restart():
            time.sleep(delay)
            print(f"[StationConfig] ============== A REINICIAR ==============")
            subprocess.run(['sudo', 'reboot', 'now'])
            print(f"[StationConfig] ============== RESTART COMPLETO ===============")
            
          
        thread = threading.Thread(target=delayed_restart, daemon=True)
        thread.start()

    
    def start(self):
        """Inicia o receiver (blocking)"""
        for attempt in range(60):
            try:
                print(f"[StationConfig] A conectar a {self.mqtt_broker}:{self.mqtt_port} (tentativa {attempt+1}/60)...")
                self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
                print(f"[StationConfig] Pronto para receber comandos de configuração")
                self.client.loop_forever()
                return
            except KeyboardInterrupt:
                print(f"\n[StationConfig] Interrompido pelo utilizador")
                self.client.disconnect()
                return
            except Exception as e:
                print(f"[StationConfig] Falhou: {e}. A aguardar 10s...")
                if attempt < 59:
                    time.sleep(10)
        print(f"[StationConfig] Não foi possível conectar após 60 tentativas.")
        sys.exit(1)


def main():
    """Execução standalone via CLI"""
    parser = argparse.ArgumentParser(description='Station Config Receiver - Gestão remota de configurações')
    parser.add_argument('--sensor-id', required=True, help='ID do sensor (ex: 2)')
    parser.add_argument('--config-file', required=True, help='Caminho para config.json')
    parser.add_argument('--broker', default='10.64.137.6', help='MQTT broker (default: 10.64.137.6)')
    parser.add_argument('--port', type=int, default=1884, help='MQTT port (default: 1884)')
    
    args = parser.parse_args()
    
    receiver = StationConfigReceiver(
        sensor_id=args.sensor_id,
        config_file_path=args.config_file,
        mqtt_broker=args.broker,
        mqtt_port=args.port
    )
    
    receiver.start()


if __name__ == '__main__':
    main()
