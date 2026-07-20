import asyncio

from app.core.plugin_manager import PluginManager
from app.core.event_bus import EventBus
from app.services.stream_service import StreamService
from app.services.game_service import GameService
from app.services.notification_service import NotificationService
from app.services.chat_service import ChatService
from app.core.scheduler import Scheduler
from app.core.service_container import container
from app.utils.config import load_config, save_config
from app.utils.logger import logger
from app.ui.desktop.main_window import StreamTailGUI
from app.ui.web.api import start_web_server


class StreamTailApp:
    def __init__(self):
        self._is_shutdown = False
        self.config = load_config()
        self.event_bus = EventBus()
        self.plugin_manager = PluginManager(self.config)

        self.stream_service = StreamService(self.plugin_manager)
        self.game_service = GameService(self.config, self.plugin_manager)
        self.notification_service = NotificationService(self.event_bus)

        container.register("event_bus", self.event_bus)
        container.register("stream", self.stream_service)
        container.register("games", self.game_service)
        container.register("config", self.config)

        self.chat_service = ChatService(self.plugin_manager, self.event_bus)
        container.register("chat", self.chat_service)

        self.scheduler = Scheduler(self.event_bus, self.plugin_manager)
        self.gui = StreamTailGUI(self)

    async def start_background(self):
        logger.info("Инициализация сервисов и загрузка плагинов...")
        self.plugin_manager.load_plugins()

        start_web_server(self)

        from app.ui.web.api import broadcast_chat_message_to_web
        self.event_bus.subscribe(
            "chat.message_received",
            lambda data: asyncio.create_task(broadcast_chat_message_to_web(data))
        )

        self.event_bus.subscribe(
            "chat.message_id_updated",
            lambda data: asyncio.create_task(broadcast_chat_message_to_web({
                "action": "update_id",
                "platform": data["platform"],
                "old_id": data["old_id"],
                "new_id": data["new_id"]
            }))
        )

        self.event_bus.subscribe(
            "chat.message_deleted",
            lambda data: asyncio.create_task(broadcast_chat_message_to_web({
                "action": "delete",
                "platform": data["platform"],
                "msg_id": data["msg_id"]
            }))
        )

        self.event_bus.subscribe(
            "chat.user_banned",
            lambda data: asyncio.create_task(broadcast_chat_message_to_web({
                "action": "ban_user",
                "platform": data["platform"],
                "username": data["username"]
            }))
        )

        platform_config = self.config.get("platforms", {})
        for name, plugin in self.plugin_manager.all().items():
            if platform_config.get(name.lower(), {}).get("enabled", True):
                plugin.enable()
                if hasattr(plugin, "start_chat_listener"):
                    asyncio.create_task(plugin.start_chat_listener())

        self.event_bus.emit("plugins.loaded", {"plugins": list(self.plugin_manager.all().keys())})

        self.scheduler.start(interval=self.config.get("app", {}).get("check_interval", 15))
        logger.info("Фоновая инициализация завершена.")

    def update_app_config(self, new_config: dict):
        self.config = new_config
        save_config(new_config)

        platform_config = self.config.get("platforms", {})
        for name, plugin in self.plugin_manager.all().items():
            plugin_cfg = platform_config.get(name.lower(), {})
            plugin.config = plugin_cfg
            if plugin_cfg.get("enabled", True):
                plugin.enable()
                if hasattr(plugin, "start_chat_listener"):
                    asyncio.create_task(plugin.start_chat_listener())
            else:
                plugin.enabled = False
                if hasattr(plugin, "stop_chat_listener"):
                    asyncio.create_task(plugin.stop_chat_listener())

    async def shutdown_async(self):
        """Асинхронная процедура последовательного, гарантированного освобождения системных ресурсов."""
        if self._is_shutdown:
            return
        self._is_shutdown = True

        logger.info("Остановка StreamTail...")
        self.scheduler.stop()

        # 1. Плавный останов Uvicorn
        from app.ui.web.api import stop_web_server
        try:
            await stop_web_server()
        except Exception as e:
            logger.debug(f"Ошибка при останове веб-сервера: {e!r}")

        # 2. Закрытие глобального пула HTTP-соединений общего HTTP-клиента
        from app.utils.http_client import close_shared_client
        try:
            await close_shared_client()
        except Exception as e:
            logger.debug(f"Ошибка при закрытии HTTP-пула соединений: {e!r}")

        # 3. Остановка слушателей чата и фонового EventSub веб-сокета
        stop_tasks = []
        for name, plugin in self.plugin_manager.all().items():
            if hasattr(plugin, "stop_chat_listener"):
                stop_tasks.append(plugin.stop_chat_listener())
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

    def shutdown(self):
        """Синхронный фасад закрытия (например, для блока finally при аварийном завершении)."""
        if self._is_shutdown:
            return

        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                loop.run_until_complete(self.shutdown_async())
                return
        except Exception:
            pass

        # Резервный синхронный фолбек при недоступности Event Loop
        self._is_shutdown = True
        self.scheduler.stop()
        for name, plugin in self.plugin_manager.all().items():
            if hasattr(plugin, "_chat_running"):
                plugin._chat_running = False
