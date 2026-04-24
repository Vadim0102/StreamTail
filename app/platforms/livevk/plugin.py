import httpx
from app.plugins.base import BasePlugin
from app.utils.logger import logger


class LiveVKPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.token = self.config.get("token")
        self.owner_id = self.config.get("owner_id")

        # НОВАЯ точка входа из официальной документации dev.live.vkvideo.ru
        self.api_base = "https://apidev.live.vkvideo.ru/v1"

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.token or not self.owner_id:
            return status

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Эндпоинт 'channel' по новой доке
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
                            # Категории теперь возвращаются словарем
                            "game": stream.get("category", {}).get("name", "")
                        })
                    else:
                        status["title"] = data.get("title", "")

        except httpx.HTTPStatusError as e:
            logger.error(f"VK Video Live API вернул статус {e.response.status_code}: {e.response.text}")
        except Exception as e:
            logger.error(f"Ошибка соединения с VK Video Live: {e}")

        return status

    async def set_title(self, title: str) -> str:
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/channel/{self.owner_id}"
            resp = await client.patch(url, headers=self.headers, json={"title": title})

            if resp.status_code in (200, 204):
                return "VK Live: Заголовок установлен"
            return f"VK Ошибка ({resp.status_code}): {resp.text}"

    async def set_game(self, game: str) -> str:
        # Для новой платформы поиск категорий происходит через эндпоинт /category
        try:
            async with httpx.AsyncClient() as client:
                # Шаг 1: Ищем ID категории
                cat_url = f"{self.api_base}/category"
                cat_resp = await client.get(cat_url, params={"search": game}, headers=self.headers)

                category_id = None
                if cat_resp.status_code == 200:
                    items = cat_resp.json().get("items", [])
                    if items:
                        category_id = items[0].get("id")  # Берем первую найденную игру

                if not category_id:
                    return f"VK Live: Игра '{game}' не найдена в базе платформы."

                # Шаг 2: Устанавливаем ID категории на канал
                url = f"{self.api_base}/channel/{self.owner_id}"
                resp = await client.patch(url, headers=self.headers, json={"categoryId": category_id})

                if resp.status_code in (200, 204):
                    return f"VK Live: Категория изменена на '{items[0].get('name')}'"
                return f"VK Ошибка ({resp.status_code}): {resp.text}"

        except Exception as e:
            return f"VK Live Сетевая ошибка: {e}"
