from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger
from app.utils import http_client

from app.platforms.youtube.client import YouTubeApiClient
from app.platforms.youtube.chat import YouTubeChatClient


class YouTubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.api_client = YouTubeApiClient(self)
        self.chat_client = YouTubeChatClient(self)

        self._last_real_id = None  # ID последнего отправленного сообщения
        self._sent_messages_cache = []  # История отправленных строк для дедупликации
        self._chat_history_cache = {}  # Временная история чата (ID -> Данные сообщения)

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

    async def _force_token_refresh(self) -> bool:
        """Принудительно запрашивает новый Access Token, игнорируя локальные проверки времени."""
        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id")
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import youtube_auth
            logger.info("YouTube: Инициировано принудительное обновление токена (OAuth refresh)...")
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

    async def create_stream(self, title: str, game: str = "20", description: str = "", stream_id: str = None,
                            latency: str = "ultraLow", is_shorts: bool = False) -> dict:
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

    async def _fetch_user_login(self) -> str:
        """Получает и кэширует реальное название канала для корректного отображения эха."""
        cached_name = self.token_data.get("broadcaster_name")
        if cached_name:
            return cached_name

        if not self.token:
            return "YouTube Owner"

        try:
            async with http_client.create_client(timeout=10.0) as client:
                resp = await client.get(
                    "https://youtube.googleapis.com/youtube/v3/channels",
                    params={"part": "snippet", "mine": "true"},
                    headers={"Authorization": f"Bearer {self.token}"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("items"):
                        name = data["items"][0]["snippet"]["title"]
                        from app.auth.token_store import set_token
                        tdata = self.token_data
                        tdata["broadcaster_name"] = name
                        set_token("youtube", tdata)
                        return name
        except Exception as e:
            logger.error(f"YouTube Plugin: не удалось получить имя канала: {e}")
        return "YouTube Owner"

    # ── Методы чата ──

    async def start_chat_listener(self):
        await self.chat_client.start()

    async def stop_chat_listener(self):
        await self.chat_client.stop()

    async def send_chat_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        if not self.token:
            return False
        await self._ensure_token_valid()

        real_id = await self.api_client.send_chat_message(self.broadcast_id, text)
        if real_id:
            self._last_real_id = real_id
            self._sent_messages_cache.append(text)
            if len(self._sent_messages_cache) > 15:
                self._sent_messages_cache.pop(0)
            return True
        return False

    def register_sent_echo(self, echo_id: str):
        if self._last_real_id:
            from app.core.service_container import container
            bus = container.get("event_bus")
            if bus:
                bus.emit("chat.message_id_updated", {
                    "platform": "youtube",
                    "old_id": echo_id,
                    "new_id": self._last_real_id
                })
            self._last_real_id = None

    async def delete_chat_message(self, message_id: str) -> bool:
        if not self.token:
            return False
        await self._ensure_token_valid()

        # ИСПРАВЛЕНО: Убрана ошибочная проверка "LCC.", так как LCC. - это валидный API-формат ID, готовый к удалению
        if str(message_id).startswith("yt_") or str(message_id).startswith("ChwK") or len(message_id) < 30:
            cached_data = self._chat_history_cache.get(message_id)
            if not cached_data:
                logger.warning("YouTube Plugin: Сообщение отсутствует в локальной истории. Удаление невозможно.")
                return False

            logger.info(f"YouTube Plugin: Попытка сопоставить scraped ID {message_id} с реальным API ID...")
            real_id = await self.api_client.resolve_scraped_id(message_id, cached_data)
            if real_id:
                # Обновляем ID на экране
                from app.core.service_container import container
                bus = container.get("event_bus")
                if bus:
                    bus.emit("chat.message_id_updated", {
                        "platform": "youtube",
                        "old_id": message_id,
                        "new_id": real_id
                    })
                message_id = real_id
            else:
                logger.warning("YouTube Plugin: Не удалось сопоставить ID. Удаление сообщения отменено.")
                return False

        res = await self.api_client.delete_message(message_id)
        if res:
            # Вручную посылаем событие удаления в интерфейс
            from app.core.service_container import container
            bus = container.get("event_bus")
            if bus:
                bus.emit("chat.message_deleted", {"platform": "youtube", "msg_id": message_id})
            return True
        return False

    async def pin_chat_message(self, message_id: str, duration: int = None) -> bool:
        """YouTube API не имеет методов для закрепления сообщений сторонними приложениями."""
        logger.warning("YouTube: Платформа YouTube Live Chat API не поддерживает закрепление сообщений сторонними приложениями.")
        return False

    async def ban_chat_user(self, user_id: str, reason: str = "", duration: int = None) -> bool:
        if not self.token:
            return False
        await self._ensure_token_valid()
        return await self.api_client.ban_user(user_id, reason, duration)
