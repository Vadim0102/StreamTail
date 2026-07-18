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

def get_asset_path(filename: str) -> Path:
    """
    Возвращает путь к статическому файлу из папки assets.
    Совместим как с обычным запуском, так и с упакованным (Nuitka/standalone/onefile).
    """
    # __file__ находится в app/utils/paths.py, поэтому корень проекта на 2 уровня выше.
    base_dir = Path(__file__).resolve().parent.parent.parent
    asset_path = base_dir / "assets" / filename

    if not asset_path.exists():
        # Резервный вариант поиска относительно текущей рабочей директории
        fallback_path = Path(os.getcwd()) / "assets" / filename
        if fallback_path.exists():
            return fallback_path

    return asset_path
