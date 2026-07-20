import time
import secrets
import webbrowser
from urllib.parse import urlencode
import httpx
from app.auth.oauth_server import wait_for_oauth_code
from app.auth.token_store import set_token
from app.utils.logger import logger

AUTH_URL = "https://goodgame.ru/oauth2/authorize"
TOKEN_URL = "https://goodgame.ru/oauth2/token"
REDIRECT_URI = "http://localhost:19234/callback"
PORT = 19234

async def authenticate(client_id: str, client_secret: str) -> bool:
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    logger.info("GoodGame: открываем браузер для авторизации...")
    webbrowser.open(url)

    result = await wait_for_oauth_code(port=PORT)
    if not result or not result.get("code"):
        logger.error("GoodGame: не удалось получить код авторизации.")
        return False

    # Защита от CSRF-атак
    if result.get("state") != state:
        logger.error("GoodGame: Ошибка безопасности OAuth: параметр state не совпадает.")
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": result["code"],
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            })
            resp.raise_for_status()
            data = resp.json()

        access_token = data.get("access_token")
        if not access_token:
            logger.error(f"GoodGame API не вернул access_token. Ответ: {data}")
            return False

        expires_in = data.get("expires_in", 3600)
        set_token("goodgame", {
            "access_token": access_token,
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": int(time.time()) + expires_in,
            "client_id": client_id,
            "client_secret": client_secret,
        })
        logger.info("GoodGame: Авторизован успешно!")
        return True
    except Exception as e:
        logger.error(f"GoodGame: ошибка обмена кода: {e}")
        return False


async def refresh(client_id: str, client_secret: str, refresh_token: str) -> bool:
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

        from app.auth.token_store import get_token, set_token
        existing = get_token("goodgame") or {}
        set_token("goodgame", {
            **existing,
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": int(time.time()) + data.get("expires_in", 3600),
        })
        logger.info("GoodGame: токен успешно обновлён (refresh).")
        return True
    except Exception as e:
        logger.error(f"GoodGame: ошибка автоматического обновления токена: {e!r}")
        return False
