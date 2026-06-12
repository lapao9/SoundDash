import os

# InfluxDB
INFLUXDB_URL   = "http://10.64.137.6:8086"
INFLUXDB_TOKEN = "LvrSeU4NaBeQN7c4S4LsJCmlflUIQDgwRJqm383tdMoQaoDkM6pHAB022sAURdkvsSG_SWGXp8FVKVciviD3iA=="
INFLUXDB_ORG   = "ISEL"
INFLUXDB_BUCKET = "SoundDashHosp"

# MQTT
MQTT_BROKER = "10.64.137.6"
MQTT_PORT   = 1881
MQTT_CONFIG_PORT = 1884

# Ficheiros de dados (caminhos relativos ao webApp/)
SYSTEM_CONFIG_FILE   = "system_config.json"
USERS_FILE           = "users.json"
CLASS_LABELS_FILE    = "class_labels_indices.csv"

# Flask
SECRET_KEY = "uma_chave_muito_secreta"
