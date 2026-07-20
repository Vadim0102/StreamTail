import json
import httpx
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token
from app.utils import token_parser
from app.utils.logger import logger
from app.utils import http_client


class LiveVKPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.api_base = "https://api.live.vkvideo.ru/v1"

    @property
    def token_data(self):
        return get_token("livevk") or {}

    @property
    def token(self):
        config_token = self.config.get("token", "").strip()
        if config_token:
            parsed = token_parser.parse_local_storage(config_token, "accessToken")
            if parsed:
                return parsed
            return config_token
        return self.token_data.get("access_token") or ""

    @property
    def client_id(self):
        """Возвращает Client ID или официальный ID сайта VK Live по умолчанию."""
        config_token = self.config.get("token", "").strip()
        parsed_cid = token_parser.parse_local_storage(config_token, "clientId")
        if parsed_cid:
            return parsed_cid

        config_cid = self.config.get("client_id", "").strip()
        if config_cid:
            return config_cid

        db_cid = self.token_data.get("client_id")
        if db_cid:
            return db_cid

        return "vkplay.live"

    @property
    def owner_id(self) -> str:
        """Нормализует Owner ID: выделяет имя канала, даже если пользователь вставил полную ссылку."""
        raw = self.config.get("owner_id", "").strip()
        if not raw:
            return ""
        if "/" in raw:
            return raw.rstrip("/").split("/")[-1]
        return raw

    @property
    def headers(self):
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        active_client_id = self.client_id
        if active_client_id:
            headers["X-From-Id"] = active_client_id
        return headers

    # ── Чтение статуса ────────────────────────────────────────────────────────

    async def get_status(self):
        status = {
            "is_live": False,
            "viewers": 0,
            "title": "",
            "game": "",
            "needs_publish": False
        }
        if not self.owner_id:
            return status

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"{self.api_base}/blog/{self.owner_id}/public_video_stream"
                resp = await client.get(url)

                if resp.status_code == 200:
                    data = resp.json()
                    is_live = data.get("isOnline", False)
                    title = data.get("title") or ""

                    category_data = data.get("category") or {}
                    game = category_data.get("title") or ""

                    count_data = data.get("count") or {}
                    viewers = count_data.get("viewers") or 0

                    status.update({
                        "is_live": is_live,
                        "viewers": viewers,
                        "title": str(title).strip(),
                        "game": str(game).strip(),
                        "needs_publish": True  # Позволяем опубликовать трансляцию в любой момент из интерфейса [2.1]
                    })
        except Exception as e:
            logger.error(f"Ошибка статуса VK: {e!r}")

        return status

    # ── Вспомогательный метод обновления ──

    async def _update_stream_info(self, title: str = None, category_id: str = None) -> str:
        current_title = ""
        current_cat_id = ""

        if title is None or category_id is None:
            status = await self.get_status()
            if title is None:
                current_title = status.get("title") or ""
            if category_id is None:
                current_game = status.get("game") or ""
                if current_game:
                    current_cat_id = await self._find_category_id(current_game)

        final_title = title if title is not None else current_title
        final_cat_id = category_id if category_id is not None else current_cat_id

        payload = {}
        if final_title:
            title_block = [
                {
                    "type": "text",
                    "content": json.dumps([final_title, "unstyled", []], ensure_ascii=False),
                    "modificator": ""
                }
            ]
            payload["title_data"] = json.dumps(title_block, ensure_ascii=False)

        if final_cat_id:
            payload["category_id"] = final_cat_id

        if not payload:
            return "VK Live: Нет данных для обновления"

        async with http_client.create_client(timeout=10.0) as client:
            url = f"{self.api_base}/channel/{self.owner_id}/manage/stream"
            resp = await client.put(url, headers=self.headers, data=payload)
            if resp.status_code in (200, 204):
                return "VK Live: Данные трансляции успешно сохранены"
            return f"VK Ошибка ({resp.status_code}): {resp.text}"

    # ── Запись ────────────────────────────────────────────────────────────────

    async def set_title(self, title: str) -> str:
        if not self.token:
            return "VK Live: Нет токена авторизации. Скопируйте JSON auth из Local Storage VK!"
        if not self.owner_id:
            return "VK Live: Не задан Owner ID (ID или имя канала)"

        try:
            return await self._update_stream_info(title=title)
        except Exception as e:
            return f"VK Live Исключение: {e!r}"

    async def set_game(self, game: str) -> str:
        if not self.token:
            return "VK Live: Нет токена авторизации. Скопируйте JSON auth из Local Storage VK!"
        if not self.owner_id:
            return "VK Live: Не задан Owner ID (ID или имя канала)"

        try:
            category_id = await self._find_category_id(game)
            if not category_id:
                return f"VK Live: Игра '{game}' не найдена в каталоге VK."

            return await self._update_stream_info(category_id=category_id)
        except Exception as e:
            return f"VK Live Исключение: {e!r}"

    async def _find_category_id(self, game: str) -> str | None:
        try:
            async with http_client.create_client(timeout=10.0) as client:
                cat_url = f"{self.api_base}/public_video_stream/category/"
                cat_resp = await client.get(cat_url, params={"search": game})

                if cat_resp.status_code == 200:
                    items = cat_resp.json().get("data", [])
                    if items:
                        return items[0].get("id")
        except Exception:
            pass
        return None

    # ── Публикация трансляции (Сделать публичной) ───────────────────────────

    async def publish_stream(self) -> str:
        """
        Публикует трансляцию в VK Video Live.
        """
        if not self.token:
            return "VK Live: Нет токена авторизации"
        if not self.owner_id:
            return "VK Live: Не задан Owner ID"

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"{self.api_base}/channel/{self.owner_id}/manage/stream"
                payload = {
                    "publish": "1",
                    "access_status": "public",
                    "is_private": "0"
                }
                resp = await client.put(url, headers=self.headers, data=payload)
                if resp.status_code in (200, 204):
                    return "VK Live: Трансляция успешно опубликована!"
                return f"VK Live Ошибка публикации ({resp.status_code}): {resp.text}"
        except Exception as e:
            return f"VK Live Исключение при публикации: {e!r}"
