import httpx
from app.plugins.base import BasePlugin
from app.utils.logger import logger


class KickPlugin(BasePlugin):
    """
    Интеграция с Kick.com.

    Kick предоставляет публичный API без официальной документации.
    Для записи (смена названия/категории) требуется OAuth2 Bearer-токен.

    Конфиг (config/app.yaml):
        kick:
          enabled: true
          channel: "your_channel_slug"          # slug канала (строчные, без пробелов)
          token: "YOUR_KICK_OAUTH_TOKEN"        # Bearer-токен (опционально, для set_*)
    """

    _BASE = "https://kick.com/api/v1"
    _BASE_V2 = "https://kick.com/api/v2"

    def __init__(self, config=None):
        super().__init__(config)
        self.channel = self.config.get("channel", "")
        self.token = self.config.get("token", "")
        self._read_headers = {
            "Accept": "application/json",
            "User-Agent": "StreamTail/1.1",
        }
        self._write_headers = {
            **self._read_headers,
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    # ── Чтение статуса ────────────────────────────────────────────────────────

    async def get_status(self) -> dict:
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.channel:
            logger.warning("KickPlugin: не задан channel в конфиге")
            return status

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._BASE}/channels/{self.channel}",
                    headers=self._read_headers,
                )
                if resp.status_code != 200:
                    logger.warning(f"Kick API: {resp.status_code} для канала {self.channel}")
                    return status

                data = resp.json()
                livestream = data.get("livestream")

                if livestream:
                    status.update(
                        {
                            "is_live": True,
                            "viewers": livestream.get("viewer_count", 0),
                            "title": livestream.get("session_title", ""),
                            "game": (
                                livestream.get("categories", [{}])[0].get("name", "")
                                if livestream.get("categories")
                                else ""
                            ),
                        }
                    )
                else:
                    # Канал оффлайн — берём последние данные
                    status["title"] = data.get("channel", {}).get("description", "")
        except httpx.RequestError as e:
            logger.error(f"Kick: сетевая ошибка: {e}")
        except Exception as e:
            logger.error(f"Kick: неожиданная ошибка в get_status: {e}")

        return status

    # ── Запись ────────────────────────────────────────────────────────────────

    async def set_title(self, title: str) -> str:
        """Меняет название трансляции через Kick API (требует OAuth-токен)."""
        if not self.token:
            return "Kick: токен не задан — смена названия недоступна"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.put(
                    f"{self._BASE_V2}/channels/{self.channel}",
                    headers=self._write_headers,
                    json={"stream_title": title},
                )
                if resp.status_code in (200, 204):
                    return "Kick: Название обновлено"
                return f"Kick Ошибка ({resp.status_code}): {resp.text[:200]}"
        except httpx.RequestError as e:
            return f"Kick: сетевая ошибка — {e}"

    async def set_game(self, game: str) -> str:
        """
        Kick не поддерживает смену категории по имени через публичный API.
        Необходим numeric category_id.
        """
        if not self.token:
            return "Kick: токен не задан — смена категории недоступна"

        # Шаг 1 — поиск категории
        category_id = await self._find_category_id(game)
        if not category_id:
            return f"Kick: категория «{game}» не найдена"

        # Шаг 2 — обновление
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.put(
                    f"{self._BASE_V2}/channels/{self.channel}",
                    headers=self._write_headers,
                    json={"category_id": category_id},
                )
                if resp.status_code in (200, 204):
                    return f"Kick: Категория изменена на «{game}»"
                return f"Kick Ошибка ({resp.status_code}): {resp.text[:200]}"
        except httpx.RequestError as e:
            return f"Kick: сетевая ошибка — {e}"

    async def _find_category_id(self, game: str) -> int | None:
        """Ищет category_id по названию игры через поиск Kick."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._BASE}/categories",
                    params={"name": game},
                    headers=self._read_headers,
                )
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list) and items:
                        return items[0].get("id")
        except Exception as e:
            logger.error(f"Kick: ошибка поиска категории: {e}")
        return None
