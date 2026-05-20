# publisher.py
import paho.mqtt.client as mqtt
import time

# Configurações do broker
broker = "localhost"  # ou usa localhost se for local
port = 1884
topic = "teste/mensagem"
mensagem = "Olá, MQTT!"

# Cria o cliente MQTT
client = mqtt.Client()

# Conecta ao broker e publica
client.connect(broker, port, 60)
client.publish(topic, mensagem)

print(f"Mensagem publicada: '{mensagem}' no tópico '{topic}'")

client.disconnect()