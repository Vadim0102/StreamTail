from app.utils.logger import logger

try:
    from plyer import notification

    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


class NotificationService:
    def __init__(self, event_bus):
        self.cache = {}  # Кэш статусов, чтобы не спамить уведомлениями
        event_bus.subscribe("stream.status_checked", self.on_status_change)

    async def on_status_change(self, data: dict):
        platform = data.get("platform")
        is_live = data.get("is_live", False)
        viewers = data.get("viewers", 0)

        status_str = "В ЭФИРЕ" if is_live else "ОФФЛАЙН"

        # Уведомляем только при смене состояния
        prev_status = self.cache.get(platform)
        if prev_status is not None and prev_status != is_live:
            msg = f"{platform} теперь {status_str}!"
            logger.info(f"🔔 Уведомление: {msg}")

            if PLYER_AVAILABLE:
                try:
                    notification.notify(
                        title="StreamTail",
                        message=msg,
                        app_name="StreamTail",
                        timeout=5
                    )
                except Exception as e:
                    logger.debug(f"Plyer не смог показать Toast: {e}")

        self.cache[platform] = is_live
