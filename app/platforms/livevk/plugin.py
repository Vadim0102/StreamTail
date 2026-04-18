import requests
from app.plugins.base import BasePlugin


class LiveVKPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.name = "LiveVK"
        self.token = self.config.get("token")
        self.owner_id = self.config.get("owner_id")
        self.api_base = "https://api.live.vkvideo.ru/v1"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def execute(self, action, *args, **kwargs):
        if not self.enabled: return None
        try:
            if action == "get_status":
                status = {"is_live": False, "viewers": 0, "title": "", "game": ""}

                # Получаем данные о канале и текущем стриме
                url = f"{self.api_base}/channel/{self.owner_id}"
                resp = requests.get(url, headers=self.headers)

                if resp.status_code == 200:
                    data = resp.json()
                    stream = data.get("stream")
                    if stream and stream.get("isOnline"):
                        status["is_live"] = True
                        status["viewers"] = stream.get("viewers", 0)
                        status["title"] = stream.get("title", data.get("title", ""))
                        status["game"] = stream.get("category", {}).get("name", "")
                    else:
                        status["title"] = data.get("title", "")
                return status

            elif action == "set_title":
                url = f"{self.api_base}/channel/{self.owner_id}"
                resp = requests.patch(url, headers=self.headers, json={"title": kwargs.get("title")})
                return "LiveVK: Заголовок установлен" if resp.ok else f"LiveVK Ошибка: {resp.text}"

            elif action == "set_game":
                url = f"{self.api_base}/channel/{self.owner_id}"
                # В зависимости от API может требоваться id, но для DevAPI обычно достаточно имени или специального запроса в каталог
                resp = requests.patch(url, headers=self.headers, json={"category": {"name": kwargs.get("game")}})
                return "LiveVK: Категория изменена" if resp.ok else f"LiveVK Ошибка: {resp.text}"

        except Exception as e:
            return f"VK Exception: {str(e)}"
