class NotificationService:
    def __init__(self, event_bus, logger):
        self.logger = logger
        event_bus.subscribe("stream_status_checked", self.on_status_change)

    def on_status_change(self, data):
        platform = data.get("platform")
        is_live = data.get("is_live", False)
        viewers = data.get("viewers", 0)
        status = "В ЭФИРЕ" if is_live else "ОФФЛАЙН"
        self.logger.info(f"Уведомление: {platform} сейчас {status} (Зрителей: {viewers})")
