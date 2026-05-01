import httpx
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token
from app.utils.logger import logger

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

    async def _get_game_id(self, game_name: str, client: httpx.AsyncClient) -> str:
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

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
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
            logger.error(f"Ошибка статуса Twitch: {e}")
        return status

    async def set_title(self, title: str) -> str:
        if not self.token: return "Twitch: Нет токена"
        async with httpx.AsyncClient() as client:
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"title": title})
            return "Twitch: Заголовок изменен" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        if not self.token: return "Twitch: Нет токена"
        async with httpx.AsyncClient() as client:
            game_id = await self._get_game_id(game, client)
            if not game_id:
                return f"Twitch: Игра '{game}' не найдена"
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"game_id": game_id})
            return "Twitch: Категория изменена" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"
