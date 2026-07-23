import asyncio
import json
import ssl
import time
import websockets
from app.core.schemas import ChatMessage, ChatAuthor
from app.utils import http_client
from app.utils.logger import logger


class GoodGameChatClient:
    """Асинхронный клиент чата GoodGame (WebSocket Chat2 Protocol на базе OAuth2)."""

    def __init__(self, plugin):
        self.plugin = plugin
        self._task = None
        self._ping_task = None
        self._running = False
        self._ws = None
        self._channel_id = None
        self._user_id = None
        self._chat_token = None
        self._is_authenticated = False
        self._processed_msg_ids = set()

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._websocket_loop())
        logger.info("GoodGame Chat: запущен фоновый WebSocket-слушатель.")

    async def stop(self):
        self._running = False
        self._is_authenticated = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None

        if self._task:
            self._task.cancel()
            self._task = None

        logger.info("GoodGame Chat: WebSocket-слушатель остановлен.")

    async def _resolve_channel_and_user_id(self):
        """Запрашивает ID канала (стрима), user_id и логин с сервера GoodGame по OAuth токену."""
        if self.plugin.token:
            try:
                async with http_client.create_client(timeout=10.0) as client:
                    resp = await client.get("https://goodgame.ru/api/4/user", headers=self.plugin.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        uid = data.get("id") or data.get("user_id")
                        if uid:
                            self._user_id = int(uid)

                        c_tok = data.get("chat_token") or data.get("token") or self.plugin.token
                        if c_tok:
                            self._chat_token = c_tok

                        sid = data.get("stream_id") or data.get("stream", {}).get("id") or data.get("channel", {}).get(
                            "id")
                        if sid:
                            self._channel_id = str(sid)

                        uname = data.get("username") or data.get("name")
                        if uname:
                            self.plugin._cached_user_login = uname
            except Exception as e:
                logger.debug(f"GoodGame Chat: Ошибка получения профиля пользователя: {e!r}")

        if not self._channel_id:
            try:
                async with http_client.create_client(timeout=10.0) as client:
                    self._channel_id = await self.plugin._get_stream_id(client)
            except Exception as e:
                logger.debug(f"GoodGame Chat: Ошибка получения channel_id: {e!r}")

        return self._channel_id

    async def _attempt_reauth(self) -> bool:
        """Динамическая авторизация сокета на лету с использованием OAuth2 токена."""
        if not self._ws or not self.plugin.token:
            return False

        await self._resolve_channel_and_user_id()
        effective_token = self._chat_token or self.plugin.token

        if not self._user_id or not effective_token:
            logger.warning("GoodGame Chat: Отсутствует user_id или OAuth токен.")
            return False

        auth_msg = {
            "type": "auth",
            "data": {
                "user_id": int(self._user_id),
                "token": str(effective_token)
            }
        }
        try:
            logger.info(f"GoodGame Chat: Отправка запроса auth (user_id={self._user_id})...")
            await self._ws.send(json.dumps(auth_msg))

            for _ in range(15):
                await asyncio.sleep(0.1)
                if self._is_authenticated:
                    return True
        except Exception as e:
            logger.error(f"GoodGame Chat: Ошибка авторизации: {e!r}")

        return self._is_authenticated

    async def send_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        """Отправляет сообщение в чат GoodGame."""
        if not self._ws or not self._running:
            logger.warning("GoodGame Chat: Сокет-соединение не установлено.")
            return False

        if not self.plugin.token:
            logger.warning("GoodGame Chat: Требуется авторизация во вкладке 'Авторизация'!")
            return False

        if not self._is_authenticated:
            logger.info("GoodGame Chat: Выполняется авторизация сессии...")
            authed = await self._attempt_reauth()
            if not authed:
                logger.warning("GoodGame Chat: Авторизация отклонена сервером. Отправка отменена.")
                return False

        if not self._channel_id:
            await self._resolve_channel_and_user_id()

        if not self._channel_id:
            logger.warning("GoodGame Chat: Не удалось определить channel_id.")
            return False

        channel_param = int(self._channel_id) if str(self._channel_id).isdigit() else str(self._channel_id)

        payload = {
            "type": "send_message",
            "data": {
                "channel_id": channel_param,
                "text": text,
                "hideIcon": False,
                "mobile": False
            }
        }

        try:
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
            self.plugin._last_real_id = f"gg_{int(time.time() * 1000)}"

            # Сохраняем строку в кэш отправленных сообщений для исключения эхо-дублей
            self.plugin._sent_messages_cache.append(text)
            if len(self.plugin._sent_messages_cache) > 20:
                self.plugin._sent_messages_cache.pop(0)

            logger.info(f"GoodGame Chat: Сообщение отправлено в канал {self._channel_id}")
            return True
        except Exception as e:
            logger.error(f"GoodGame Chat: ошибка отправки: {e!r}")
            return False

    async def _ping_loop(self):
        while self._running and self._ws:
            try:
                await asyncio.sleep(30)
                if self._ws:
                    await self._ws.send(json.dumps({"type": "ping", "data": {}}))
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _send_initial_commands(self):
        if not self._ws:
            return

        channel_id = await self._resolve_channel_and_user_id()
        if not channel_id:
            return

        channel_param = int(channel_id) if str(channel_id).isdigit() else str(channel_id)
        effective_token = self._chat_token or self.plugin.token

        # 1. Авторизация
        if self._user_id and effective_token:
            auth_msg = {
                "type": "auth",
                "data": {
                    "user_id": int(self._user_id),
                    "token": str(effective_token)
                }
            }
            await self._ws.send(json.dumps(auth_msg))
            await asyncio.sleep(0.2)

        # 2. Вход в канал
        join_msg = {
            "type": "join",
            "data": {
                "channel_id": channel_param,
                "hidden": False
            }
        }
        await self._ws.send(json.dumps(join_msg))
        await asyncio.sleep(0.2)

        # 3. Запрос истории чата
        history_msg = {
            "type": "get_channel_history",
            "data": {
                "channel_id": channel_param,
                "from": 0,
                "amount": 50
            }
        }
        await self._ws.send(json.dumps(history_msg))
        logger.info(f"GoodGame Chat: Выполнен вход и запрос истории канала {channel_id}")

    async def _websocket_loop(self):
        backoff = 5

        while self._running:
            self._is_authenticated = False
            try:
                await self.plugin._ensure_token_valid()
                channel_id = await self._resolve_channel_and_user_id()

                if not channel_id:
                    await asyncio.sleep(10)
                    continue

                ssl_context = ssl.create_default_context()
                url = "wss://chat-1.goodgame.ru/chat2/"

                ws_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Origin": "https://goodgame.ru"
                }

                import inspect
                sig = inspect.signature(websockets.connect)
                connect_kwargs = {}
                if "additional_headers" in sig.parameters:
                    connect_kwargs["additional_headers"] = ws_headers
                else:
                    connect_kwargs["extra_headers"] = ws_headers

                proxy = http_client.get_proxy_settings()
                if proxy:
                    sock = await asyncio.get_running_loop().run_in_executor(
                        None, http_client.connect_via_proxy_sync, "chat-1.goodgame.ru", 443, proxy
                    )
                    ws = await websockets.connect(
                        url,
                        sock=sock,
                        ssl=ssl_context,
                        server_hostname="chat-1.goodgame.ru",
                        **connect_kwargs
                    )
                else:
                    ws = await websockets.connect(url, ssl=ssl_context, **connect_kwargs)

                self._ws = ws
                backoff = 5

                self._ping_task = asyncio.create_task(self._ping_loop())

                async for raw_message in ws:
                    if not self._running:
                        break
                    try:
                        data = json.loads(raw_message)
                        self._handle_ws_message(data)
                    except Exception as ex:
                        logger.debug(f"GoodGame Chat: ошибка разбора пакета: {ex!r}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"GoodGame Chat: сбой сокета: {e!r}. Реконнект через {backoff}с...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
            finally:
                self._is_authenticated = False
                if self._ping_task:
                    self._ping_task.cancel()
                    self._ping_task = None
                self._ws = None

    def _handle_ws_message(self, data: dict):
        msg_type = data.get("type")
        msg_data = data.get("data") or {}

        if msg_type == "welcome":
            logger.info("GoodGame Chat: Соединение установлено (welcome).")
            asyncio.create_task(self._send_initial_commands())
            return

        if msg_type == "ping":
            if self._ws:
                asyncio.create_task(self._ws.send(json.dumps({"type": "pong", "data": {}})))
            return

        if msg_type == "success_auth":
            uid = msg_data.get("user_id")
            uname = msg_data.get("user_name")
            if uid and str(uid) != "0":
                self._is_authenticated = True
                logger.info(f"GoodGame Chat: Успешная авторизация пользователя {uname} (user_id={uid})!")
            else:
                self._is_authenticated = False
                logger.warning("GoodGame Chat: Подключено в гостевом режиме.")
            return

        if msg_type == "error":
            error_text = msg_data.get("errorMsg") or msg_data.get("error_msg") or str(msg_data)
            logger.error(f"GoodGame Chat сервер вернул ошибку: {error_text}")
            return

        if msg_type in ("message", "welcome_data", "channel_history"):
            messages = []
            if msg_type in ("welcome_data", "channel_history"):
                messages = msg_data.get("messages", [])
                from app.core.service_container import container
                bus = container.get("event_bus")
                if bus:
                    bus.emit("chat.history_loaded", {"platform": "goodgame"})
            else:
                messages = [msg_data]

            from app.core.service_container import container
            bus = container.get("event_bus")
            if not bus:
                return

            for m in messages:
                if not isinstance(m, dict):
                    continue

                text = (m.get("text") or m.get("message") or "").strip()
                if not text:
                    continue

                user_id = str(m.get("user_id") or m.get("userId") or "")
                user_name = m.get("user_name") or m.get("userName") or "Anonymous"
                user_rights = m.get("user_rights", 0)

                is_owner = (user_id and str(self._user_id) and user_id == str(self._user_id)) or (user_rights >= 40)

                # Фильтрация дублирующего эха собственного отправленного сообщения
                if is_owner and text in self.plugin._sent_messages_cache:
                    self.plugin._sent_messages_cache.remove(text)
                    logger.debug(f"GoodGame Chat: Отфильтровано собственное дублирующее сообщение: '{text}'")
                    continue

                msg_id = str(m.get("message_id") or m.get("id") or f"gg_{int(time.time() * 1000)}")
                if msg_id in self._processed_msg_ids:
                    continue

                self._processed_msg_ids.add(msg_id)
                if len(self._processed_msg_ids) > 1000:
                    self._processed_msg_ids.clear()

                is_mod = is_owner or (user_rights >= 20)

                badges = []
                if is_owner:
                    badges.append("owner")
                elif is_mod:
                    badges.append("moderator")

                if m.get("payments"):
                    badges.append("subscriber")

                author = ChatAuthor(
                    id=user_id,
                    name=user_name,
                    avatar_url=m.get("user_avatar"),
                    is_owner=is_owner,
                    is_mod=is_mod,
                    is_sub="subscriber" in badges,
                    badges=badges
                )

                ts_raw = m.get("timestamp") or m.get("time")
                try:
                    timestamp = int(float(ts_raw) * 1000) if ts_raw else int(time.time() * 1000)
                except Exception:
                    timestamp = int(time.time() * 1000)

                chat_msg = ChatMessage(
                    id=msg_id,
                    platform="goodgame",
                    author=author,
                    text=text,
                    timestamp=timestamp
                )

                bus.emit("chat.message_received", chat_msg.to_dict())
