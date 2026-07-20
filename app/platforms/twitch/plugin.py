import asyncio
import time
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger
from app.utils import http_client
from app.core.schemas import ChatMessage, ChatAuthor


class TwitchPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.client_id = self.config.get("client_id")
        self._chat_task = None
        self._chat_running = False
        self._writer = None
        self._sent_echoes = []  # Очередь временных ID отправленных эхо-сообщений

    @property
    def token_data(self):
        return get_token("twitch") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def broadcaster_id(self):
        return self.token_data.get("broadcaster_id") or self.config.get("broadcaster_id")

    @property
    def headers(self):
        return {
            "Client-Id": self.token_data.get("client_id", self.client_id),
            "Authorization": f"Bearer {self.token}"
        }

    async def _ensure_token_valid(self) -> bool:
        if is_token_valid("twitch"):
            return True

        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id") or self.client_id
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import twitch_auth
            logger.info("Twitch: токен истек. Выполняем автоматическое обновление токена...")
            return await twitch_auth.refresh(c_id, c_sec, r_token)
        return False

    async def _get_game_id(self, game_name: str, client: http_client.create_client) -> str:
        url = f"https://api.twitch.tv/helix/games?name={game_name}"
        resp = await client.get(url, headers=self.headers)
        data = resp.json()
        if data.get("data"):
            return data["data"][0]["id"]
        return ""

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.token or not self.broadcaster_id:
            return status

        await self._ensure_token_valid()

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"https://api.twitch.tv/helix/streams?user_id={self.broadcaster_id}"
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()

                if data.get("data"):
                    stream = data["data"][0]
                    status.update({
                        "is_live": True,
                        "viewers": stream.get("viewer_count", 0),
                        "title": stream.get("title", ""),
                        "game": stream.get("game_name", "")
                    })
                else:
                    url_ch = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
                    resp_ch = await client.get(url_ch, headers=self.headers)
                    ch_data = resp_ch.json()
                    if ch_data.get("data"):
                        ch = ch_data["data"][0]
                        status.update({
                            "title": ch.get("title", ""),
                            "game": ch.get("game_name", "")
                        })
        except Exception as e:
            logger.error(f"Ошибка статуса Twitch: {e!r}")
        return status

    async def set_title(self, title: str) -> str:
        if not self.token: return "Twitch: Нет токена"
        await self._ensure_token_valid()
        async with http_client.create_client() as client:
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"title": title})
            return "Twitch: Заголовок изменен" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        if not self.token: return "Twitch: Нет токена"
        await self._ensure_token_valid()
        async with http_client.create_client() as client:
            game_id = await self._get_game_id(game, client)
            if not game_id:
                return f"Twitch: Игра '{game}' не найдена"
            url = f"https://api.twitch.tv/helix/channels?broadcaster_id={self.broadcaster_id}"
            resp = await client.patch(url, headers=self.headers, json={"game_id": game_id})
            return "Twitch: Категория изменена" if resp.status_code == 204 else f"Twitch Ошибка: {resp.text}"

    # ── Чтение чата и управление ──

    def register_sent_echo(self, echo_id: str):
        """Регистрирует локальный временный ID отправленного сообщения."""
        self._sent_echoes.append(echo_id)

    async def start_chat_listener(self):
        if self._chat_running:
            return
        self._chat_running = True
        self._chat_task = asyncio.create_task(self._irc_loop())
        logger.info("Twitch Chat: запущен фоновый сокет-слушатель.")

    async def stop_chat_listener(self):
        self._chat_running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        if self._chat_task:
            self._chat_task.cancel()
            self._chat_task = None
        logger.info("Twitch Chat: сокет-слушатель остановлен.")

    async def send_chat_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        if self._writer and self._chat_running:
            try:
                login = await self._fetch_user_login()

                # Если передан ID родительского сообщения, отправляем пакет со спецификацией IRC-ответа
                if reply_parent_msg_id:
                    logger.debug(f"Twitch Chat: Отправка ответа в тред PRIVMSG #{login} (parent={reply_parent_msg_id})")
                    self._writer.write(
                        f"@reply-parent-msg-id={reply_parent_msg_id} PRIVMSG #{login} :{text}\r\n".encode())
                else:
                    logger.debug(f"Twitch Chat: Отправка PRIVMSG #{login} : {text}")
                    self._writer.write(f"PRIVMSG #{login} :{text}\r\n".encode())

                await self._writer.drain()
                logger.info(f"Twitch Chat: Сообщение успешно записано в сокет")
                return True
            except Exception as e:
                logger.error(f"Twitch Chat: ошибка отправки сообщения: {e!r}")
        return False

    async def pin_chat_message(self, message_id: str, duration: int = None) -> bool:
        """Выполняет закрепление сообщения на канале через Helix API."""
        await self._ensure_token_valid()
        if not self.token or not self.broadcaster_id:
            return False

        try:
            async with http_client.create_client() as client:
                url = "https://api.twitch.tv/helix/chat/pins"
                params = {
                    "broadcaster_id": self.broadcaster_id,
                    "moderator_id": self.broadcaster_id,
                    "message_id": message_id
                }
                if duration:
                    params["duration_seconds"] = int(duration)

                # PUT-запрос с пустым телом по спецификации Twitch
                resp = await client.put(url, headers=self.headers, params=params)
                if resp.status_code in (200, 204):
                    logger.info(f"Twitch Chat API: Сообщение {message_id} успешно закреплено.")
                    return True
                else:
                    logger.error(f"Twitch Chat API: Ошибка закрепления (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Twitch Chat API: Исключение при закрепе сообщения: {e!r}")
        return False

    async def delete_chat_message(self, message_id: str) -> bool:
        await self._ensure_token_valid()
        if not self.token or not self.broadcaster_id:
            return False

        try:
            async with http_client.create_client() as client:
                url = "https://api.twitch.tv/helix/moderation/chat"
                params = {
                    "broadcaster_id": self.broadcaster_id,
                    "moderator_id": self.broadcaster_id,
                    "message_id": message_id
                }
                resp = await client.delete(url, headers=self.headers, params=params)
                if resp.status_code == 204:
                    logger.info(f"Twitch Chat API: Сообщение {message_id} успешно удалено.")
                    return True
                else:
                    logger.error(f"Twitch Chat API: Ошибка удаления (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Twitch Chat API: Исключение при удалении сообщения: {e!r}")
        return False

    async def ban_chat_user(self, user_id: str, reason: str = "", duration: int = None) -> bool:
        await self._ensure_token_valid()
        if not self.token or not self.broadcaster_id:
            return False

        try:
            async with http_client.create_client() as client:
                url = "https://api.twitch.tv/helix/moderation/bans"
                params = {
                    "broadcaster_id": self.broadcaster_id,
                    "moderator_id": self.broadcaster_id
                }
                payload = {
                    "data": {
                        "user_id": str(user_id)
                    }
                }
                if duration:
                    payload["data"]["duration"] = int(duration)
                if reason:
                    payload["data"]["reason"] = str(reason)

                resp = await client.post(url, headers=self.headers, params=params, json=payload)
                if resp.status_code in (200, 201):
                    logger.info(f"Twitch Chat API: Пользователь {user_id} успешно заблокирован.")
                    return True
                else:
                    logger.error(f"Twitch Chat API: Ошибка блокировки (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Twitch Chat API: Исключение при блокировке пользователя: {e!r}")
        return False

    async def _fetch_user_login(self) -> str:
        cached_login = self.token_data.get("broadcaster_login")
        if cached_login:
            return cached_login

        if not self.token:
            return ""

        try:
            async with http_client.create_client(timeout=10) as client:
                resp = await client.get("https://api.twitch.tv/helix/users", headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        login = data["data"][0]["login"]
                        from app.auth.token_store import set_token
                        tdata = self.token_data
                        tdata["broadcaster_login"] = login
                        set_token("twitch", tdata)
                        return login
        except Exception as e:
            logger.error(f"Twitch Chat: не удалось получить логин пользователя: {e}")
        return ""

    async def _fetch_and_load_chat_history(self, channel_login: str):
        """Асинхронно запрашивает последние сообщения через публичный кэш Chatterino."""
        try:
            url = f"https://recent-messages.robotty.de/api/v2/recent-messages/{channel_login}"
            headers = {"User-Agent": "StreamTail/2.5.1"}
            async with http_client.create_client(timeout=10.0) as client:
                resp = await client.get(url, headers=headers, params={"limit": 50})
                if resp.status_code == 200:
                    data = resp.json()
                    messages = data.get("messages", [])
                    logger.info(f"Twitch Chat: Загружено {len(messages)} сообщений истории для #{channel_login}")

                    from app.core.service_container import container
                    bus = container.get("event_bus")
                    if not bus:
                        return

                    for raw_line in messages:
                        msg = self._parse_irc_message(raw_line.strip(), channel_login)
                        if msg:
                            bus.emit("chat.message_received", msg.to_dict())
        except Exception as e:
            logger.debug(f"Twitch Chat: Не удалось загрузить историю чата: {e!r}")

    async def _irc_loop(self):
        while self._chat_running:
            reader, writer = None, None
            try:
                await self._ensure_token_valid()
                if not self.token:
                    await asyncio.sleep(10)
                    continue

                login = await self._fetch_user_login()
                if not login:
                    await asyncio.sleep(10)
                    continue

                logger.info(f"Twitch Chat: Подключение к IRC для #{login}...")
                reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
                self._writer = writer

                writer.write("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n".encode())
                writer.write(f"PASS oauth:{self.token}\r\n".encode())
                writer.write(f"NICK {login}\r\n".encode())
                await writer.drain()

                await asyncio.sleep(0.5)
                writer.write(f"JOIN #{login}\r\n".encode())
                await writer.drain()

                logger.info("Twitch Chat: авторизован в сокете IRC.")

                # Загружаем историю чата в фоне
                asyncio.create_task(self._fetch_and_load_chat_history(login))

                while self._chat_running:
                    line_bytes = await reader.readline()
                    if not line_bytes:
                        break

                    line = line_bytes.decode("utf-8", errors="ignore").strip()
                    logger.debug(f"Twitch Chat RAW: {line}")

                    if line.startswith("PING"):
                        writer.write("PONG :tmi.twitch.tv\r\n".encode())
                        await writer.drain()
                        continue

                    # ПЕРЕХВАТ ПАКЕТА ПОДТВЕРЖДЕНИЯ ОТПРАВКИ (USERSTATE) ДЛЯ ИЗВЛЕЧЕНИЯ СЕРВЕРНОГО ID СООБЩЕНИЯ
                    if "USERSTATE" in line and "GLOBALUSERSTATE" not in line:
                        try:
                            tag_str = line.split(" ", 1)[0][1:]
                            tags = {}
                            for item in tag_str.split(";"):
                                if "=" in item:
                                    k, v = item.split("=", 1)
                                    tags[k] = v
                            real_id = tags.get("id")
                            if real_id and self._sent_echoes:
                                old_id = self._sent_echoes.pop(0)
                                from app.core.service_container import container
                                bus = container.get("event_bus")
                                if bus:
                                    bus.emit("chat.message_id_updated", {
                                        "platform": "twitch",
                                        "old_id": old_id,
                                        "new_id": real_id
                                    })
                        except Exception as ex:
                            logger.debug(f"Twitch Chat: Ошибка разбора USERSTATE для получения ID: {ex!r}")

                    if "CLEARMSG" in line:
                        try:
                            tag_str = line.split(" ", 1)[0][1:]
                            tags = {}
                            for item in tag_str.split(";"):
                                if "=" in item:
                                    k, v = item.split("=", 1)
                                    tags[k] = v
                            target_msg_id = tags.get("target-msg-id")
                            if target_msg_id:
                                from app.core.service_container import container
                                bus = container.get("event_bus")
                                if bus:
                                    bus.emit("chat.message_deleted", {"platform": "twitch", "msg_id": target_msg_id})
                        except Exception as ex:
                            logger.debug(f"Twitch Chat: Ошибка парсинга CLEARMSG: {ex!r}")

                    if "CLEARCHAT" in line:
                        try:
                            parts = line.split(" :", 1)
                            if len(parts) >= 2:
                                target_user = parts[1].strip()
                                if target_user:
                                    from app.core.service_container import container
                                    bus = container.get("event_bus")
                                    if bus:
                                        bus.emit("chat.user_banned", {"platform": "twitch", "username": target_user})
                        except Exception as ex:
                            logger.debug(f"Twitch Chat: Ошибка парсинга CLEARCHAT: {ex!r}")

                    if "PRIVMSG" in line:
                        msg = self._parse_irc_message(line, login)
                        if msg:
                            logger.info(f"Twitch Chat: [#{login}] {msg.author.name}: {msg.text}")
                            from app.core.service_container import container
                            bus = container.get("event_bus")
                            if bus:
                                bus.emit("chat.message_received", msg.to_dict())

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Twitch Chat: разрыв сокета или ошибка в цикле: {e!r}. Реконнект через 5с...")
                await asyncio.sleep(5)
            finally:
                if writer:
                    try:
                        writer.close()
                    except Exception:
                        pass

    def _parse_irc_message(self, line: str, channel_login: str) -> ChatMessage | None:
        try:
            if not line.startswith("@"):
                return None
            parts = line.split(" ", 4)
            if len(parts) < 5:
                return None

            tag_str = parts[0][1:]
            prefix = parts[1]
            message_text = parts[4][1:]

            tags = {}
            for item in tag_str.split(";"):
                if "=" in item:
                    k, v = item.split("=", 1)
                    tags[k] = v

            msg_id = tags.get("id", "")
            display_name = tags.get("display-name") or prefix.split("!")[0][1:]
            user_id = tags.get("user-id", "")

            is_mod = tags.get("mod") == "1"
            is_sub = tags.get("subscriber") == "1"
            badges_raw = tags.get("badges", "")
            is_owner = "broadcaster" in badges_raw or display_name.lower() == channel_login.lower()

            if is_owner:
                is_mod = True

            badges_list = []
            if is_owner:
                badges_list.append("owner")
            elif is_mod:
                badges_list.append("moderator")
            if is_sub: badges_list.append("subscriber")

            author = ChatAuthor(
                id=user_id,
                name=display_name,
                is_mod=is_mod,
                is_sub=is_sub,
                is_owner=is_owner,
                badges=badges_list
            )

            return ChatMessage(
                id=msg_id,
                platform="twitch",
                author=author,
                text=message_text,
                timestamp=int(time.time() * 1000)
            )
        except Exception as e:
            logger.debug(f"Twitch Chat: не удалось разобрать строку: {e!r}")
            return None
