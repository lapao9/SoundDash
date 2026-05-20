import csv
import json
import time

# Input and output file paths
csv_file = 'Levels_20250607_030326.csv'
json_file = 'ficheiro4_updated.json'

# Read CSV and convert to JSON
json_array = []

with open(csv_file, mode='r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    
    for row in reader:
        # Create JSON object with the required structure
        json_obj = {
            "TimeStamp": float(row.get("TimeStamp",0)),
            "LAEA": float(row.get("LAEA", 0)),
            "LCpeak": float(row.get("LCpeak", 0)),
            "LCpeakT": float(row.get("LCpeakT", 0)),
            "LAFmax": float(row.get("LAFmax", 0)),
            "LAFmaxT": float(row.get("LAFmaxT", 0)),
            "LAFmin": float(row.get("LAFmin", 0)),
            "LAFminT": float(row.get("LAFminT", 0)),
            "LAeq": float(row.get("LAeq", 0)),
            "BT25": float(row.get("BT25",0)),
            "BT31_5":float(row.get("BT31_5",0)),
            "BT40":float(row.get("BT40",0)),
            "BT50":float(row.get("BT50",0)),
            "BT63":float(row.get("BT63",0)),
            "BT80":float(row.get("BT80",0)),
            "BT100":float(row.get("BT100",0)),
            "BT125":float(row.get("BT125",0)),
            "BT160":float(row.get("BT160",0)),
            "BT200":float(row.get("BT200",0)),
            "BT250":float(row.get("BT250",0)),
            "BT315":float(row.get("BT315",0)),
            "BT400":float(row.get("BT400",0)),
            "BT500":float(row.get("BT500",0)),
            "BT630":float(row.get("BT630",0)),
            "BT800":float(row.get("BT800",0)),
            "BT1000":float(row.get("BT1000",0)),
            "BT1250":float(row.get("BT1250",0)),
            "BT1600":float(row.get("BT1600",0)),
            "BT2000":float(row.get("BT2000",0)),
            "BT2500":float(row.get("BT2500",0)),
            "BT3150":float(row.get("BT3150",0)),
            "BT4000":float(row.get("BT4000",0)),
            "BT5000":float(row.get("BT5000",0)),
            "BT6300":float(row.get("BT6300",0)),
            "BT8000":float(row.get("BT8000",0)),
            "BT10000":float(row.get("BT10000",0)),
            "BT12500":float(row.get("BT12500",0)),
            "BT16000":float(row.get("BT16000",0)),
            "BT20000":float(row.get("BT20000",0)),
            "LAEA_SLOW_EVENT":float(row.get("LAEA_SLOW_EVENT",0)),
            "EventDetect":float(row.get("EventDetect",0)),
            "EventType1":float(row.get("EventType1",0)),
            "EventType2":float(row.get("EventType2",0)),
            "EventType3":float(row.get("EventType3",0)),
            "EventType4":float(row.get("EventType4",0)),
            "EventType5":float(row.get("EventType5",0)),
            "EventType6":float(row.get("EventType6",0)),
            "EventType7":float(row.get("EventType7",0)),
            "EventType8":float(row.get("EventType8",0)),
            "EventType9":float(row.get("EventType9",0)),
            "EventType10":float(row.get("EventType10",0))
        }
        json_array.append(json_obj)

# Write to JSON file
with open(json_file, mode='w', encoding='utf-8') as f:
    json.dump(json_array, f, indent=2)

print(f"Conversion complete. JSON saved to {json_file}")