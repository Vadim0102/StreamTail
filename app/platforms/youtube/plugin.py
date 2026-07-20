# app/platforms/youtube/plugin.py
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger

from app.platforms.youtube.client import YouTubeApiClient


class YouTubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.api_client = YouTubeApiClient(self)

    @property
    def token_data(self):
        return get_token("youtube") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def broadcast_id(self):
        return self.token_data.get("broadcast_id") or self.config.get("broadcast_id")

    async def _ensure_token_valid(self) -> bool:
        if is_token_valid("youtube"):
            return True

        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id")
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import youtube_auth
            logger.info("YouTube: токен истек. Выполняем автоматический refresh...")
            return await youtube_auth.refresh(c_id, c_sec, r_token)
        return False

    async def get_status(self):
        if not self.token:
            return {"is_live": False, "viewers": 0, "title": "", "game": ""}

        await self._ensure_token_valid()

        # Автоматическое определение broadcast_id при его отсутствии
        broadcast_id = self.broadcast_id
        if not broadcast_id:
            from app.auth.youtube_auth import _fetch_broadcast_id
            from app.auth.token_store import set_token
            bid = await _fetch_broadcast_id(self.token)
            if bid:
                broadcast_id = bid
                tdata = self.token_data
                tdata["broadcast_id"] = bid
                set_token("youtube", tdata)
            else:
                return {"is_live": False, "viewers": 0, "title": "", "game": ""}

        return await self.api_client.fetch_status(broadcast_id)

    async def get_broadcasts(self) -> list:
        if not self.token:
            return []
        await self._ensure_token_valid()
        return await self.api_client.fetch_broadcasts()

    async def get_live_streams(self) -> list:
        if not self.token:
            return []
        await self._ensure_token_valid()
        return await self.api_client.fetch_live_streams()

    async def set_title(self, title: str) -> str:
        if not self.token:
            return "YouTube: Нет токена"
        await self._ensure_token_valid()
        return await self.api_client.update_title(self.broadcast_id, title)

    async def set_game(self, game: str) -> str:
        if not self.token:
            return "YouTube: Нет токена"
        await self._ensure_token_valid()

        # Нормализация категорий
        categories_map = {
            "gaming": "20", "games": "20", "игры": "20",
            "people": "22", "blogs": "22", "блоги": "22",
            "entertainment": "24", "развлечения": "24",
            "music": "10", "музыка": "10",
            "education": "27", "образование": "27",
            "tech": "28", "science": "28", "наука": "28", "технологии": "28"
        }

        normalized = game.lower().strip()
        category_id = "20"  # По умолчанию Игры
        for k, v in categories_map.items():
            if k in normalized:
                category_id = v
                break

        if normalized.isdigit():
            category_id = normalized

        return await self.api_client.update_category(self.broadcast_id, category_id)

    async def create_stream(self, title: str, game: str = "20", description: str = "", stream_id: str = None, latency: str = "ultraLow", is_shorts: bool = False) -> dict:
        if not self.token:
            return {"success": False, "error": "YouTube: Требуется авторизация"}
        await self._ensure_token_valid()
        return await self.api_client.create_broadcast(title, game, description, stream_id, latency, is_shorts)

    async def publish_stream(self) -> str:
        if not self.token:
            return "YouTube: Требуется авторизация"
        await self._ensure_token_valid()
        return await self.api_client.publish_broadcast(self.broadcast_id)

    async def stop_stream(self) -> str:
        if not self.token:
            return "YouTube: Требуется авторизация"
        await self._ensure_token_valid()
        return await self.api_client.stop_broadcast(self.broadcast_id)

    async def upload_thumbnail(self, image_path: str) -> str:
        if not self.token:
            return "YouTube: Требуется авторизация"
        await self._ensure_token_valid()
        return await self.api_client.upload_thumbnail_image(self.broadcast_id, image_path)
