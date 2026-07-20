import asyncio
import time
from app.utils.logger import logger


class Scheduler:
    def __init__(self, event_bus, plugin_manager):
        self.event_bus = event_bus
        self.plugin_manager = plugin_manager
        self.running = False
        self._task = None
        self._failures = {}  # Счетчик подряд идущих ошибок по каждой платформе
        self._next_allowed_check = {}  # Время следующей разрешенной проверки по платформе

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
            current_interval = self.plugin_manager.config.get("app", {}).get("check_interval", interval)
            now = time.time()

            tasks = []
            for name, plugin in self.plugin_manager.all().items():
                if plugin.enabled:
                    # Проверка на экспоненциальный откат (Backoff-таймаут)
                    allowed_time = self._next_allowed_check.get(name, 0)
                    if now < allowed_time:
                        logger.debug(
                            f"Планировщик: опрос {name} отложен по защите backoff до {time.strftime('%H:%M:%S', time.localtime(allowed_time))}")
                        continue

                    # Выделенная задача для изолированного опроса
                    async def check_single(p_name=name, p_plugin=plugin):
                        try:
                            status = await p_plugin.get_status()
                            status["platform"] = p_name
                            self.event_bus.emit("stream.status_checked", status)

                            # Сброс штрафных очков при успешном выполнении
                            self._failures[p_name] = 0
                            self._next_allowed_check[p_name] = 0
                        except Exception as e:
                            consecutive_failures = self._failures.get(p_name, 0) + 1
                            self._failures[p_name] = consecutive_failures

                            # Расчет штрафного интервала: interval * 2^failures (максимум 10 минут)
                            penalty = min(current_interval * (2 ** consecutive_failures), 600)
                            self._next_allowed_check[p_name] = time.time() + penalty

                            logger.error(
                                f"Ошибка проверки статуса {p_name} (сбой {consecutive_failures}): {e!r}. "
                                f"Запросы к платформе приостановлены на {penalty}с."
                            )

                    tasks.append(check_single())

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(current_interval)
