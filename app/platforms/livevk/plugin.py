import httpx
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token
from app.utils.logger import logger

class LiveVKPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.api_base = "https://apidev.live.vkvideo.ru/v1"

    @property
    def token_data(self):
        return get_token("livevk") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def owner_id(self):
        return self.config.get("owner_id")

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.token or not self.owner_id:
            return status

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = f"{self.api_base}/channel/{self.owner_id}"
                resp = await client.get(url, headers=self.headers)

                if resp.status_code == 200:
                    data = resp.json()
                    stream = data.get("stream")
                    if stream and stream.get("isOnline"):
                        status.update({
                            "is_live": True,
                            "viewers": stream.get("viewers", 0),
                            "title": stream.get("title", data.get("title", "")),
                            "game": stream.get("category", {}).get("name", "")
                        })
                    else:
                        status["title"] = data.get("title", "")
        except Exception as e:
            logger.error(f"Ошибка статуса VK: {e}")

        return status

    async def set_title(self, title: str) -> str:
        if not self.token: return "VK Live: Нет токена"
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/channel/{self.owner_id}"
            resp = await client.patch(url, headers=self.headers, json={"title": title})
            return "VK Live: Заголовок установлен" if resp.status_code in (200, 204) else f"VK Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        if not self.token: return "VK Live: Нет токена"
        try:
            async with httpx.AsyncClient() as client:
                cat_url = f"{self.api_base}/category"
                cat_resp = await client.get(cat_url, params={"search": game}, headers=self.headers)

                category_id = None
                if cat_resp.status_code == 200:
                    items = cat_resp.json().get("items", [])
                    if items: category_id = items[0].get("id")

                if not category_id: return f"VK Live: Игра '{game}' не найдена."

                url = f"{self.api_base}/channel/{self.owner_id}"
                resp = await client.patch(url, headers=self.headers, json={"categoryId": category_id})
                return f"VK Live: Категория изменена" if resp.status_code in (200, 204) else f"VK Ошибка: {resp.text}"
        except Exception as e:
            return f"VK Live Ошибка: {e}"
