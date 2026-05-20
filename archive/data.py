import json
import time
import paho.mqtt.client as mqtt
import sys
from datetime import datetime, timezone

BROKER = "172.17.0.2"
PORT = 1883
TOPIC = "sensors/data"

client = mqtt.Client()
client.connect(BROKER, PORT, 60)

def send_data(sensor_id, json_file):
    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    for item in data:
        dt = datetime.utcfromtimestamp(item["TimeStamp"])
        message = {
            "measurement": "sound_level",
            "tags": {
                "sensor": "acoustic"
            },
            "sensor_id": str(sensor_id),
            "LAEA": float(item["LAEA"]),
            "LCpeak": float(item["LCpeak"]),
            "LCpeakT": float(item["LCpeakT"]),
            "LAFmax": float(item["LAFmax"]),
            "LAFmaxT": float(item["LAFmaxT"]),
            "LAFmin": float(item["LAFmin"]),
            "LAFminT": float(item["LAFminT"]),
            "LAeq": float(item["LAeq"]),
            "BT25": float(item["BT25"]),
            "BT31_5": float(item["BT31_5"]),
            "BT40": float(item["BT40"]),
            "BT50": float(item["BT50"]),
            "BT63": float(item["BT63"]),
            "BT80": float(item["BT80"]),
            "BT100": float(item["BT100"]),
            "BT125": float(item["BT125"]),
            "BT160": float(item["BT160"]),
            "BT200": float(item["BT200"]),
            "BT250": float(item["BT250"]),
            "BT315": float(item["BT315"]),
            "BT400": float(item["BT400"]),
            "BT500": float(item["BT500"]),
            "BT630": float(item["BT630"]),
            "BT800": float(item["BT800"]),
            "BT1000": float(item["BT1000"]),
            "BT1250": float(item["BT1250"]),
            "BT1600": float(item["BT1600"]),
            "BT2000": float(item["BT2000"]),
            "BT2500": float(item["BT2500"]),
            "BT3150": float(item["BT3150"]),
            "BT4000": float(item["BT4000"]),
            "BT5000": float(item["BT5000"]),
            "BT6300": float(item["BT6300"]),
            "BT8000": float(item["BT8000"]),
            "BT10000": float(item["BT10000"]),
            "BT12500": float(item["BT12500"]),
            "BT16000": float(item["BT16000"]),
            "BT20000": float(item["BT20000"]),
            "LAEA_SLOW_EVENT":float(item["LAEA_SLOW_EVENT"]),
            "EventDetect":float(item["EventDetect"]),
            "EventType1":float(item["EventType1"]),
            "EventType2":float(item["EventType2"]),
            "EventType3":float(item["EventType3"]),
            "EventType4":float(item["EventType4"]),
            "EventType5":float(item["EventType5"]),
            "EventType6":float(item["EventType6"]),
            "EventType7":float(item["EventType7"]),
            "EventType8":float(item["EventType8"]),
            "EventType9":float(item["EventType9"]),
            "EventType10":float(item["EventType10"]),
            "timestamp": datetime.fromtimestamp(item["TimeStamp"], tz=timezone.utc).isoformat()
        }

        try:
            print(message)
            message_json = json.dumps(message)
            client.publish(TOPIC, message_json)
        except Exception as e:
            print(f"Error creating JSON: {e}")

        time.sleep(0.1)

    client.disconnect()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python script.py <sensor_id> <ficheiro_json>")
        sys.exit(1)

    sensor_id = sys.argv[1]
    json_file = sys.argv[2]
    send_data(sensor_id, json_file)