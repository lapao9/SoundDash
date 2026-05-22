import json
from app.config import SYSTEM_CONFIG_FILE


def load_system_config():
    try:
        with open(SYSTEM_CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {"grafana_url": "http://10.64.137.6:3000"}


def save_system_config(config):
    with open(SYSTEM_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
