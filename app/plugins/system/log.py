from app.plugins.base import BasePlugin
from app.utils.logger import logger

class SystemLoggerPlugin(BasePlugin):
    """Системный плагин для аудита событий."""

    def __init__(self, config=None):
        super().__init__(config)
        self.name = "SystemLogger"

    async def get_status(self):
        return {"is_live": True, "viewers": 999, "title": "System Audit", "game": "Hacking"}

    async def set_title(self, title):
        logger.info(f"[AUDIT] Смена названия: {title}")
        return "Аудит: Лог записан"

    async def set_game(self, game):
        logger.info(f"[AUDIT] Смена игры: {game}")
        return "Аудит: Лог записан"
