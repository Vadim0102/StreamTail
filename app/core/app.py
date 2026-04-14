from app.core.plugin_manager import PluginManager
from app.core.event_bus import EventBus
from app.services.stream_service import StreamService
from app.core.scheduler import Scheduler


class StreamTailApp:
    def __init__(self):
        self.event_bus = EventBus()
        self.plugin_manager = PluginManager()
        self.stream_service = StreamService(self.plugin_manager)

        # Инициализируем планировщик
        self.scheduler = Scheduler(self.event_bus, self.plugin_manager)

    def bootstrap(self):
        print("[StreamTail] Инициализация ядра...")
        self.plugin_manager.load_plugins()
        print(f"[StreamTail] Доступные платформы: {', '.join(self.plugin_manager.all().keys())}")

    def run(self):
        self.bootstrap()

        # Запускаем фоновую проверку статусов стрима (каждые 10 секунд)
        self.scheduler.start(interval=10)
        print("[StreamTail] Планировщик запущен.")

        # Запускаем GUI
        # Импортируем здесь, чтобы избежать циклических импортов на старте
        from app.ui.desktop.main_window import StreamTailGUI

        gui = StreamTailGUI(self)
        try:
            print("[StreamTail] Запуск графического интерфейса...")
            gui.run()
        finally:
            # При закрытии окна корректно останавливаем фоновые потоки
            print("[StreamTail] Остановка сервисов...")
            self.scheduler.stop()
