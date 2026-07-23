import asyncio
import time
from app.core.schemas import ChatMessage, ChatAuthor
from app.utils import http_client
from app.utils.logger import logger


class RutubeChatClient:
    """Асинхронный клиент чата RUTUBE (Poll & Send API на основе HTTP/2)."""

    def __init__(self, plugin):
        self.plugin = plugin
        self._task = None
        self._running = False
        self._last_timestamp = "0"
        self._processed_msg_ids = set()

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("RUTUBE Chat: запущен фоновый опрос чата.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("RUTUBE Chat: опрос чата остановлен.")

    async def send_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        """Отправка текстового сообщения в чат RUTUBE."""
        if not self.plugin.token:
            logger.warning("RUTUBE Chat: Нет токена/кук для отправки сообщения.")
            return False

        broadcast_id = await self._resolve_broadcast_id()
        if not broadcast_id:
            logger.warning("RUTUBE Chat: Не удалось определить ID трансляции для отправки.")
            return False

        url = f"https://rutube.ru/api/chat/{broadcast_id}/"
        headers = dict(self.plugin.headers)
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://rutube.ru"
        headers["Referer"] = f"https://rutube.ru/live/chat/{broadcast_id}/"

        payload = {"text": text}
        if reply_parent_msg_id:
            payload["parent_id"] = str(reply_parent_msg_id)

        try:
            async with http_client.create_client(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    msg_id = data.get("id")
                    if msg_id:
                        self.plugin._last_real_id = str(msg_id)
                        self._processed_msg_ids.add(str(msg_id))
                    return True
                else:
                    logger.error(
                        f"RUTUBE Chat: ошибка отправки (HTTP {resp.status_code}): {resp.text[:150]}"
                    )
        except Exception as e:
            logger.error(f"RUTUBE Chat: исключение при отправке сообщения: {e!r}")

        return False

    async def _resolve_broadcast_id(self) -> str:
        """Определяет актуальный broadcast_id для подключения к чату."""
        bid = self.plugin.broadcast_id
        if bid:
            return bid

        try:
            broadcasts = await self.plugin.get_broadcasts()
            if broadcasts:
                for b in broadcasts:
                    if b.get("status") in ("live", "actual"):
                        return b["id"]
                return broadcasts[0]["id"]
        except Exception as e:
            logger.debug(f"RUTUBE Chat: ошибка автоопределения broadcast_id: {e!r}")

        return ""

    async def _poll_loop(self):
        backoff = 3
        initial_history_loaded = False

        while self._running:
            try:
                broadcast_id = await self._resolve_broadcast_id()
                if not broadcast_id:
                    await asyncio.sleep(5)
                    continue

                if not initial_history_loaded:
                    await self._fetch_initial_history(broadcast_id)
                    initial_history_loaded = True

                await self._poll_chat(broadcast_id)
                backoff = 3
                await asyncio.sleep(3)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"RUTUBE Chat: ошибка опроса: {e!r}. Реконнект через {backoff}с...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _fetch_initial_history(self, broadcast_id: str):
        """Загружает начальное состояние чата при старте."""
        url = f"https://rutube.ru/api/chat/{broadcast_id}"
        params = {
            "time": "0",
            "direction": "present",
            "format": "json",
            "only_active": "true"
        }
        try:
            async with http_client.create_client(timeout=10.0) as client:
                resp = await client.get(url, headers=self.plugin.headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    self._last_timestamp = str(data.get("timestamp") or "0")
                    results = data.get("results", []) or []
                    self._process_results(results)
        except Exception as e:
            logger.debug(f"RUTUBE Chat: ошибка выгрузки истории чата: {e!r}")
        finally:
            from app.core.service_container import container
            bus = container.get("event_bus")
            if bus:
                bus.emit("chat.history_loaded", {"platform": "rutube"})

    async def _poll_chat(self, broadcast_id: str):
        """Регулярный опрос новых сообщений."""
        url = f"https://rutube.ru/api/chat/{broadcast_id}"
        params = {
            "time": self._last_timestamp,
            "direction": "present",
            "format": "json",
            "only_active": "true"
        }
        async with http_client.create_client(timeout=10.0) as client:
            resp = await client.get(url, headers=self.plugin.headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                new_ts = data.get("timestamp")
                if new_ts and new_ts != "0":
                    self._last_timestamp = str(new_ts)

                results = data.get("results", []) or []
                self._process_results(results)

    def _process_results(self, results: list):
        from app.core.service_container import container
        bus = container.get("event_bus")
        if not bus:
            return

        for item in results:
            if not isinstance(item, dict):
                continue

            payload = item.get("payload") if "payload" in item else item
            if not isinstance(payload, dict):
                continue

            msg_id = str(payload.get("id") or "")
            if not msg_id or msg_id in self._processed_msg_ids:
                continue

            self._processed_msg_ids.add(msg_id)
            if len(self._processed_msg_ids) > 1000:
                self._processed_msg_ids.clear()

            text = payload.get("text", "").strip()
            if not text:
                continue

            user_data = payload.get("user") or {}
            user_id = str(user_data.get("id") or "")
            user_name = user_data.get("name") or "Anonymous"
            avatar_url = user_data.get("avatar_url")

            channel_id = str(self.plugin.channel_id)
            is_owner = (user_id == channel_id) or user_data.get("is_official", False)
            badges = []
            if is_owner:
                badges.append("owner")

            author = ChatAuthor(
                id=user_id,
                name=user_name,
                avatar_url=avatar_url,
                is_owner=is_owner,
                is_mod=is_owner,
                badges=badges
            )

            created_ts_real = payload.get("created_ts_real") or item.get("created_ts_real")
            if created_ts_real:
                try:
                    timestamp = int(float(created_ts_real) * 1000)
                except Exception:
                    timestamp = int(time.time() * 1000)
            else:
                timestamp = int(time.time() * 1000)

            chat_msg = ChatMessage(
                id=msg_id,
                platform="rutube",
                author=author,
                text=text,
                timestamp=timestamp
            )

            bus.emit("chat.message_received", chat_msg.to_dict())
