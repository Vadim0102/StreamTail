import httpx
from app.plugins.base import BasePlugin


class YouTubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.token = self.config.get("token")
        self.broadcast_id = self.config.get("broadcast_id")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={self.broadcast_id}"
                resp = await client.get(url, headers=self.headers)
                data = resp.json()

                if data.get("items"):
                    item = data["items"][0]
                    status["is_live"] = (item["status"]["lifeCycleStatus"] == "live")
                    status["title"] = item["snippet"]["title"]

                    video_id = item["id"]
                    v_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet&id={video_id}"
                    v_resp = await client.get(v_url, headers=self.headers)
                    v_data = v_resp.json()

                    if v_data.get("items"):
                        v_item = v_data["items"][0]
                        lsd = v_item.get("liveStreamingDetails", {})
                        status["viewers"] = int(lsd.get("concurrentViewers", 0))
                        status["game"] = v_item["snippet"].get("categoryId", "")

        except httpx.HTTPStatusError as e:
            # Ошибка авторизации или серверов платформы
            from app.utils.logger import logger
            logger.error(f"YouTube API вернул статус {e.response.status_code}")
        except Exception as e:
            from app.utils.logger import logger
            logger.error(f"Ошибка соединения с YouTube: {e}")
        return status

    async def set_title(self, title: str) -> str:
        async with httpx.AsyncClient() as client:
            url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&id={self.broadcast_id}"
            current = await client.get(url, headers=self.headers)
            data = current.json()
            if not data.get("items"):
                return "YouTube: Трансляция не найдена"

            snippet = data["items"][0]["snippet"]
            snippet["title"] = title

            update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet"
            resp = await client.put(update_url, headers=self.headers,
                                    json={"id": self.broadcast_id, "snippet": snippet})
            return "YouTube: Заголовок изменен" if resp.status_code == 200 else f"YouTube Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        return "YouTube: Смена категории по имени ограничена YouTube API."
