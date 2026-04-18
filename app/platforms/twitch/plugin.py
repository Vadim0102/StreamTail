import requests
from app.plugins.base import BasePlugin


class TwitchPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.name = "Twitch"
        self.client_id = self.config.get("client_id")
        self.token = self.config.get("token")
        self.broadcaster_id = self.config.get("broadcaster_id")

        self.headers = {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }

    def _get_game_id(self, game_name):
        url = f"https://api.twitch.tv/helix/games?name={game_name}"
        resp = requests.get(url, headers=self.headers).json()
        if resp.get("data"):
            return resp["data"][0]["id"]
        return None

    def execute(self, action, *args, **kwargs):
        if not self.enabled: return None

        try:
            if action == "get_status":
                status = {"is_live": False, "viewers": 0, "title": "", "game": ""}

                # Проверка трансляции
                url = f"https://api.twitch.tv/helix/streams?user_id={self.broadcaster_id}"
                resp = requests.get(url, headers=self.headers).json()

                if resp.get("data"):
                    stream = resp["data"][0]
                    status["is_live"] = True
                    status["viewers"] = stream.get("viewer_count", 0)
                    status["title"] = stream.get("title", "")
                    status["game"] = stream.get("game_name", "")
                else:
                    # Если оффлайн, получаем название и игру канала
                    url_ch = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
                    resp_ch = requests.get(url_ch, headers=self.headers).json()
                    if resp_ch.get("data"):
                        ch = resp_ch["data"][0]
                        status["title"] = ch.get("title", "")
                        status["game"] = ch.get("game_name", "")
                return status

            elif action == "set_title":
                url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
                resp = requests.patch(url, headers=self.headers, json={"title": kwargs.get("title")})
                return "Twitch: Заголовок успешно изменен" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

            elif action == "set_game":
                game_id = self._get_game_id(kwargs.get("game"))
                if not game_id: return f"Twitch: Игра '{kwargs.get('game')}' не найдена"

                url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
                resp = requests.patch(url, headers=self.headers, json={"game_id": game_id})
                return "Twitch: Категория изменена" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

        except Exception as e:
            return f"Twitch Exception: {str(e)}"
