import asyncio
import json
import ssl
import websockets
from app.utils import http_client
from app.utils.logger import logger


class TwitchEventSubClient:
    def __init__(self, plugin):
        self.plugin = plugin
        self._task = None
        self._running = False
        self._session_id = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._websocket_loop())
        logger.info("Twitch EventSub: запущен фоновый real-time клиент веб-сокетов.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Twitch EventSub: real-time клиент остановлен.")

    async def _websocket_loop(self):
        backoff = 5
        while self._running:
            try:
                await self.plugin._ensure_token_valid()
                if not self.plugin.token or not self.plugin.broadcaster_id:
                    await asyncio.sleep(10)
                    continue

                ssl_context = ssl.create_default_context()
                url = "wss://eventsub.wss.twitch.tv/v1"

                # Поддержка обхода блокировок/проксирования для сокета EventSub
                proxy = http_client.get_proxy_settings()
                if proxy:
                    logger.debug(f"Twitch EventSub: туннелирование сокета через прокси-сервер {proxy}")
                    sock = await asyncio.get_running_loop().run_in_executor(
                        None, http_client.connect_via_proxy_sync, "eventsub.wss.twitch.tv", 443, proxy
                    )
                    ws = await websockets.connect(
                        url,
                        sock=sock,
                        ssl=ssl_context,
                        server_hostname="eventsub.wss.twitch.tv"
                    )
                else:
                    ws = await websockets.connect(url, ssl=ssl_context)

                async with ws:
                    backoff = 5
                    async for raw_message in ws:
                        if not self._running:
                            break
                        data = json.loads(raw_message)
                        await self._handle_message(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Twitch EventSub: сбой веб-сокета: {e!r}. Реконнект через {backoff}с...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)

    async def _handle_message(self, data: dict):
        metadata = data.get("metadata", {})
        msg_type = metadata.get("message_type")
        payload = data.get("payload", {})

        if msg_type == "session_welcome":
            session = payload.get("session", {})
            self._session_id = session.get("id")
            logger.info(f"Twitch EventSub: сессия установлена! session_id={self._session_id}")
            # Оформление асинхронных real-time подписок на события канала
            asyncio.create_task(self._subscribe_all())

        elif msg_type == "session_keepalive":
            pass

        elif msg_type == "notification":
            event_type = metadata.get("subscription_type")
            event_data = payload.get("event", {})
            logger.info(f"Twitch EventSub: получено мгновенное уведомление: {event_type}")
            await self._parse_and_emit_event(event_type, event_data)

    async def _subscribe_all(self):
        if not self._session_id:
            return

        # Список необходимых real-time событий Twitch
        subscriptions = [
            {"type": "stream.online", "version": "1"},
            {"type": "stream.offline", "version": "1"},
            {"type": "channel.update", "version": "2"}
        ]

        async with http_client.create_client() as client:
            headers = {
                "Client-Id": self.plugin.token_data.get("client_id", self.plugin.client_id),
                "Authorization": f"Bearer {self.plugin.token}",
                "Content-Type": "application/json"
            }

            for sub in subscriptions:
                payload = {
                    "type": sub["type"],
                    "version": sub["version"],
                    "condition": {
                        "broadcaster_user_id": str(self.plugin.broadcaster_id)
                    },
                    "transport": {
                        "method": "websocket",
                        "session_id": self._session_id
                    }
                }
                try:
                    resp = await client.post(
                        "https://api.twitch.tv/helix/eventsub/subscriptions",
                        headers=headers,
                        json=payload
                    )
                    if resp.status_code in (200, 201, 202):
                        logger.debug(f"Twitch EventSub: подписка на {sub['type']} успешно зарегистрирована")
                    else:
                        logger.error(
                            f"Twitch EventSub: ошибка регистрации {sub['type']} ({resp.status_code}): {resp.text}")
                except Exception as e:
                    logger.error(f"Twitch EventSub: исключение при регистрации подписки {sub['type']}: {e!r}")

    async def _parse_and_emit_event(self, event_type: str, event: dict):
        from app.core.service_container import container
        bus = container.get("event_bus")
        if not bus:
            return

        status = {
            "platform": "Twitch",
            "is_live": False,
            "viewers": 0,
            "title": "",
            "game": ""
        }

        # Быстрый опрос статуса через API Helix, чтобы получить точные метаданные без ожидания
        try:
            status = await self.plugin.get_status()
        except Exception:
            pass

        if event_type == "stream.online":
            status["is_live"] = True
            logger.info("🔔 Twitch EventSub: Канал вышел В ЭФИР (🟢 LIVE)!")
        elif event_type == "stream.offline":
            status["is_live"] = False
            status["viewers"] = 0
            logger.info("🔔 Twitch EventSub: Трансляция ЗАВЕРШЕНА (🔴 ОФФЛАЙН)!")
        elif event_type == "channel.update":
            status["title"] = event.get("title", status["title"])
            status["game"] = event.get("category_name", status["game"])
            logger.info(f"🔔 Twitch EventSub: Смена метаданных: «{status['title']}» | {status['game']}")

        # Мгновенная публикация статуса в шину событий приложения
        bus.emit("stream.status_checked", status)
