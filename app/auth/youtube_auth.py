"""
YouTube OAuth2 — Authorization Code Flow (Google).

Scopes: youtube.force-ssl (чтение/запись трансляций).
После авторизации автоматически ищется активный/ближайший broadcast_id.
"""
import time
import webbrowser
from urllib.parse import urlencode

import httpx

from app.auth.oauth_server import wait_for_oauth_code
from app.auth.token_store import get_token, set_token
from app.utils.logger import logger

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "http://localhost:19234/callback"
SCOPES = "https://www.googleapis.com/auth/youtube.force-ssl"
PORT = 19234

BROADCASTS_URL = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts"


async def authenticate(client_id: str, client_secret: str) -> bool:
    """
    Открывает браузер с Google OAuth, ждёт callback,
    сохраняет токены и определяет broadcast_id.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",  # Гарантирует получение refresh_token
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    logger.info("YouTube: открываем браузер для авторизации Google...")
    webbrowser.open(url)

    result = await wait_for_oauth_code(port=PORT)
    if not result or not result.get("code"):
        logger.error("YouTube: не удалось получить код авторизации.")
        return False

    return await _exchange_code(client_id, client_secret, result["code"])


async def _exchange_code(client_id: str, client_secret: str, code: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            })
            resp.raise_for_status()
            data = resp.json()

        access_token = data.get("access_token")
        if not access_token:
            logger.error(f"YouTube API не вернул access_token. Ответ: {data}")
            return False

        refresh_token = data.get("refresh_token", "")
        expires_in = data.get("expires_in", 3600)

        # Ищем активный broadcast
        broadcast_id = await _fetch_broadcast_id(access_token)

        from app.auth.token_store import set_token # Локальный импорт
        set_token("youtube", {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": int(time.time()) + expires_in,
            "broadcast_id": broadcast_id,
            "client_id": client_id,
            "client_secret": client_secret,
        })
        logger.info(f"YouTube: авторизован! broadcast_id={broadcast_id or '(не найден)'}")
        return True

    except httpx.HTTPStatusError as e:
        logger.error(f"YouTube: ошибка авторизации (HTTP {e.response.status_code}): {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"YouTube: ошибка обмена кода: {e}")
        return False


async def _fetch_broadcast_id(access_token: str) -> str:
    """
    Ищет активную или ближайшую трансляцию.
    Порядок: live → upcoming → все.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    for status in ("active", "upcoming", "all"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    BROADCASTS_URL,
                    params={
                        "part": "id,snippet",
                        "broadcastStatus": status,
                        "broadcastType": "all",
                        "maxResults": 1,
                    },
                    headers=headers,
                )
                data = resp.json()
                items = data.get("items", [])
                if items:
                    bid = items[0]["id"]
                    logger.debug(f"YouTube: найден broadcast_id={bid} (status={status})")
                    return bid
        except Exception as e:
            logger.error(f"YouTube: ошибка поиска broadcast: {e}")
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

        existing = get_token("youtube") or {}
        set_token("youtube", {
            **existing,
            "access_token": data["access_token"],
            # Google редко даёт новый refresh_token — оставляем старый
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": int(time.time()) + data.get("expires_in", 3600),
        })
        logger.info("YouTube: токен успешно обновлён (refresh).")
        return True
    except Exception as e:
        logger.error(f"YouTube: ошибка обновления токена: {e}")
        return False
