import yaml
import os

def load_config(path="config/app.yaml"):
    if not os.path.exists(path):
        return {"app": {"check_interval": 30}, "favorites": {"games": []}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
