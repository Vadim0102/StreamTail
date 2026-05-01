"""
VK Video Live OAuth2 — Implicit Flow (Без обмена кода).
"""
import time
import webbrowser
from urllib.parse import urlencode

from app.auth.oauth_server import wait_for_oauth_code
from app.auth.token_store import set_token
from app.utils.logger import logger

REDIRECT_URI = "http://localhost:19234/callback"
SCOPES = "channel:stream:settings"
PORT = 19234


async def authenticate(client_id: str, client_secret: str) -> bool:
    auth_url = "https://auth.live.vkvideo.ru/app/oauth2/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "token",  # ИСПОЛЬЗУЕМ IMPLICIT FLOW!
        "scope": SCOPES,
    }
    url = f"{auth_url}?{urlencode(params)}"
    logger.info("VK Live: открываем браузер для авторизации...")
    webbrowser.open(url)

    result = await wait_for_oauth_code(port=PORT)
    if not result:
        logger.error("VK Live: не удалось получить данные авторизации.")
        return False

    # В Implicit Flow платформа отдает токен сразу в URL браузера
    if result.get("access_token"):
        set_token("livevk", {
            "access_token": result["access_token"],
            "refresh_token": "",  # VK не выдает refresh_token при Implicit Flow
            "expires_at": int(time.time()) + result["expires_in"] if result["expires_in"] else 0,
            "client_id": client_id,
            "client_secret": client_secret,
        })
        logger.info("✅ VK Live: Авторизация успешна (токен получен напрямую)!")
        return True

    logger.error("VK Live: платформа не вернула токен.")
    return False

async def refresh(client_id: str, client_secret: str, refresh_token: str) -> bool:
    # Implicit Flow не поддерживает обновление токена, нужно будет нажать "Авторизоваться" еще раз
    return False
