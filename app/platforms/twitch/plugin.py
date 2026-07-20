from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger
from app.utils import http_client

from app.platforms.twitch.client import TwitchHelixClient
from app.platforms.twitch.chat import TwitchIRCClient
from app.platforms.twitch.eventsub import TwitchEventSubClient


class TwitchPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.client_id = self.config.get("client_id")

        self.api_client = TwitchHelixClient(self)
        self.chat_client = TwitchIRCClient(self)
        self.eventsub_client = TwitchEventSubClient(self)  # Инициализация Real-time WebSockets клиента

    @property
    def token_data(self):
        return get_token("twitch") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def broadcaster_id(self):
        return self.token_data.get("broadcaster_id") or self.config.get("broadcaster_id")

    async def _ensure_token_valid(self) -> bool:
        if is_token_valid("twitch"):
            return True

        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id") or self.client_id
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import twitch_auth
            logger.info("Twitch: токен истек. Выполняем автоматическое обновление...")
            return await twitch_auth.refresh(c_id, c_sec, r_token)
        return False

    async def _fetch_user_login(self) -> str:
        cached_login = self.token_data.get("broadcaster_login")
        if cached_login:
            return cached_login

        if not self.token:
            return ""

        try:
            async with http_client.create_client(timeout=15.0) as client:
                resp = await client.get("https://api.twitch.tv/helix/users", headers={
                    "Client-Id": self.token_data.get("client_id", self.client_id),
                    "Authorization": f"Bearer {self.token}"
                })
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        login = data["data"][0]["login"]
                        from app.auth.token_store import set_token
                        tdata = self.token_data
                        tdata["broadcaster_login"] = login
                        set_token("twitch", tdata)
                        return login
        except Exception as e:
            logger.error(f"Twitch Plugin: не удалось получить логин пользователя: {e}")
        return ""

    async def get_status(self):
        return await self.api_client.fetch_status()

    async def set_title(self, title: str) -> str:
        if not self.token:
            return "Twitch: Нет токена"
        await self._ensure_token_valid()
        return await self.api_client.update_title(title)

    async def set_game(self, game: str) -> str:
        if not self.token:
            return "Twitch: Нет токена"
        await self._ensure_token_valid()
        return await self.api_client.update_game(game)

    async def pin_chat_message(self, message_id: str, duration: int = None) -> bool:
        return await self.api_client.pin_message(message_id, duration)

    async def delete_chat_message(self, message_id: str) -> bool:
        return await self.api_client.delete_message(message_id)

    async def ban_chat_user(self, user_id: str, reason: str = "", duration: int = None) -> bool:
        return await self.api_client.ban_user(user_id, reason, duration)

    def register_sent_echo(self, echo_id: str):
        self.chat_client.register_sent_echo(echo_id)

    async def start_chat_listener(self):
        await self.chat_client.start()
        await self.eventsub_client.start()  # Запуск реал-тайм прослушивания событий

    async def stop_chat_listener(self):
        await self.chat_client.stop()
        await self.eventsub_client.stop()  # Остановка реал-тайм прослушивания событий

    async def send_chat_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        return await self.chat_client.send_message(text, reply_parent_msg_id)
