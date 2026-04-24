import httpx
from app.plugins.base import BasePlugin
from app.utils.logger import logger


class YouTubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.token = self.config.get("token")
        self.broadcast_id = self.config.get("broadcast_id")

        # Заголовки для официального API v3
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Заголовки для InnerTube (может потребоваться Cookie, если Bearer токена не хватит)
        self.innertube_headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Origin": "https://studio.youtube.com",
        }

        # Базовый контекст запроса для внутреннего API (как в твоем дампе)
        self.innertube_context = {
            "client": {
                "clientName": 62,  # 62 = WEB_CREATOR (Творческая студия)
                "clientVersion": "1.20260422.03.00",
                "hl": "ru",
                "gl": "RU"
            }
        }

    async def get_status(self):
        # Официальный API отлично подходит для чтения статуса
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
        # Для названия оставляем Data API v3 (он работает надежно)
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

    # --- РАБОТА С INNER TUBE ---

    async def _find_game_mid(self, game_name: str) -> str | None:
        """Ищет Knowledge Graph ID (mid) игры через скрытый API Творческой студии."""
        url = "https://studio.youtube.com/youtubei/v1/gaming/game_title?alt=json"
        payload = {
            "context": self.innertube_context,
            "userInput": game_name
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=self.innertube_headers)
                if resp.status_code == 200:
                    data = resp.json()
                    titles = data.get("gameTitles", [])
                    if titles:
                        # Возвращаем ID первого результата совпадения (например, /m/09v6kpg)
                        logger.debug(f"Найдена игра на YT: {titles[0]['title']} (mid: {titles[0]['mid']})")
                        return titles[0].get("mid")
        except Exception as e:
            logger.error(f"YouTube InnerTube Поиск Ошибка: {e}")

        return None

    async def set_game(self, game: str) -> str:
        """Смена игры через скрытый API (позволяет задать точную игру, а не просто категорию)."""
        mid = await self._find_game_mid(game)
        if not mid:
            return f"YouTube: Игра '{game}' не найдена в базе (InnerTube)"

        # Используем эндпоинт Творческой студии для обновления метаданных видео
        url = "https://studio.youtube.com/youtubei/v1/video_manager/metadata_update?alt=json"

        payload = {
            "context": self.innertube_context,
            "encryptedVideoId": self.broadcast_id,
            "videoMetadata": {
                "category": {
                    "newCategoryId": 20  # Категория "Видеоигры"
                },
                "gameTitle": {
                    "newKgEntityId": mid  # Привязка к конкретной игре!
                }
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=self.innertube_headers)

                # InnerTube часто возвращает 200 OK, но содержит статус ошибки внутри JSON
                if resp.status_code == 200:
                    data = resp.json()
                    # Если API вернёт ошибку прав или токена, она будет в 'responseContext' или 'errors'
                    if "errors" in data:
                        return f"YouTube InnerTube Ошибка: {data['errors']}"

                    return f"YouTube: Категория изменена на '{game}'"
                else:
                    return f"YouTube InnerTube Ошибка ({resp.status_code}): {resp.text}"
        except Exception as e:
            return f"YouTube Сетевая ошибка: {e}"
