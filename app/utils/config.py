import yaml
import os
from pathlib import Path


def load_config(path: str = "config/app.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        # Если файла нет, создаем дефолтный конфиг
        default_config = {
            "app": {"check_interval": 15, "version": "1.1.0"},
            "favorites": {"games": ["Just Chatting"]},
            "platforms": {}
        }
        os.makedirs(config_path.parent, exist_ok=True)
        save_config(default_config, path)
        return default_config

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(config_data: dict, path: str = "config/app.yaml"):
    """Сохраняет изменения обратно в YAML файл."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f, allow_unicode=True, default_flow_style=False)
