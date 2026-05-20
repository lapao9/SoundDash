import csv
import json
import time
import paho.mqtt.client as mqtt
import sys

def convert_types(row):
    new_row = {}

    for key, value in row.items():
        if value == "" or value is None:
            continue

        try:
            new_row[key] = float(value)
        except:
            new_row[key] = value

    return new_row


def csv_to_json(file_path, sensor_name, mqtt_broker, mqtt_topic):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(mqtt_broker, 1884, 60)  

    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)

        for row in reader:
            data = convert_types(row)

            if "TimeStamp" in data:
                data["timestamp"] = float(data["TimeStamp"])
                data["time"] = int(float(data["TimeStamp"]) * 1000)  # ms
                del data["TimeStamp"]

            # adicionar sensor
            data["sensor_name"] = sensor_name

            json_data = json.dumps(data)

            print(json_data)
            client.publish(mqtt_topic, json_data)

            time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python CSVtoJSON_MQTT.py <csv> <sensor>")
        sys.exit(1)

    file_path = sys.argv[1]
    sensor_name = sys.argv[2]

    mqtt_broker = "10.64.137.6"
    mqtt_topic = "sound/levels"

    csv_to_json(file_path, sensor_name, mqtt_broker, mqtt_topic)
