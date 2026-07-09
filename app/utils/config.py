from pathlib import Path
from app.utils import db

def load_config() -> dict:
    # Игнорируем всю папку config в .gitignore
    gitignore_path = Path("config/.gitignore")
    if not gitignore_path.exists():
        try:
            gitignore_path.parent.mkdir(parents=True, exist_ok=True)
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write("# Игнорировать все файлы настроек и БД в этой папке\n*\n")
        except Exception:
            pass

    # Извлекаем конфигурацию из зашифрованной SQLite
    db_config = db.get_setting("app_config")
    if db_config:
        return db_config

    # Дефолтная конфигурация при первом запуске
    default_config = {
        "app": {"check_interval": 15, "version": "1.2.0"},
        "favorites": {"games": ["Just Chatting", "Разговоры", "Игры", "Retro"]},
        "platforms": {
            "twitch": {"enabled": True, "client_id": "", "client_secret": ""},
            "youtube": {"enabled": True, "client_id": "", "client_secret": ""},
            "livevk": {"enabled": True, "client_id": "", "client_secret": "", "owner_id": ""},
            "kick": {"enabled": True, "channel": "", "token": ""},
            "rutube": {"enabled": True, "channel_id": "", "token": ""},
            "goodgame": {"enabled": True, "channel": "", "client_id": "", "client_secret": ""}
        }
    }

    db.set_setting("app_config", default_config)
    return default_config

def save_config(config_data: dict):
    db.set_setting("app_config", config_data)
