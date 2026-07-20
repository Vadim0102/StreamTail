import secrets
import hashlib
import base64
import time
import webbrowser
from urllib.parse import urlencode
import httpx

from app.auth.oauth_server import wait_for_oauth_code
from app.auth.token_store import set_token
from app.utils.logger import logger

AUTH_URL = "https://id.kick.com/oauth/authorize"
TOKEN_URL = "https://id.kick.com/oauth/token"
REDIRECT_URI = "http://localhost:19234/callback"
PORT = 19234
SCOPES = "user:read channel:read channel:write"


def _generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    sha256_hash = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8').rstrip('=')
    return verifier, challenge


async def authenticate(client_id: str, client_secret: str) -> bool:
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(16)

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256"
    }

    url = f"{AUTH_URL}?{urlencode(params)}"
    logger.info("Kick: открываем браузер для авторизации...")
    webbrowser.open(url)

    result = await wait_for_oauth_code(port=PORT)
    if not result or not result.get("code"):
        logger.error("Kick: не удалось получить код авторизации.")
        return False

    # Защита от CSRF-атак
    if result.get("state") != state:
        logger.error("Kick: Ошибка безопасности OAuth: параметр state не совпадает.")
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URL, data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
                "code": result["code"]
            })

            resp.raise_for_status()
            data = resp.json()

        access_token = data.get("access_token")
        if not access_token:
            logger.error(f"Kick API не вернул access_token. Ответ: {data}")
            return False

        expires_in = data.get("expires_in", 3600)
        set_token("kick", {
            "access_token": access_token,
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": int(time.time()) + expires_in,
            "client_id": client_id,
            "client_secret": client_secret,
        })

        logger.info("Kick: Успешно получен официальный токен пользователя!")
        return True

    except Exception as e:
        logger.error(f"Kick: Ошибка обмена кода авторизации: {e!r}")
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
        existing = get_token("kick") or {}
        set_token("kick", {
            **existing,
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": int(time.time()) + data.get("expires_in", 3600),
        })
        logger.info("Kick: токен пользователя успешно обновлён (refresh).")
        return True
    except Exception as e:
        logger.error(f"Kick: ошибка обновления токена пользователя: {e!r}")
        return False
