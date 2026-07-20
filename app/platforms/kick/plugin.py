import httpx
import urllib.parse
from app.plugins.base import BasePlugin
from app.utils.logger import logger
from app.utils import token_parser
from app.utils import http_client


class KickPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.client_id = self.config.get("client_id", "").strip()
        self.client_secret = self.config.get("client_secret", "").strip()

        self._BASE = "https://kick.com/api/v1"
        self._BASE_V2 = "https://kick.com/api/v2"
        self._app_token = ""

    @property
    def token_data(self) -> dict:
        from app.auth.token_store import get_token
        return get_token("kick") or {}

    @property
    def token(self) -> str:
        raw_token = self.token_data.get("access_token") or self.config.get("token", "").strip()
        return token_parser.parse_any_cookie_format(raw_token)

    @property
    def is_unofficial(self) -> bool:
        """Определяет, куки это или стандартный OAuth-токен."""
        return token_parser.is_cookie_format(self.token)

    @property
    def channel_slug(self) -> str:
        raw = self.config.get("channel", "").strip()
        if not raw:
            return ""
        if "/" in raw:
            return raw.rstrip("/").split("/")[-1]
        return raw

    @property
    def headers(self) -> dict:
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://kick.com/",
            "Origin": "https://kick.com"
        }

        active_token = self.token
        if active_token:
            if self.is_unofficial:
                headers["Cookie"] = active_token
                # Извлекаем и декодируем защитный XSRF-TOKEN из куки
                xsrf = token_parser.extract_cookie(active_token, "XSRF-TOKEN")
                if xsrf:
                    headers["X-XSRF-TOKEN"] = xsrf
            else:
                headers["Authorization"] = f"Bearer {active_token}"

        return headers

    async def _ensure_app_token_valid(self) -> str:
        """Получает App Access Token (Client Credentials) в память для чтения статуса."""
        if self._app_token:
            return self._app_token

        if self.client_id and self.client_secret:
            try:
                async with http_client.create_client(timeout=10) as client:
                    resp = await client.post("https://id.kick.com/oauth/token", data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    })
                    if resp.status_code == 200:
                        data = resp.json()
                        self._app_token = data["access_token"]
                        logger.info("Kick: Успешно получен фоновый App Access Token для чтения статуса.")
                        return self._app_token
            except Exception as e:
                logger.debug(f"Kick: Не удалось получить фоновый App Token: {e!r}")
        return ""

    async def _ensure_user_token_valid(self) -> bool:
        if self.is_unofficial:
            return True

        from app.auth.token_store import is_token_valid
        if is_token_valid("kick") and self.token:
            return True

        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id") or self.client_id
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import kick_auth
            logger.info("Kick: Токен пользователя истек. Попытка автоматического обновления...")
            success = await kick_auth.refresh(c_id, c_sec, r_token)
            if success:
                return True
        return False

    # ── Чтение статуса ────────────────────────────────────────────────────────

    async def get_status(self) -> dict:
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        slug = self.channel_slug
        if not slug:
            return status

        await self._ensure_user_token_valid()

        active_token = self.token
        is_official = active_token and not self.is_unofficial

        if not active_token:
            app_tok = await self._ensure_app_token_valid()
            if app_tok:
                active_token = app_tok
                is_official = True

        # Метод 1: Официальный API (Без Cloudflare)
        if active_token and is_official:
            try:
                async with http_client.create_client(timeout=10) as client:
                    resp = await client.get(
                        f"https://api.kick.com/public/v1/channels?slug={slug}",
                        headers={"Authorization": f"Bearer {active_token}", "Accept": "application/json"}
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        if data:
                            ch_data = data[0]
                            stream_data = ch_data.get("stream")
                            is_live = False
                            if stream_data:
                                is_live = stream_data.get("is_live", False)

                            title = ""
                            game = ""
                            viewers = 0

                            if is_live and stream_data:
                                title = stream_data.get("title") or ""
                                viewers = stream_data.get("viewer_count") or 0
                                if stream_data.get("category"):
                                    game = stream_data.get("category", {}).get("name") or ""

                            # Fallback на оффлайн метаданные
                            if not title:
                                title = ch_data.get("stream_title") or ch_data.get("title") or ""
                            if not game:
                                root_cat = ch_data.get("category") or {}
                                game = root_cat.get("name") if isinstance(root_cat, dict) else ""

                            status.update({
                                "is_live": is_live,
                                "viewers": viewers,
                                "title": str(title).strip(),
                                "game": str(game).strip()
                            })
                            return status
            except Exception as e:
                logger.debug(f"Kick (Официальный API): Ошибка get_status: {e!r}")

        # Метод 2: Резервный публичный метод
        try:
            async with http_client.create_client(timeout=10) as client:
                resp = await client.get(
                    f"{self._BASE}/channels/{slug}",
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    livestream = data.get("livestream")

                    if livestream:
                        status.update(
                            {
                                "is_live": True,
                                "viewers": livestream.get("viewer_count", 0),
                                "title": livestream.get("session_title", "") or "",
                                "game": (
                                    livestream.get("categories", [{}])[0].get("name", "")
                                    if livestream.get("categories")
                                    else ""
                                ),
                            }
                        )
                    else:
                        status["is_live"] = False
                        status["title"] = data.get("channel", {}).get("description") or ""
                else:
                    logger.debug(f"Kick API: {resp.status_code} для канала {slug} (Cloudflare Protection)")
        except Exception as e:
            logger.debug(f"Kick: ошибка get_status: {e!r}")

        return status

    # ── Запись ────────────────────────────────────────────────────────────────

    async def set_title(self, title: str) -> str:
        await self._ensure_user_token_valid()
        if not self.token:
            return "Kick: Токен пользователя не задан — смена названия недоступна"
        slug = self.channel_slug

        # Официальный метод (api.kick.com)
        if not self.is_unofficial:
            try:
                async with http_client.create_client(timeout=10) as client:
                    resp = await client.patch(
                        "https://api.kick.com/public/v1/channels",
                        headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                        json={"stream_title": title}
                    )
                    if resp.status_code in (200, 204):
                        return "Kick: Название обновлено (Official API)"
                    return f"Kick API Ошибка ({resp.status_code}): {resp.text[:150]}"
            except Exception as e:
                return f"Kick API: ошибка запроса — {e!r}"

        # Неофициальный метод (Cookies)
        try:
            async with http_client.create_client(timeout=10) as client:
                resp = await client.put(
                    f"{self._BASE_V2}/channels/{slug}",
                    headers=self.headers,
                    json={"stream_title": title},
                )
                if resp.status_code in (200, 204):
                    return "Kick: Название обновлено (Cookies API)"
                return f"Kick Ошибка ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            return f"Kick: Ошибка соединения — {e!r}"

    async def set_game(self, game: str) -> str:
        await self._ensure_user_token_valid()
        if not self.token:
            return "Kick: Токен пользователя не задан — смена категории недоступна"

        category_id = await self._find_category_id(game)
        if not category_id:
            return f"Kick: категория «{game}» не найдена"

        slug = self.channel_slug

        # Официальный метод
        if not self.is_unofficial:
            try:
                async with http_client.create_client(timeout=10) as client:
                    resp = await client.patch(
                        "https://api.kick.com/public/v1/channels",
                        headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                        json={"category_id": int(category_id)}
                    )
                    if resp.status_code in (200, 204):
                        return f"Kick: Категория изменена на «{game}»"
                    return f"Kick Ошибка ({resp.status_code}): {resp.text[:150]}"
            except Exception as e:
                return f"Kick: ошибка — {e!r}"

        # Неофициальный метод
        try:
            async with http_client.create_client(timeout=10) as client:
                resp = await client.put(
                    f"{self._BASE_V2}/channels/{slug}",
                    headers=self.headers,
                    json={"category_id": int(category_id)},
                )
                if resp.status_code in (200, 204):
                    return f"Kick: Категория изменена на «{game}»"
                return f"Kick Ошибка ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            return f"Kick: ошибка сетевая — {e!r}"

    async def _find_category_id(self, game: str) -> int | None:
        active_token = self.token
        if not active_token:
            active_token = await self._ensure_app_token_valid()

        if active_token and not self.is_unofficial:
            try:
                async with http_client.create_client(timeout=10) as client:
                    resp = await client.get(
                        "https://api.kick.com/public/v2/categories",
                        params={"name": game},
                        headers={"Authorization": f"Bearer {active_token}", "Accept": "application/json"}
                    )
                    if resp.status_code == 200:
                        items = resp.json().get("data", [])
                        if items:
                            return items[0].get("id")
            except Exception as e:
                logger.debug(f"Kick (Официальный поиск категорий): Ошибка: {e!r}")

        try:
            async with http_client.create_client(timeout=10) as client:
                resp = await client.get(
                    f"{self._BASE}/categories",
                    params={"name": game},
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list) and items:
                        return items[0].get("id")
        except Exception as e:
            logger.debug(f"Kick (Публичный поиск категорий): ошибка: {e!r}")

        return None
