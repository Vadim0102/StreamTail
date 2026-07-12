import sqlite3
import json
from pathlib import Path
from app.utils import crypto

DB_PATH = Path("config/streamtail.db")
_settings_cache = {}
_tokens_cache = {}
_db_initialized = False


def init_db():
    global _db_initialized
    if _db_initialized:
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Включаем WAL-режим для ускорения работы СУБД в многопоточной среде
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

    # Предварительное кэширование настроек
    conn = sqlite3.connect(DB_PATH)
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
            # Предотвращение сохранения сырой Base64-строки при сбое дешифрования (например, изменение Hardware ID)
            try:
                _settings_cache[key] = json.loads(raw_val)
            except Exception:
                if len(raw_val) > 16 and (raw_val.endswith("==") or not (raw_val.startswith("{") or raw_val.startswith("["))):
                    # Если строка похожа на шифрованный Base64, но расшифровать её не вышло — игнорируем
                    _settings_cache[key] = None
                else:
                    _settings_cache[key] = raw_val

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
    return _settings_cache.get(key, default)


def set_setting(key: str, value):
    init_db()
    _settings_cache[key] = value
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    val_str = json.dumps(data, ensure_ascii=False)
    encrypted_val = crypto.encrypt_text(val_str)
    cursor.execute("INSERT OR REPLACE INTO tokens (platform, token_data) VALUES (?, ?)", (platform, encrypted_val))
    conn.commit()
    conn.close()


def clear_token(platform: str):
    init_db()
    _tokens_cache.pop(platform, None)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tokens WHERE platform = ?", (platform,))
    conn.commit()
    conn.close()
