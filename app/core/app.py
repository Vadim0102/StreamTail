import asyncio

from app.core.plugin_manager import PluginManager
from app.core.event_bus import EventBus
from app.services.stream_service import StreamService
from app.services.game_service import GameService
from app.services.notification_service import NotificationService
from app.core.scheduler import Scheduler
from app.core.service_container import container
from app.utils.config import load_config
from app.utils.logger import logger
from app.ui.desktop.main_window import StreamTailGUI


class StreamTailApp:
    def __init__(self):
        self.config = load_config()
        self.event_bus = EventBus()
        self.plugin_manager = PluginManager(self.config)

        # Инициализация сервисов (IoC)
        self.stream_service = StreamService(self.plugin_manager)
        self.game_service = GameService(self.config)
        self.notification_service = NotificationService(self.event_bus)

        container.register("stream", self.stream_service)
        container.register("games", self.game_service)
        container.register("config", self.config)

        self.scheduler = Scheduler(self.event_bus, self.plugin_manager)

        # GUI создаётся синхронно. Карточки платформ будут добавлены
        # позже — после события plugins.loaded (см. start_background).
        self.gui = StreamTailGUI(self)

    async def start_background(self):
        """Асинхронная задача, запускаемая вместе с GUI."""
        logger.info("Инициализация сервисов и загрузка плагинов...")
        self.plugin_manager.load_plugins()

        platform_config = self.config.get("platforms", {})
        for name, plugin in self.plugin_manager.all().items():
            if platform_config.get(name.lower(), {}).get("enabled", True):
                plugin.enable()
                logger.info(f"✅ Платформа активирована: {name}")

        # Оповещаем GUI: плагины готовы — можно строить карточки
        self.event_bus.emit(
            "plugins.loaded",
            {"plugins": list(self.plugin_manager.all().keys())},
        )

        interval = self.config.get("app", {}).get("check_interval", 15)
        self.scheduler.start(interval=interval)

        logger.info("Фоновая инициализация завершена. Ожидание действий пользователя.")

    def shutdown(self):
        logger.info("Остановка StreamTail...")
        self.scheduler.stop()
