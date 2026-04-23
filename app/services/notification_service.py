import asyncio
from app.utils.logger import logger

try:
    from plyer import notification

    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


class NotificationService:
    def __init__(self, event_bus):
        self.cache = {}
        event_bus.subscribe("stream.status_checked", self.on_status_change)

    def _show_toast(self, msg: str):
        """Синхронная функция для запуска в отдельном потоке."""
        try:
            notification.notify(
                title="StreamTail",
                message=msg,
                app_name="StreamTail",
                timeout=5
            )
        except Exception as e:
            logger.debug(f"Plyer не смог показать Toast: {e}")

    async def on_status_change(self, data: dict):
        platform = data.get("platform")
        is_live = data.get("is_live", False)

        prev_status = self.cache.get(platform)
        if prev_status is not None and prev_status != is_live:
            status_str = "В ЭФИРЕ" if is_live else "ОФФЛАЙН"
            msg = f"{platform} теперь {status_str}!"
            logger.info(f"🔔 Уведомление: {msg}")

            if PLYER_AVAILABLE:
                # Отправляем блокирующую задачу в пул потоков, чтобы не фризить Tkinter
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, self._show_toast, msg)

        self.cache[platform] = is_live
