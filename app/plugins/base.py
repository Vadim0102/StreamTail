# app/plugins/base.py
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
        pass

    @abstractmethod
    async def set_title(self, title: str) -> str:
        pass

    @abstractmethod
    async def set_game(self, game: str) -> str:
        pass

    async def create_stream(self, title: str, game: str = "", description: str = "") -> dict:
        return {"success": False, "error": f"Платформа {self.name} не поддерживает прямое создание стримов."}

    async def publish_stream(self) -> str:
        return f"Платформа {self.name} не поддерживает публикацию через API."

    async def stop_stream(self) -> str:
        return f"Платформа {self.name} не поддерживает завершение трансляций через API."

    async def upload_thumbnail(self, image_path: str) -> str:
        return f"Платформа {self.name} не поддерживает загрузку превью через API."

    # ── Методы чата ──

    async def start_chat_listener(self):
        """Запуск фоновой задачи чтения чата платформы."""
        pass

    async def stop_chat_listener(self):
        """Остановка фоновой задачи чтения чата платформы."""
        pass

    async def send_chat_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        """Отправка сообщения в чат платформы (с возможностью ответа в тред)."""
        return False

    async def delete_chat_message(self, message_id: str) -> bool:
        """Удаление сообщения из чата (модерация)."""
        return False

    async def ban_chat_user(self, user_id: str, reason: str = "", duration: int = None) -> bool:
        """Блокировка или тайм-аут пользователя на платформе."""
        return False

    async def pin_chat_message(self, message_id: str, duration: int = None) -> bool:
        """Закрепление сообщения в чате платформы."""
        return False
