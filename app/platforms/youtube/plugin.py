"""
YouTube Data API v3 Integration Plugin.

========================================================================================
                                     YOUTUBE API MAP
========================================================================================

1. ЧТЕНИЕ СТАТУСА ТРАНСЛЯЦИИ:
   • GET https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={broadcast_id}
   • Headers: Authorization: Bearer <token>
   • Response: {"items": [{"status": {"lifeCycleStatus": "live"}, "snippet": {"title": "Stream Title"}}]}

2. ПОЛУЧЕНИЕ ЧИСЛА ЗРИТЕЛЕЙ:
   • GET https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet&id={broadcast_id}
   • Response: {"items": [{"liveStreamingDetails": {"concurrentViewers": "150"}, "snippet": {"categoryId": "20"}}]}

3. СПИСОК ВСЕХ ТРАНСЛЯЦИЙ:
   • GET https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=id,snippet,status&broadcastStatus=all&maxResults=15
   • Response: Список всех трансляций пользователя для окна «Выбор стрима».

4. ОБНОВЛЕНИЕ ТИТЛА ТРАНСЛЯЦИИ (Метод PUT, паттерн Read-Modify-Write):
   • PUT https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet
   • Body (JSON): {"id": "{broadcast_id}", "snippet": { ... "title": "New Title" ... }}
     * Важно: API YouTube v3 требует отправки всего объекта snippet целиком, поэтому 
       плагин сначала запрашивает текущий snippet через GET, изменяет title и отправляет PUT.
========================================================================================
"""

from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger
from app.utils import http_client


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
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.token or not self.broadcast_id:
            return status

        await self._ensure_token_valid()

        try:
            async with http_client.create_client() as client:
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
            logger.error(f"Ошибка статуса YouTube: {e!r}")
        return status

    async def get_broadcasts(self) -> list:
        if not self.token:
            return []
        await self._ensure_token_valid()
        try:
            async with http_client.create_client(timeout=10) as client:
                resp = await client.get(
                    "https://youtube.googleapis.com/youtube/v3/liveBroadcasts",
                    params={
                        "part": "id,snippet,status",
                        "broadcastStatus": "all",
                        "maxResults": 15,
                    },
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    return [
                        {
                            "id": item["id"],
                            "title": item["snippet"]["title"],
                            "status": item["status"]["lifeCycleStatus"]
                        }
                        for item in items
                    ]
        except Exception as e:
            logger.error(f"YouTube: Ошибка получения списка трансляций: {e}")
        return []

    async def set_title(self, title: str) -> str:
        if not self.token: return "YouTube: Нет токена"
        await self._ensure_token_valid()
        async with http_client.create_client() as client:
            url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&id={self.broadcast_id}"
            current = await client.get(url, headers=self.headers)
            data = current.json()
            if not data.get("items"): return "YouTube: Трансляция не найдена"

            snippet = data["items"][0]["snippet"]
            snippet["title"] = title
            update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet"
            resp = await client.put(update_url, headers=self.headers,
                                    json={"id": self.broadcast_id, "snippet": snippet})
            return "YouTube: Заголовок изменен" if resp.status_code == 200 else f"YouTube Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        return "YouTube: Смена игры по названию требует сложного InnerTube API. Разработка продолжается."
