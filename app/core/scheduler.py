import asyncio
from app.utils.logger import logger

class Scheduler:
    def __init__(self, event_bus, plugin_manager):
        self.event_bus = event_bus
        self.plugin_manager = plugin_manager
        self.running = False
        self._task = None

    def start(self, interval: int = 15):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop(interval))
        logger.info(f"⏱ Планировщик запущен (Интервал: {interval}с)")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("🛑 Планировщик остановлен.")

    async def _loop(self, interval: int):
        while self.running:
            for name, plugin in self.plugin_manager.all().items():
                if plugin.enabled:
                    try:
                        status = await plugin.get_status()
                        status["platform"] = name
                        self.event_bus.emit("stream.status_checked", status)
                    except Exception as e:
                        logger.error(f"Ошибка проверки статуса {name}: {e}")
            await asyncio.sleep(interval)
