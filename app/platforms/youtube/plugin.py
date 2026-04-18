import requests
from app.plugins.base import BasePlugin


class YouTubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.name = "YouTube"
        self.token = self.config.get("token")
        self.broadcast_id = self.config.get("broadcast_id")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def execute(self, action, *args, **kwargs):
        if not self.enabled: return None
        try:
            if action == "get_status":
                status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
                url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={self.broadcast_id}"
                resp = requests.get(url, headers=self.headers).json()

                if "items" in resp and len(resp["items"]) > 0:
                    item = resp["items"][0]
                    status["is_live"] = (item["status"]["lifeCycleStatus"] == "live")
                    status["title"] = item["snippet"]["title"]

                    # Запрос количества зрителей (на ютубе это свойство самого видео, а не трансляции)
                    video_id = item["id"]
                    v_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet&id={video_id}"
                    v_resp = requests.get(v_url, headers=self.headers).json()

                    if v_resp.get("items"):
                        v_item = v_resp["items"][0]
                        lsd = v_item.get("liveStreamingDetails", {})
                        status["viewers"] = int(lsd.get("concurrentViewers", 0))
                        status["game"] = v_item["snippet"].get("categoryId", "")  # ID категории
                return status

            elif action == "set_title":
                url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&id={self.broadcast_id}"
                current = requests.get(url, headers=self.headers).json()
                if not current.get("items"): return "YouTube: Трансляция не найдена"

                snippet = current["items"][0]["snippet"]
                snippet["title"] = kwargs.get("title")

                update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet"
                resp = requests.put(update_url, headers=self.headers, json={
                    "id": self.broadcast_id,
                    "snippet": snippet
                })
                return "YouTube: Заголовок изменен" if resp.status_code == 200 else f"YT Ошибка: {resp.text}"

            elif action == "set_game":
                return "YouTube: Смена категории по имени ограничена YouTube API (требуется передавать CategoryID)"

        except Exception as e:
            return f"YT Exception: {str(e)}"
