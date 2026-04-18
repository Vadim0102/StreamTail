from app.core.plugin_manager import PluginManager
from app.core.event_bus import EventBus
from app.services.stream_service import StreamService
from app.services.game_service import GameService
from app.services.notification_service import NotificationService
from app.core.scheduler import Scheduler
from app.core.service_container import container
from app.utils.config import load_config
from app.utils.logger import setup_logger


class StreamTailApp:
    def __init__(self):
        self.config = load_config()
        self.logger = setup_logger()

        self.event_bus = EventBus()
        self.plugin_manager = PluginManager(self.config)

        # Регистрация сервисов
        self.stream_service = StreamService(self.plugin_manager)
        self.game_service = GameService(self.config)
        self.notification_service = NotificationService(self.event_bus, self.logger)

        container.register("stream", self.stream_service)
        container.register("games", self.game_service)

        self.scheduler = Scheduler(self.event_bus, self.plugin_manager)

    def bootstrap(self):
        self.logger.info("Загрузка плагинов...")
        self.plugin_manager.load_plugins()

        # Включаем плагины согласно конфигу
        platform_config = self.config.get("platforms", {})
        for name, plugin in self.plugin_manager.all().items():
            if platform_config.get(name.lower(), {}).get("enabled", True):
                plugin.enable()

    def run(self):
        self.bootstrap()

        interval = self.config.get("app", {}).get("check_interval", 10)
        self.scheduler.start(interval=interval)

        from app.ui.desktop.main_window import StreamTailGUI
        gui = StreamTailGUI(self)
        try:
            gui.run()
        finally:
            self.logger.info("Остановка приложения...")
            self.scheduler.stop()
