import threading
import time

class Scheduler:
    def __init__(self, event_bus, plugin_manager):
        self.event_bus = event_bus
        self.plugin_manager = plugin_manager
        self.running = False
        self._thread = None

    def start(self, interval=30):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def _loop(self, interval):
        while self.running:
            # Получаем расширенный статус всех платформ
            for name, plugin in self.plugin_manager.all().items():
                if plugin.enabled:
                    status = plugin.execute("get_status")
                    if isinstance(status, dict):
                        status["platform"] = name
                        self.event_bus.emit("stream_status_checked", status)
            time.sleep(interval)
