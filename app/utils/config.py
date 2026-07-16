from app.utils import db

def load_config() -> dict:
    # Извлекаем конфигурацию из зашифрованной SQLite
    db_config = db.get_setting("app_config")
    if db_config:
        return db_config

    # Дефолтная конфигурация при первом запуске
    default_config = {
        "app": {"check_interval": 15, "version": "2.3.1"},  # VERSION
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
