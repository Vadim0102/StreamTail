"""
Twitch Helix API Integration Plugin.

========================================================================================
                                     TWITCH API MAP
========================================================================================

1. ЧТЕНИЕ СТАТУСА ТРАНСЛЯЦИИ (В эфире):
   • GET https://api.twitch.tv/helix/streams?user_id={broadcaster_id}
   • Headers: Client-Id: ...; Authorization: Bearer <token>
   • Response: {"data": [{"viewer_count": 150, "title": "Stream Title", "game_name": "Minecraft"}]}

2. ЧТЕНИЕ ПАРАМЕТРОВ КАНАЛА (Оффлайн-резерв):
   • GET https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}
   • Headers: Client-Id: ...; Authorization: Bearer <token>
   • Response: {"data": [{"title": "Offline Title", "game_name": "Minecraft"}]}

3. ПОИСК ИГРЫ ПО ИМЕНИ:
   • GET https://api.twitch.tv/helix/games?name={game_name}
   • Response: {"data": [{"id": "game_id_string"}]}

4. ОБНОВЛЕНИЕ ТРАНСЛЯЦИИ (Метод PATCH):
   • PATCH https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}
   • Headers: Client-Id: ...; Authorization: Bearer <token>; Content-Type: application/json
   • Body (JSON): {"title": "New Title", "game_id": "game_id_string"}
========================================================================================
"""

from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger
from app.utils import http_client


class TwitchPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.client_id = self.config.get("client_id")

    @property
    def token_data(self):
        return get_token("twitch") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def broadcaster_id(self):
        return self.token_data.get("broadcaster_id") or self.config.get("broadcaster_id")

    @property
    def headers(self):
        return {
            "Client-Id": self.token_data.get("client_id", self.client_id),
            "Authorization": f"Bearer {self.token}"
        }

    async def _ensure_token_valid(self) -> bool:
        if is_token_valid("twitch"):
            return True

        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id") or self.client_id
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import twitch_auth
            logger.info("Twitch: токен истек. Выполняем автоматическое обновление токена...")
            return await twitch_auth.refresh(c_id, c_sec, r_token)
        return False

    async def _get_game_id(self, game_name: str, client: http_client.create_client) -> str:
        url = f"https://api.twitch.tv/helix/games?name={game_name}"
        resp = await client.get(url, headers=self.headers)
        data = resp.json()
        if data.get("data"):
            return data["data"][0]["id"]
        return ""

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.token or not self.broadcaster_id:
            return status

        await self._ensure_token_valid()

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"https://api.twitch.tv/helix/streams?user_id={self.broadcaster_id}"
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()

                if data.get("data"):
                    stream = data["data"][0]
                    status.update({
                        "is_live": True,
                        "viewers": stream.get("viewer_count", 0),
                        "title": stream.get("title", ""),
                        "game": stream.get("game_name", "")
                    })
                else:
                    url_ch = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
                    resp_ch = await client.get(url_ch, headers=self.headers)
                    ch_data = resp_ch.json()
                    if ch_data.get("data"):
                        ch = ch_data["data"][0]
                        status.update({
                            "title": ch.get("title", ""),
                            "game": ch.get("game_name", "")
                        })
        except Exception as e:
            logger.error(f"Ошибка статуса Twitch: {e!r}")
        return status

    async def set_title(self, title: str) -> str:
        if not self.token: return "Twitch: Нет токена"
        await self._ensure_token_valid()
        async with http_client.create_client() as client:
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"title": title})
            return "Twitch: Заголовок изменен" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        if not self.token: return "Twitch: Нет токена"
        await self._ensure_token_valid()
        async with http_client.create_client() as client:
            game_id = await self._get_game_id(game, client)
            if not game_id:
                return f"Twitch: Игра '{game}' не найдена"
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"game_id": game_id})
            return "Twitch: Категория изменена" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"
