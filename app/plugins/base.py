from abc import ABC, abstractmethod
from typing import Dict, Any

class BasePlugin(ABC):
    def __init__(self, config: dict = None):
        self.enabled = False
        self.config = config or {}
        self.name = self.__class__.__name__.replace("Plugin", "")

    def enable(self):
        self.enabled = True

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Возвращает: {'is_live': bool, 'viewers': int, 'title': str, 'game': str}"""
        pass

    @abstractmethod
    async def set_title(self, title: str) -> str:
        """Меняет название стрима."""
        pass

    @abstractmethod
    async def set_game(self, game: str) -> str:
        """Меняет категорию/игру стрима."""
        pass

    async def create_stream(self, title: str, game: str = "", description: str = "") -> dict:
        """Создает новый стрим на платформе. Возвращает dict с результатом."""
        return {"success": False, "error": f"Платформа {self.name} не поддерживает прямое создание стримов."}

    async def publish_stream(self) -> str:
        """Переводит стрим из приватного состояния подготовки в публичный эфир."""
        return f"Платформа {self.name} не поддерживает публикацию через API."

    async def stop_stream(self) -> str:
        """Останавливает (завершает) трансляцию на платформе."""
        return f"Платформа {self.name} не поддерживает завершение трансляций через API."

    async def upload_thumbnail(self, image_path: str) -> str:
        """Загружает обложку-превью для текущей трансляции."""
        return f"Платформа {self.name} не поддерживает загрузку превью через API."
