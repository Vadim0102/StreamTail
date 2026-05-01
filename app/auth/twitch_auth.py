"""
Twitch OAuth2 — Authorization Code Flow.

Scopes: channel:manage:broadcast, user:read:email
После успешной авторизации автоматически определяется broadcaster_id.
"""
import time
import webbrowser
from urllib.parse import urlencode

import httpx

from app.auth.oauth_server import wait_for_oauth_code
from app.auth.token_store import get_token, set_token
from app.utils.logger import logger

AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
REVOKE_URL = "https://id.twitch.tv/oauth2/revoke"
USERS_URL = "https://api.twitch.tv/helix/users"
REDIRECT_URI = "http://localhost:19234/callback"
SCOPES = "channel:manage:broadcast user:read:email"
PORT = 19234


async def authenticate(client_id: str, client_secret: str) -> bool:
    """
    Открывает браузер, ждёт callback, получает access+refresh токен.
    Сохраняет токен и broadcaster_id в TokenStore.
    Возвращает True при успехе.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "force_verify": "true",
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    logger.info(f"Twitch: открываем браузер для авторизации...")
    webbrowser.open(url)

    result = await wait_for_oauth_code(port=PORT)
    if not result or not result.get("code"):
        logger.error("Twitch: не удалось получить код авторизации.")
        return False

    return await _exchange_code(client_id, client_secret, result["code"])


async def _exchange_code(client_id: str, client_secret: str, code: str) -> bool:
    """Обменивает code на access_token + refresh_token."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            })

            # Если Twitch вернул ошибку, выбрасываем исключение
            resp.raise_for_status()
            data = resp.json()

        access_token = data.get("access_token")
        if not access_token:
            logger.error(f"Twitch API не вернул access_token. Ответ: {data}")
            return False

        refresh_token = data.get("refresh_token", "")
        expires_in = data.get("expires_in", 3600)

        # Определяем broadcaster_id
        broadcaster_id = await _fetch_broadcaster_id(client_id, access_token)

        from app.auth.token_store import set_token  # Локальный импорт для верности
        set_token("twitch", {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": int(time.time()) + expires_in,
            "broadcaster_id": broadcaster_id,
            "client_id": client_id,
            "client_secret": client_secret,
        })
        logger.info(f"Twitch: авторизован! broadcaster_id={broadcaster_id}")
        return True

    except httpx.HTTPStatusError as e:
        logger.error(f"Twitch: ошибка авторизации (HTTP {e.response.status_code}): {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Twitch: непредвиденная ошибка обмена кода: {e}")
        return False


async def _fetch_broadcaster_id(client_id: str, access_token: str) -> str:
    """Получает ID пользователя через /helix/users."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(USERS_URL, headers={
                "Client-Id": client_id,
                "Authorization": f"Bearer {access_token}",
            })
            data = resp.json()
            if data.get("data"):
                return data["data"][0]["id"]
    except Exception as e:
        logger.error(f"Twitch: не удалось получить broadcaster_id: {e}")
    return ""


async def refresh(client_id: str, client_secret: str, refresh_token: str) -> bool:
    """Обновляет access_token через refresh_token."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            })
            resp.raise_for_status()
            data = resp.json()

        existing = get_token("twitch") or {}
        set_token("twitch", {
            **existing,
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": int(time.time()) + data.get("expires_in", 3600),
        })
        logger.info("Twitch: токен успешно обновлён (refresh).")
        return True
    except Exception as e:
        logger.error(f"Twitch: ошибка обновления токена: {e}")
        return False
