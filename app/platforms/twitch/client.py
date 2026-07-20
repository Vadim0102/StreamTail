import httpx
from app.utils import http_client
from app.utils.logger import logger


class TwitchHelixClient:
    def __init__(self, plugin):
        self.plugin = plugin

    @property
    def headers(self):
        return {
            "Client-Id": self.plugin.token_data.get("client_id", self.plugin.client_id),
            "Authorization": f"Bearer {self.plugin.token}"
        }

    async def get_game_id(self, game_name: str, client: httpx.AsyncClient) -> str:
        url = f"https://api.twitch.tv/helix/games?name={game_name}"
        resp = await client.get(url, headers=self.headers)
        data = resp.json()
        if data.get("data"):
            return data["data"][0]["id"]
        return ""

    async def fetch_status(self) -> dict:
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.plugin.token or not self.plugin.broadcaster_id:
            return status

        await self.plugin._ensure_token_valid()

        # Ошибки таймаута намеренно не отлавливаются здесь, чтобы планировщик сохранял последнее стабильное состояние GUI
        async with http_client.create_client(timeout=20.0) as client:
            url = f"https://api.twitch.tv/helix/streams?user_id={self.plugin.broadcaster_id}"
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
                url_ch = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.plugin.broadcaster_id}"
                resp_ch = await client.get(url_ch, headers=self.headers)
                resp_ch.raise_for_status()
                ch_data = resp_ch.json()
                if ch_data.get("data"):
                    ch = ch_data["data"][0]
                    status.update({
                        "title": ch.get("title", ""),
                        "game": ch.get("game_name", "")
                    })
        return status

    async def update_title(self, title: str) -> str:
        async with http_client.create_client() as client:
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.plugin.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"title": title})
            return "Twitch: Заголовок изменен" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

    async def update_game(self, game_name: str) -> str:
        async with http_client.create_client() as client:
            game_id = await self.get_game_id(game_name, client)
            if not game_id:
                return f"Twitch: Игра '{game_name}' не найдена"
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.plugin.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"game_id": game_id})
            return "Twitch: Категория изменена" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

    async def pin_message(self, message_id: str, duration: int = None) -> bool:
        try:
            async with http_client.create_client() as client:
                url = "https://api.twitch.tv/helix/chat/pins"
                params = {
                    "broadcaster_id": self.plugin.broadcaster_id,
                    "moderator_id": self.plugin.broadcaster_id,
                    "message_id": message_id
                }
                if duration:
                    params["duration_seconds"] = int(duration)

                resp = await client.put(url, headers=self.headers, params=params)
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Twitch API Client: ошибка закрепления сообщения: {e!r}")
        return False

    async def delete_message(self, message_id: str) -> bool:
        try:
            async with http_client.create_client() as client:
                url = "https://api.twitch.tv/helix/moderation/chat"
                params = {
                    "broadcaster_id": self.plugin.broadcaster_id,
                    "moderator_id": self.plugin.broadcaster_id,
                    "message_id": message_id
                }
                resp = await client.delete(url, headers=self.headers, params=params)
                return resp.status_code == 204
        except Exception as e:
            logger.error(f"Twitch API Client: ошибка удаления сообщения: {e!r}")
        return False

    async def ban_user(self, user_id: str, reason: str = "", duration: int = None) -> bool:
        try:
            async with http_client.create_client() as client:
                url = "https://api.twitch.tv/helix/moderation/bans"
                params = {
                    "broadcaster_id": self.plugin.broadcaster_id,
                    "moderator_id": self.plugin.broadcaster_id
                }
                payload = {"data": {"user_id": str(user_id)}}
                if duration:
                    payload["data"]["duration"] = int(duration)
                if reason:
                    payload["data"]["reason"] = str(reason)

                resp = await client.post(url, headers=self.headers, params=params, json=payload)
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Twitch API Client: ошибка блокировки пользователя: {e!r}")
        return False
