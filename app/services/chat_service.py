# app/services/chat_service.py
import asyncio
import time
import traceback
from collections import OrderedDict
from app.core.schemas import ChatMessage, ChatAuthor
from app.utils.logger import logger
from app.core.service_container import container


class ChatService:
    def __init__(self, plugin_manager, event_bus):
        self.plugin_manager = plugin_manager
        self.event_bus = event_bus
        self.seen_ids = OrderedDict()
        self.max_cache_size = 1000

        # Подписываемся на сырые сообщения от плагинов
        self.event_bus.subscribe("chat.message_received", self.on_message_received)

    def is_duplicate(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        if msg_id in self.seen_ids:
            return True
        self.seen_ids[msg_id] = True
        if len(self.seen_ids) > self.max_cache_size:
            self.seen_ids.popitem(last=False)
        return False

    async def on_message_received(self, data: dict):
        msg_id = data.get("id")
        if msg_id and self.is_duplicate(msg_id):
            return

        text = data.get("text", "")
        # Пример парсинга простейшей команды в чате
        if text.startswith("!"):
            asyncio.create_task(self._handle_command(data))

    async def _handle_command(self, data: dict):
        text = data.get("text", "")
        platform = data.get("platform")
        author_name = data.get("author", {}).get("name", "User")

        parts = text.split(" ", 1)
        cmd = parts[0].lower()

        if cmd == "!ping":
            reply = f"@{author_name}, Pong! StreamTail Мультичат работает исправно."
            await self.send_message(platform, reply)

    async def send_message(self, platform: str, text: str, reply_parent_id: str = None) -> bool:
        plugin = self.plugin_manager.get(platform)
        if plugin and plugin.enabled:
            if hasattr(plugin, "send_chat_message"):
                logger.debug(f"ChatService: Отправка сообщения на платформу '{platform}': {text} (reply={reply_parent_id})")
                res = await plugin.send_chat_message(text, reply_parent_msg_id=reply_parent_id)
                if res:
                    logger.info(f"ChatService: Сообщение успешно доставлено на '{platform}'")
                    await self._echo_locally(platform, text)
                    return True
                else:
                    logger.warning(f"ChatService: Платформа '{platform}' отклонила отправку сообщения")
            else:
                logger.warning(f"ChatService: Плагин '{platform}' не поддерживает отправку сообщений в чат")
        else:
            logger.warning(f"ChatService: Плагин '{platform}' не найден или отключен")
        return False

    async def pin_message(self, platform: str, message_id: str, duration: int = None) -> bool:
        """Закрепляет сообщение на указанной платформе."""
        plugin = self.plugin_manager.get(platform)
        if plugin and plugin.enabled and hasattr(plugin, "pin_chat_message"):
            logger.debug(f"ChatService: Закрепление сообщения {message_id} на '{platform}'")
            return await plugin.pin_chat_message(message_id, duration)
        return False

    async def send_global_message(self, text: str):
        """Отправка сообщения на все активные стримы одновременно."""
        logger.debug(f"ChatService: Массовая отправка сообщения во все активные чаты: {text}")
        tasks = []
        for name, plugin in self.plugin_manager.all().items():
            if plugin.enabled and hasattr(plugin, "send_chat_message"):
                async def send_and_echo(p_name=name, p_plugin=plugin):
                    res = await p_plugin.send_chat_message(text)
                    if res:
                        # Принудительно приводим имя платформы к нижнему регистру при эхе
                        await self._echo_locally(p_name.lower(), text)
                tasks.append(send_and_echo())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def delete_message(self, platform: str, message_id: str) -> bool:
        """Удаление конкретного сообщения (модерация)."""
        plugin = self.plugin_manager.get(platform)
        if plugin and plugin.enabled and hasattr(plugin, "delete_chat_message"):
            return await plugin.delete_chat_message(message_id)
        return False

    async def ban_user(self, platform: str, user_id: str, reason: str = "", duration: int = None) -> bool:
        """Блокировка или тайм-аут пользователя на платформе."""
        plugin = self.plugin_manager.get(platform)
        if plugin and plugin.enabled and hasattr(plugin, "ban_chat_user"):
            return await plugin.ban_chat_user(user_id, reason, duration)
        return False

    async def _echo_locally(self, platform: str, text: str):
        """Локальное эхо отправленного сообщения (так как IRC не возвращает собственные сообщения)."""
        try:
            platform = platform.lower()  # Принудительно в нижний регистр
            author_name = "Вы"
            plugin = self.plugin_manager.get(platform)
            if plugin and hasattr(plugin, "_fetch_user_login"):
                try:
                    login = await plugin._fetch_user_login()
                    if login:
                        author_name = login
                except Exception as ex:
                    logger.debug(f"ChatService: Не удалось получить имя для эха: {ex!r}")

            msg_id = f"echo_{platform}_{int(time.time() * 1000)}"

            if plugin and hasattr(plugin, "register_sent_echo"):
                plugin.register_sent_echo(msg_id)

            echo_msg = ChatMessage(
                id=msg_id,
                platform=platform,
                author=ChatAuthor(
                    id="local_broadcaster",
                    name=author_name,
                    is_owner=True,
                    is_mod=True,
                    badges=["owner"]
                ),
                text=text,
                timestamp=int(time.time() * 1000)
            )

            self.event_bus.emit("chat.message_received", echo_msg.to_dict())
        except Exception as e:
            logger.error(f"ChatService: Ошибка в _echo_locally: {e!r}")
            logger.error(traceback.format_exc())
