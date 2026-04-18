import yaml
import os
from pathlib import Path

def load_config(path: str = "config/app.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        # Возвращаем базовую структуру, если конфига нет
        return {
            "app": {"check_interval": 30, "version": "1.1.0"},
            "favorites": {"games": ["Just Chatting"]},
            "platforms": {}
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
