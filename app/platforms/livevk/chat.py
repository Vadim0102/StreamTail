import asyncio
import json
import ssl
import time
import inspect
import re
import httpx
import websockets

from app.core.schemas import ChatMessage, ChatAuthor
from app.utils import http_client, token_parser
from app.utils.logger import logger


class LiveVKChatClient:
    def __init__(self, plugin):
        self.plugin = plugin
        self._chat_task = None
        self._chat_running = False
        self._ws = None

    async def start(self):
        if self._chat_running:
            return
        self._chat_running = True
        self._chat_task = asyncio.create_task(self._websocket_loop())
        asyncio.create_task(self._load_initial_history())
        logger.info("VK Live Chat: запущен фоновый сокет-слушатель Centrifugo.")

    async def stop(self):
        self._chat_running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._chat_task:
            self._chat_task.cancel()
            self._chat_task = None
        logger.info("VK Live Chat: сокет-слушатель остановлен.")

    def _build_auth_headers(self) -> dict:
        """Формирует заголовки авторизации (Cookie или Bearer) и системные заголовки VK Video."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "X-App": "streams_web"
        }
        config_token = self.plugin.config.get("token", "").strip()
        if token_parser.is_cookie_format(config_token):
            headers["Cookie"] = token_parser.parse_any_cookie_format(config_token)
        elif self.plugin.token:
            headers["Authorization"] = f"Bearer {self.plugin.token}"

        active_client_id = self.plugin.client_id
        if active_client_id:
            headers["X-From-Id"] = active_client_id

        return headers

    async def send_message(self, text: str, reply_to_id: str | None = None) -> bool:
        """
        Отправляет сообщение в чат канала. Если указан reply_to_id — отправляет как ответ.
        Подтверждено по HAR-логу реального запроса браузера.
        """
        owner = self.plugin.owner_id.lower()
        if not owner:
            logger.error("VK Live Chat: не задан owner_id, отправка сообщения невозможна.")
            return False

        payload_data = json.dumps([
            {"type": "text", "content": json.dumps([text, "unstyled", []]), "modificator": ""},
            {"type": "text", "content": "", "modificator": "BLOCK_END"}
        ])
        form = {"data": payload_data}
        if reply_to_id:
            form["reply_to_id"] = str(reply_to_id)

        url = f"https://api.live.vkvideo.ru/v1/channel/{owner}/stream/slot/default/chat"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=self._build_auth_headers(), data=form)
                if resp.status_code == 200:
                    logger.debug(f"VK Live Chat: сообщение отправлено. Ответ: {resp.text[:300]!r}")
                    return True
                logger.error(f"VK Live Chat: отправка сообщения вернула статус {resp.status_code}: {resp.text[:300]!r}")
                return False
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка отправки сообщения: {e!r}")
            return False

    async def delete_message(self, message_id: str) -> bool:
        """
        Удаляет сообщение по его id. Подтверждено по HAR-логу реального запроса браузера.
        Обратите внимание: этот эндпоинт использует /v1/blog/, а не /v1/channel/.
        """
        owner = self.plugin.owner_id.lower()
        if not owner:
            logger.error("VK Live Chat: не задан owner_id, удаление сообщения невозможно.")
            return False

        url = f"https://api.live.vkvideo.ru/v1/blog/{owner}/public_video_stream/chat/{message_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(url, headers=self._build_auth_headers())
                if resp.status_code == 200:
                    logger.debug(f"VK Live Chat: сообщение {message_id} удалено.")
                    return True
                logger.error(f"VK Live Chat: удаление сообщения {message_id} вернуло статус {resp.status_code}: {resp.text[:300]!r}")
                return False
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка удаления сообщения {message_id}: {e!r}")
            return False

    async def pin_message(self, message_id: str, kind: str = "permanent", reactable: bool = True) -> bool:
        """
        Закрепляет сообщение по его id. Подтверждено по HAR-логу реального запроса браузера.
        kind: "permanent" (пока не открепят вручную) — другие варианты (например, ограниченные по времени) не проверялись.
        """
        owner = self.plugin.owner_id.lower()
        if not owner:
            logger.error("VK Live Chat: не задан owner_id, закрепление невозможно.")
            return False

        form = {"kind": kind, "message_id": str(message_id), "reactable": "true" if reactable else "false"}
        url = f"https://api.live.vkvideo.ru/v1/channel/{owner}/stream/slot/default/chat/pinned_message"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=self._build_auth_headers(), data=form)
                if resp.status_code == 200:
                    logger.debug(f"VK Live Chat: сообщение {message_id} закреплено.")
                    return True
                logger.error(f"VK Live Chat: закрепление сообщения {message_id} вернуло статус {resp.status_code}: {resp.text[:300]!r}")
                return False
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка закрепления сообщения {message_id}: {e!r}")
            return False

    async def unpin_message(self) -> bool:
        """Открепляет текущее закреплённое сообщение. Подтверждено по HAR-логу реального запроса браузера."""
        owner = self.plugin.owner_id.lower()
        if not owner:
            logger.error("VK Live Chat: не задан owner_id, открепление невозможно.")
            return False

        url = f"https://api.live.vkvideo.ru/v1/channel/{owner}/stream/slot/default/chat/pinned_message"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(url, headers=self._build_auth_headers())
                if resp.status_code == 200:
                    logger.debug("VK Live Chat: закреплённое сообщение снято.")
                    return True
                logger.error(f"VK Live Chat: открепление вернуло статус {resp.status_code}: {resp.text[:300]!r}")
                return False
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка открепления: {e!r}")
            return False

    async def mute_user(self, user_id: str, duration_seconds: int | None = 600, reason: str = "") -> bool:
        """
        Выдает временный таймаут (мут) пользователю на VK Video Live.
        Подтверждено по HAR-логу.
        """
        owner = self.plugin.owner_id.lower()
        if not owner:
            logger.error("VK Live Chat: не задан owner_id, мьют невозможен.")
            return False

        url = f"https://api.live.vkvideo.ru/v1/channel/{owner}/public_video_stream/ban/stream/slot/default"
        form = {
            "user_id": str(user_id),
            "period": str(duration_seconds or 600),
            "by_stream": "false",
            "is_permanent": "false"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.put(url, headers=self._build_auth_headers(), data=form)
                if resp.status_code == 200:
                    logger.info(f"VK Live Chat: пользователю {user_id} выдан таймаут на {duration_seconds}с.")
                    return True
                logger.error(f"VK Live Chat: мьют пользователя {user_id} вернул статус {resp.status_code}: {resp.text[:300]!r}")
                return False
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка mute_user: {e!r}")
            return False

    async def ban_user(self, user_id: str, reason: str = "") -> bool:
        """
        Выдает перманентный бан пользователю с очисткой сообщений на VK Video Live.
        Подтверждено по HAR-логу.
        """
        owner = self.plugin.owner_id.lower()
        if not owner:
            logger.error("VK Live Chat: не задан owner_id, бан невозможен.")
            return False

        url = f"https://api.live.vkvideo.ru/v1/channel/{owner}/public_video_stream/ban/stream/slot/default"
        form = {
            "user_id": str(user_id),
            "is_permanent": "true",
            "by_stream": "false",
            "clean_messages": "true"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.put(url, headers=self._build_auth_headers(), data=form)
                if resp.status_code == 200:
                    logger.info(f"VK Live Chat: пользователь {user_id} забанен перманентно.")
                    return True
                logger.error(f"VK Live Chat: бан пользователя {user_id} вернул статус {resp.status_code}: {resp.text[:300]!r}")
                return False
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка ban_user: {e!r}")
            return False

    async def unban_user(self, user_id: str) -> bool:
        """Снимает бан/таймаут с пользователя на VK Video Live."""
        owner = self.plugin.owner_id.lower()
        if not owner:
            return False

        url = f"https://api.live.vkvideo.ru/v1/channel/{owner}/public_video_stream/ban/stream/slot/default"
        params = {
            "by_stream": "false",
            "user_id": str(user_id)
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(url, headers=self._build_auth_headers(), params=params)
                if resp.status_code == 200:
                    logger.info(f"VK Live Chat: пользователь {user_id} разбанен.")
                    return True
                return False
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка unban_user: {e!r}")
            return False

    async def _load_initial_history(self):
        """Загружает начальную историю сообщений чата при запуске."""
        await asyncio.sleep(1)
        owner = self.plugin.owner_id.lower()
        if not owner:
            return

        logger.info("VK Live Chat: загрузка начальной истории чата...")
        history_items = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                config_token = self.plugin.config.get("token", "").strip()
                if token_parser.is_cookie_format(config_token):
                    headers["Cookie"] = token_parser.parse_any_cookie_format(config_token)
                elif self.plugin.token:
                    headers["Authorization"] = f"Bearer {self.plugin.token}"

                endpoints = [
                    f"https://api.live.vkvideo.ru/v1/channel/{owner}/stream/slot/default/chat",
                    f"https://api.live.vkvideo.ru/v1/channel/{owner}/public_video_stream/chat/messages",
                    f"https://api.live.vkvideo.ru/v1/channel/{owner}/chat/messages"
                ]

                for url in endpoints:
                    try:
                        resp = await client.get(url, headers=headers, params={"limit": 50})
                        if resp.status_code == 200:
                            res_json = resp.json()
                            items = res_json.get("data") or res_json.get("items") or res_json.get("messages")
                            if isinstance(items, list) and items:
                                history_items = items
                                logger.debug(f"VK Live Chat: Успешно загружена история ({len(items)} сообщ.) через {url}")
                                break
                            else:
                                logger.debug(
                                    f"VK Live Chat: История {url} вернула 200, но без пригодного списка сообщений. "
                                    f"Ключи ответа: {list(res_json.keys())!r}"
                                )
                        else:
                            logger.debug(
                                f"VK Live Chat: История {url} вернула статус {resp.status_code}: {resp.text[:200]!r}"
                            )
                    except Exception as e:
                        logger.debug(f"VK Live Chat: Ошибка запроса истории через {url}: {e!r}")

        except Exception as e:
            logger.debug(f"VK Live Chat: Ошибка загрузки истории: {e!r}")

        if history_items:
            from app.core.service_container import container
            bus = container.get("event_bus")
            if bus:
                for item in reversed(history_items):
                    msg = self._parse_chat_message(item)
                    if msg:
                        bus.emit("chat.message_received", msg.to_dict())

        from app.core.service_container import container
        bus = container.get("event_bus")
        if bus:
            bus.emit("chat.history_loaded", {"platform": "livevk"})

    async def _fetch_global_ws_token(self, client: httpx.AsyncClient) -> str:
        """
        Получает публичный глобальный WebSocket JWT-токен сокета VK Video Live:
        1. Из REST API /v1/app/config
        2. Из HTML-кода главной страницы live.vkvideo.ru
        """
        try:
            resp = await client.get("https://api.live.vkvideo.ru/v1/app/config")
            if resp.status_code == 200:
                data = resp.json()
                ws_obj = data.get("websocket") or data.get("data", {}).get("websocket") or {}
                if isinstance(ws_obj, dict):
                    tok = ws_obj.get("token") or ws_obj.get("wsToken")
                    if tok and str(tok).startswith("ey") and len(str(tok)) > 50:
                        logger.debug("VK Live Chat: Получен глобальный ws_token из /v1/app/config.")
                        return str(tok).strip()
        except Exception as e:
            logger.debug(f"VK Live Chat: Ошибка при запросе /app/config: {e!r}")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            resp = await client.get("https://live.vkvideo.ru/", headers=headers)
            if resp.status_code == 200:
                html = resp.text
                match = re.search(r'"websocket"\s*:\s*\{[^}]*"token"\s*:\s*"(ey[A-Za-z0-9_\-\.]{50,})"', html)
                if not match:
                    match = re.search(r'"token"\s*:\s*"(ey[A-Za-z0-9_\-\.]{50,})"', html)

                if match:
                    tok = match.group(1)
                    logger.debug("VK Live Chat: Успешно спарсен глобальный ws_token из HTML live.vkvideo.ru.")
                    return tok
        except Exception as e:
            logger.debug(f"VK Live Chat: Ошибка при парсинге HTML страницы: {e!r}")

        return ""

    async def _fetch_channel_chat_info(self) -> tuple[str, str]:
        """
        Определяет Centrifugo-канал (channel-chat:{owner_id}) и глобальный сокет-токен.
        """
        chat_channel = ""
        ws_token = ""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                owner = self.plugin.owner_id.lower()

                # 1. Запрос глобального JWT сокета
                ws_token = await self._fetch_global_ws_token(client)

                # 2. Определение топика канала через /blog/{owner}/public_video_stream/chat/user/
                url_chat_user = f"https://api.live.vkvideo.ru/v1/blog/{owner}/public_video_stream/chat/user/"
                try:
                    resp_cu = await client.get(url_chat_user)
                    if resp_cu.status_code == 200:
                        data_cu = resp_cu.json()
                        ws_ch = data_cu.get("wsChatChannel") or data_cu.get("channel") or data_cu.get("channelId")
                        if ws_ch:
                            chat_channel = str(ws_ch)
                        else:
                            owner_id = data_cu.get("owner", {}).get("id")
                            if owner_id:
                                chat_channel = f"channel-chat:{owner_id}"
                except Exception as e:
                    logger.debug(f"VK Live Chat: Ошибка при запросе chat/user/: {e!r}")

                # 3. Резервное определение через /blog/{owner}
                if not chat_channel:
                    url_blog = f"https://api.live.vkvideo.ru/v1/blog/{owner}"
                    try:
                        resp_blog = await client.get(url_blog)
                        if resp_blog.status_code == 200:
                            data_blog = resp_blog.json()
                            owner_id = data_blog.get("owner", {}).get("id")
                            if owner_id:
                                chat_channel = f"channel-chat:{owner_id}"
                    except Exception as e:
                        logger.debug(f"VK Live Chat: ошибка при запросе blog: {e!r}")

        except Exception as ex:
            logger.debug(f"VK Live Chat: исключение в _fetch_channel_chat_info: {ex!r}")

        logger.debug(f"VK Live Chat: топик={chat_channel}, ws_token={'получен' if ws_token else 'не получен'}.")
        return chat_channel, ws_token

    async def _websocket_loop(self):
        backoff = 5

        while self._chat_running:
            try:
                if not self.plugin.owner_id:
                    await asyncio.sleep(5)
                    continue

                # Извлечение информации о канале и получение глобального JWT
                chat_channel, ws_token = await self._fetch_channel_chat_info()
                if not chat_channel:
                    logger.warning("VK Live Chat: не удалось определить Centrifugo-канал. Реконнект через 10с...")
                    await asyncio.sleep(10)
                    continue

                if not ws_token:
                    logger.warning("VK Live Chat: не удалось получить глобальный WebSocket JWT токен. Реконнект через 10с...")
                    await asyncio.sleep(10)
                    continue

                ssl_context = ssl.create_default_context()
                url = "wss://pubsub.live.vkvideo.ru/connection/websocket?cf_protocol_version=v2"

                ws_headers = {
                    "Origin": "https://live.vkvideo.ru",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }

                sig = inspect.signature(websockets.connect)
                connect_kwargs = {}
                if "additional_headers" in sig.parameters:
                    connect_kwargs["additional_headers"] = ws_headers
                else:
                    connect_kwargs["extra_headers"] = ws_headers

                proxy = http_client.get_proxy_settings()
                if proxy:
                    logger.debug(f"VK Live Chat: сокет туннелируется через прокси {proxy}")
                    sock = await asyncio.get_running_loop().run_in_executor(
                        None, http_client.connect_via_proxy_sync, "pubsub.live.vkvideo.ru", 443, proxy
                    )
                    ws = await websockets.connect(
                        url,
                        sock=sock,
                        ssl=ssl_context,
                        server_hostname="pubsub.live.vkvideo.ru",
                        **connect_kwargs
                    )
                else:
                    ws = await websockets.connect(url, ssl=ssl_context, **connect_kwargs)

                self._ws = ws
                backoff = 5

                # Шаг 1: Connect-фрейм с передачей глобального JWT
                connect_body = {
                    "token": ws_token,
                    "name": "js",
                    "version": "3.6.2"
                }

                await ws.send(json.dumps({"id": 1, "connect": connect_body}))
                logger.debug("VK Live Chat: Отправлен connect-фрейм с глобальным JWT.")

                # Дожидаемся ответа от сервера на connect
                raw_connect_resp = await ws.recv()
                if raw_connect_resp in ("{}", "[]"):
                    await ws.send("{}")
                    raw_connect_resp = await ws.recv()

                resp_data = json.loads(raw_connect_resp)
                connect_resp = resp_data[0] if isinstance(resp_data, list) and resp_data else resp_data
                logger.debug(f"VK Live Chat: Ответ сервера на connect: {connect_resp}")

                if "error" in connect_resp:
                    logger.error(f"VK Live Chat: Ошибка авторизации Centrifugo: {connect_resp['error']}")
                    await ws.close()
                    await asyncio.sleep(5)
                    continue

                # Шаг 2: Subscribe-фрейм подписки на публичный канал (без токена!)
                await ws.send(json.dumps({"id": 2, "subscribe": {"channel": chat_channel}}))

                raw_sub_resp = await ws.recv()
                if raw_sub_resp in ("{}", "[]"):
                    await ws.send("{}")
                    raw_sub_resp = await ws.recv()

                sub_data = json.loads(raw_sub_resp)
                sub_resp = sub_data[0] if isinstance(sub_data, list) and sub_data else sub_data
                logger.debug(f"VK Live Chat: Ответ сервера на подписку {chat_channel}: {sub_resp}")

                if "error" in sub_resp:
                    logger.error(f"VK Live Chat: Ошибка подписки на канал: {sub_resp['error']}")
                    await ws.close()
                    await asyncio.sleep(5)
                    continue

                logger.info(f"VK Live Chat: Успешная подписка на Centrifugo-канал {chat_channel}!")

                # Основной цикл обработки входящих сообщений
                async for raw_message in ws:
                    if not self._chat_running:
                        break

                    if raw_message in ("{}", "[]"):
                        await ws.send("{}")
                        continue

                    logger.debug(f"VK Live Chat: получен сырой фрейм: {raw_message[:500]!r}")

                    data = json.loads(raw_message)
                    if isinstance(data, list):
                        for item in data:
                            await self._handle_websocket_message(item)
                    elif isinstance(data, dict):
                        await self._handle_websocket_message(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"VK Live Chat: сбой веб-сокета: {e!r}. Реконнект через {backoff}с...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _handle_websocket_message(self, data: dict):
        push_data = data.get("push")
        if not push_data:
            logger.debug(f"VK Live Chat: фрейм без 'push', пропущен. Ключи: {list(data.keys())!r}")
            return

        pub_data = push_data.get("pub", {}).get("data", {})
        if not pub_data:
            logger.debug(f"VK Live Chat: 'push' без 'pub.data', пропущен. push_data: {push_data!r}")
            return

        # Сервер оборачивает фактическое сообщение ещё на один уровень:
        # {"data": {<само сообщение: id, author, data[], createdAt, ...>}, "type": "message"}
        event_type = pub_data.get("type")
        message_data = pub_data.get("data")

        if not isinstance(message_data, dict):
            logger.debug(f"VK Live Chat: событие без вложенного 'data'-объекта. pub_data: {pub_data!r}")
            return

        if event_type not in (None, "message"):
            logger.debug(f"VK Live Chat: пропущено событие типа {event_type!r} (не текстовое сообщение)")
            return

        msg = self._parse_chat_message(message_data)
        if msg:
            from app.core.service_container import container
            bus = container.get("event_bus")
            if bus:
                bus.emit("chat.message_received", msg.to_dict())
        else:
            logger.debug(f"VK Live Chat: сообщение не распознано парсером. message_data: {message_data!r}")

    def _parse_chat_message(self, pub_data) -> ChatMessage | None:
        try:
            if isinstance(pub_data, str):
                try:
                    pub_data = json.loads(pub_data)
                except Exception:
                    return None

            if not isinstance(pub_data, dict):
                return None

            msg_id = str(pub_data.get("id", f"vk_{int(time.time()*1000)}"))
            created_at = pub_data.get("createdAt")
            timestamp = (created_at * 1000) if created_at else int(time.time() * 1000)

            author_data = pub_data.get("author", {})
            if isinstance(author_data, dict):
                author_id = str(author_data.get("id", ""))
                author_name = author_data.get("displayName") or author_data.get("name") or "User"
                avatar_url = author_data.get("avatarUrl")
                is_owner = author_data.get("isOwner", False)
                is_mod = author_data.get("isChannelModerator", False) or author_data.get("isChatModerator", False) or is_owner
                raw_badges = author_data.get("badges", [])
            else:
                author_id = ""
                author_name = str(author_data) if author_data else "User"
                avatar_url = None
                is_owner = False
                is_mod = False
                raw_badges = []

            badges_list = []
            if isinstance(raw_badges, list):
                for badge in raw_badges:
                    if isinstance(badge, dict):
                        ach = badge.get("achievement", {})
                        if isinstance(ach, dict):
                            ach_name = ach.get("name") or ach.get("type")
                            if ach_name:
                                badges_list.append(str(ach_name))

            if is_owner and "owner" not in badges_list:
                badges_list.append("owner")
            elif is_mod and "moderator" not in badges_list:
                badges_list.append("moderator")

            text_blocks = []
            data_blocks = pub_data.get("data", [])
            if isinstance(data_blocks, list):
                for block in data_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        content_raw = block.get("content", "")
                        if content_raw:
                            if isinstance(content_raw, str):
                                try:
                                    parsed_content = json.loads(content_raw)
                                    if isinstance(parsed_content, list) and parsed_content:
                                        text_blocks.append(str(parsed_content[0]))
                                    else:
                                        text_blocks.append(str(content_raw))
                                except Exception:
                                    text_blocks.append(str(content_raw))
                            elif isinstance(content_raw, list) and content_raw:
                                text_blocks.append(str(content_raw[0]))
                            else:
                                text_blocks.append(str(content_raw))
            elif isinstance(data_blocks, str):
                text_blocks.append(data_blocks)

            text = " ".join(text_blocks).strip()
            if not text:
                return None

            author = ChatAuthor(
                id=author_id,
                name=author_name,
                avatar_url=avatar_url,
                is_mod=is_mod,
                is_owner=is_owner,
                badges=badges_list
            )

            return ChatMessage(
                id=msg_id,
                platform="livevk",
                author=author,
                text=text,
                timestamp=timestamp
            )
        except Exception as e:
            logger.error(f"VK Live Chat: ошибка разбора структуры сообщения: {e!r}")
            return None
