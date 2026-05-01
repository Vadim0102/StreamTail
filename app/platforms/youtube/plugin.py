import httpx
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token
from app.utils.logger import logger

class YouTubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.innertube_context = {
            "client": {"clientName": 62, "clientVersion": "1.20260422.03.00", "hl": "ru", "gl": "RU"}
        }

    @property
    def token_data(self):
        return get_token("youtube") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def broadcast_id(self):
        return self.token_data.get("broadcast_id") or self.config.get("broadcast_id")

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def innertube_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Origin": "https://studio.youtube.com",
        }

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.token or not self.broadcast_id:
            return status

        try:
            async with httpx.AsyncClient() as client:
                url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={self.broadcast_id}"
                resp = await client.get(url, headers=self.headers)
                data = resp.json()

                if data.get("items"):
                    item = data["items"][0]
                    status["is_live"] = (item["status"]["lifeCycleStatus"] == "live")
                    status["title"] = item["snippet"]["title"]

                    video_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet&id={item['id']}"
                    v_resp = await client.get(video_url, headers=self.headers)
                    v_data = v_resp.json()

                    if v_data.get("items"):
                        v_item = v_data["items"][0]
                        lsd = v_item.get("liveStreamingDetails", {})
                        status["viewers"] = int(lsd.get("concurrentViewers", 0))
                        status["game"] = v_item["snippet"].get("categoryId", "")
        except Exception as e:
            logger.error(f"Ошибка статуса YouTube: {e}")
        return status

    async def set_title(self, title: str) -> str:
        if not self.token: return "YouTube: Нет токена"
        async with httpx.AsyncClient() as client:
            url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&id={self.broadcast_id}"
            current = await client.get(url, headers=self.headers)
            data = current.json()
            if not data.get("items"): return "YouTube: Трансляция не найдена"

            snippet = data["items"][0]["snippet"]
            snippet["title"] = title
            update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet"
            resp = await client.put(update_url, headers=self.headers, json={"id": self.broadcast_id, "snippet": snippet})
            return "YouTube: Заголовок изменен" if resp.status_code == 200 else f"YouTube Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        return "YouTube: Смена игры по названию требует сложного InnerTube API. Разработка продолжается."
