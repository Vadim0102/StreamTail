import httpx
from app.plugins.base import BasePlugin

class LiveVKPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.token = self.config.get("token")
        self.owner_id = self.config.get("owner_id")
        self.api_base = "https://api.live.vkvideo.ru/v1"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        async with httpx.AsyncClient() as client:
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
        return status

    async def set_title(self, title: str) -> str:
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/channel/{self.owner_id}"
            resp = await client.patch(url, headers=self.headers, json={"title": title})
            return "LiveVK: Заголовок установлен" if resp.status_code in (200, 204) else f"VK Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/channel/{self.owner_id}"
            resp = await client.patch(url, headers=self.headers, json={"category": {"name": game}})
            return "LiveVK: Категория изменена" if resp.status_code in (200, 204) else f"VK Ошибка: {resp.text}"
