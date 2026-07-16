import os
import sys
from pathlib import Path


def get_app_data_dir() -> Path:
    """
    Возвращает путь к директории хранения настроек, БД и логов в пользовательской папке.
    - Windows: %APPDATA%/StreamTail (обычно C:/Users/Имя/AppData/Roaming/StreamTail)
    - macOS: ~/Library/Application Support/StreamTail
    - Linux: ~/.config/StreamTail или по стандарту XDG
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")

    path = Path(base) / "StreamTail"
    path.mkdir(parents=True, exist_ok=True)
    return path
