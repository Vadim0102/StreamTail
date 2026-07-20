import sqlite3
import json
import threading
from app.utils import crypto
from app.utils.paths import get_app_data_dir

# База данных хранится в AppData
DB_PATH = get_app_data_dir() / "streamtail.db"
_settings_cache = {}
_tokens_cache = {}
_db_initialized = False
_db_lock = threading.Lock()  # Блокировка для гарантированной потокобезопасности СУБД


def init_db():
    global _db_initialized
    if _db_initialized:
        return
    with _db_lock:
        if _db_initialized:
            return
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Отключаем check_same_thread для разделения дескрипторов между asyncio-потоками
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()

        # WAL-режим для многопоточного параллельного доступа
        cursor.execute("PRAGMA journal_mode=WAL")

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS settings
                       (
                           key TEXT PRIMARY KEY,
                           value TEXT
                       )
                       """)
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS tokens
                       (
                           platform TEXT PRIMARY KEY,
                           token_data TEXT
                       )
                       """)
        conn.commit()
        conn.close()

        # Чтение кэша настроек
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        for r in cursor.fetchall():
            key, raw_val = r[0], r[1]
            decrypted = crypto.decrypt_text(raw_val)
            if decrypted:
                try:
                    _settings_cache[key] = json.loads(decrypted)
                except Exception:
                    _settings_cache[key] = decrypted
            else:
                try:
                    _settings_cache[key] = json.loads(raw_val)
                except Exception:
                    _settings_cache[key] = raw_val

        # Чтение кэша авторизационных токенов
        cursor.execute("SELECT platform, token_data FROM tokens")
        for r in cursor.fetchall():
            decrypted = crypto.decrypt_text(r[1])
            if decrypted:
                try:
                    _tokens_cache[r[0]] = json.loads(decrypted)
                except Exception:
                    pass
        conn.close()
        _db_initialized = True


def get_setting(key: str, default=None):
    init_db()
    val = _settings_cache.get(key)
    return default if val is None else val


def set_setting(key: str, value):
    init_db()
    _settings_cache[key] = value
    with _db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        val_str = json.dumps(value, ensure_ascii=False)
        encrypted_val = crypto.encrypt_text(val_str)
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, encrypted_val))
        conn.commit()
        conn.close()


def get_token(platform: str) -> dict | None:
    init_db()
    return _tokens_cache.get(platform)


def set_token(platform: str, data: dict):
    init_db()
    _tokens_cache[platform] = data
    with _db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        val_str = json.dumps(data, ensure_ascii=False)
        encrypted_val = crypto.encrypt_text(val_str)
        cursor.execute("INSERT OR REPLACE INTO tokens (platform, token_data) VALUES (?, ?)", (platform, encrypted_val))
        conn.commit()
        conn.close()


def clear_token(platform: str):
    init_db()
    _tokens_cache.pop(platform, None)
    with _db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tokens WHERE platform = ?", (platform,))
        conn.commit()
        conn.close()
