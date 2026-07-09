"""
Хранилище OAuth-токенов на базе SQLite.
"""
import time
from typing import Optional
from app.utils import db
from app.utils.logger import logger

def get_token(platform: str) -> Optional[dict]:
    return db.get_token(platform)

def set_token(platform: str, data: dict):
    db.set_token(platform, data)
    logger.debug(f"TokenStore: токен для '{platform}' сохранён в БД.")

def clear_token(platform: str):
    db.clear_token(platform)

def is_token_valid(platform: str, buffer_seconds: int = 300) -> bool:
    token_data = get_token(platform)
    if not token_data or not token_data.get("access_token"):
        return False
    expires_at = token_data.get("expires_at", 0)
    if expires_at == 0:
        return True
    return time.time() < expires_at - buffer_seconds
