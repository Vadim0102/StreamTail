import asyncio
import threading
import time
import pytchat
from app.core.schemas import ChatMessage, ChatAuthor
from app.utils.logger import logger


class YouTubeChatClient:
    def __init__(self, plugin):
        self.plugin = plugin
        self._thread = None
        self._chat_running = False
        self._main_loop = None  # Ссылка на запущенный event loop главного потока

    async def start(self):
        if self._chat_running:
            return
        self._chat_running = True
        self._main_loop = asyncio.get_running_loop()

        # 1. Загружаем начальную историю через API при запуске
        asyncio.create_task(self._load_initial_history())

        # 2. Запускаем фоновый поток для рилтайм-чтения
        self._thread = threading.Thread(target=self._chat_thread_loop, daemon=True)
        self._thread.start()
        logger.info("YouTube Chat: запущен фоновый поток pytchat.")

    async def _load_initial_history(self):
        await asyncio.sleep(2)  # Даем время на определение liveChatId в планировщике
        if not self.plugin.token:
            self._emit_history_loaded()
            return

        logger.info("YouTube Chat: загрузка начальной истории чата...")
        try:
            items = await self.plugin.api_client.fetch_chat_history(self.plugin.broadcast_id)
            if items:
                for item in items:
                    msg = self._parse_api_message(item)
                    if msg:
                        self._emit_message(msg)
        except Exception as e:
            logger.error(f"YouTube Chat: ошибка загрузки истории чата: {e!r}")
        finally:
            self._emit_history_loaded()

    def _emit_history_loaded(self):
        from app.core.service_container import container
        bus = container.get("event_bus")
        if bus:
            bus.emit("chat.history_loaded", {"platform": "youtube"})

    def _parse_api_message(self, item: dict) -> ChatMessage | None:
        try:
            snippet = item.get("snippet", {})
            author_details = item.get("authorDetails", {})

            is_owner = author_details.get("isChatOwner", False)
            is_mod = author_details.get("isChatModerator", False) or is_owner
            is_sub = author_details.get("isChatSponsor", False)

            badges = []
            if is_owner:
                badges.append("owner")
            elif is_mod:
                badges.append("moderator")
            if is_sub:
                badges.append("subscriber")

            author_id = author_details.get("channelId", "")
            author_name = author_details.get("displayName", "Anonymous")

            if author_name.startswith("@"):
                author_name = author_name[1:]

            author = ChatAuthor(
                id=author_id,
                name=author_name,
                avatar_url=author_details.get("profileImageUrl"),
                is_mod=is_mod,
                is_sub=is_sub,
                is_owner=is_owner,
                badges=badges
            )

            published_at = snippet.get("publishedAt", "")
            try:
                import datetime
                ts_str = published_at.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(ts_str)
                timestamp = int(dt.timestamp() * 1000)
            except Exception:
                timestamp = int(time.time() * 1000)

            msg_text = snippet.get("textMessageDetails", {}).get("messageText", "") if "textMessageDetails" in snippet else snippet.get("displayMessage", "")
            msg_id = item.get("id", "")

            return ChatMessage(
                id=msg_id,
                platform="youtube",
                author=author,
                text=msg_text,
                timestamp=timestamp
            )
        except Exception as e:
            logger.error(f"YouTube Chat: ошибка парсинга сообщения из истории: {e!r}")
            return None

    def _parse_message(self, c) -> ChatMessage | None:
        try:
            author_obj = c.author
            badges_list = []

            is_owner = getattr(author_obj, "isChatOwner", False)
            is_mod = getattr(author_obj, "isChatModerator", False) or is_owner
            is_sub = getattr(author_obj, "isChatSponsor", False)

            message_text = getattr(c, "message", "")
            if is_owner and message_text in self.plugin._sent_messages_cache:
                self.plugin._sent_messages_cache.remove(message_text)
                logger.debug(f"YouTube Chat: отфильтровано дублирующее собственное сообщение: '{message_text}'")
                return None

            if is_owner:
                badges_list.append("owner")
            elif is_mod:
                badges_list.append("moderator")
            if is_sub:
                badges_list.append("subscriber")

            author_id = getattr(author_obj, "channelId", "")
            author = ChatAuthor(
                id=author_id,
                name=getattr(author_obj, "name", "Anonymous"),
                avatar_url=getattr(author_obj, "imageUrl", None),
                is_mod=is_mod,
                is_sub=is_sub,
                is_owner=is_owner,
                badges=badges_list
            )

            timestamp = getattr(c, "timestamp", int(time.time() * 1000))
            msg_id = getattr(c, "id", f"yt_{int(time.time() * 1000)}")

            return ChatMessage(
                id=msg_id,
                platform="youtube",
                author=author,
                text=message_text,
                timestamp=timestamp
            )
        except Exception as e:
            logger.error(f"YouTube Chat: ошибка парсинга сообщения pytchat: {e!r}")
            return None

    def _emit_message(self, msg: ChatMessage):
        # Перенос мутации словаря кэша в главный поток для предотвращения Data Race
        if msg.id:
            self.plugin._chat_history_cache[msg.id] = {
                "author_id": msg.author.id,
                "text": msg.text,
                "timestamp": msg.timestamp
            }
            if len(self.plugin._chat_history_cache) > 150:
                first_key = next(iter(self.plugin._chat_history_cache))
                self.plugin._chat_history_cache.pop(first_key, None)

        from app.core.service_container import container
        bus = container.get("event_bus")
        if bus:
            bus.emit("chat.message_received", msg.to_dict())

    async def stop(self):
        self._chat_running = False
        logger.info("YouTube Chat: остановка фонового потока pytchat.")

    def _chat_thread_loop(self):
        backoff = 5

        while self._chat_running:
            broadcast_id = self.plugin.broadcast_id
            if not broadcast_id:
                time.sleep(5)
                continue

            logger.info(f"YouTube Chat: мгновенное подключение к трансляции ID={broadcast_id}...")
            try:
                chat = pytchat.create(video_id=broadcast_id, interruptable=False)

                while self._chat_running and chat.is_alive():
                    data = chat.get()
                    if data and data.items:
                        for c in data.items:
                            msg = self._parse_message(c)
                            if msg:
                                self._main_loop.call_soon_threadsafe(self._emit_message, msg)

                    time.sleep(0.1)

                backoff = 5

            except Exception as e:
                logger.error(f"YouTube Chat: ошибка в потоке чтения чата: {e!r}. Реконнект через {backoff}с...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                logger.debug("YouTube Chat: поток чтения завершил итерацию.")
                time.sleep(5)  # Защитная пауза перед созданием нового объекта подключения

