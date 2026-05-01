"""
Хранилище OAuth-токенов.
Токены сохраняются в config/tokens.json.
"""
import json
import time
from pathlib import Path
from typing import Optional

from app.utils.logger import logger

TOKENS_PATH = Path("config/tokens.json")
_cache = None  # КЭШ В ПАМЯТИ (исправляет лаги интерфейса)


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache  # Возвращаем из быстрой памяти!

    if TOKENS_PATH.exists():
        try:
            with open(TOKENS_PATH, "r", encoding="utf-8") as f:
                _cache = json.load(f)
                return _cache
        except Exception as e:
            logger.warning(f"TokenStore: не удалось прочитать tokens.json: {e}")

    _cache = {}
    return _cache


def _save(data: dict):
    global _cache
    _cache = data  # Обновляем кэш

    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_token(platform: str) -> Optional[dict]:
    """Возвращает словарь токена для платформы или None."""
    return _load().get(platform)


def set_token(platform: str, data: dict):
    """Сохраняет токен для платформы."""
    all_tokens = _load()
    all_tokens[platform] = data
    _save(all_tokens)
    logger.debug(f"TokenStore: токен для '{platform}' сохранён.")


def clear_token(platform: str):
    """Удаляет токен платформы."""
    all_tokens = _load()
    all_tokens.pop(platform, None)
    _save(all_tokens)


def is_token_valid(platform: str, buffer_seconds: int = 300) -> bool:
    """
    Проверяет, действителен ли токен.
    buffer_seconds — запас перед истечением (по умолчанию 5 минут).
    """
    token_data = get_token(platform)
    if not token_data or not token_data.get("access_token"):
        return False
    expires_at = token_data.get("expires_at", 0)
    # Если expires_at == 0 — токен бессрочный (например VK без refresh_token)
    if expires_at == 0:
        return True
    return time.time() < expires_at - buffer_seconds
