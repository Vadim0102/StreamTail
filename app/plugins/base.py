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
