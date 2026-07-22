import asyncio
import ssl
import time
from app.core.schemas import ChatMessage, ChatAuthor
from app.utils import http_client
from app.utils.logger import logger
from app.core import __version__ as version


class TwitchIRCClient:
    def __init__(self, plugin):
        self.plugin = plugin
        self._chat_task = None
        self._chat_running = False
        self._writer = None
        self._sent_echoes = []

    def register_sent_echo(self, echo_id: str):
        self._sent_echoes.append(echo_id)

    async def start(self):
        if self._chat_running:
            return
        self._chat_running = True
        self._chat_task = asyncio.create_task(self._irc_loop())
        logger.info("Twitch Chat IRC: запущен фоновый сокет-слушатель.")

    async def stop(self):
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
        logger.info("Twitch Chat IRC: сокет-слушатель остановлен.")

    async def send_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        if self._writer and self._chat_running:
            try:
                login = await self.plugin._fetch_user_login()
                if reply_parent_msg_id:
                    self._writer.write(
                        f"@reply-parent-msg-id={reply_parent_msg_id} PRIVMSG #{login} :{text}\r\n".encode())
                else:
                    self._writer.write(f"PRIVMSG #{login} :{text}\r\n".encode())
                await self._writer.drain()
                return True
            except Exception as e:
                logger.error(f"Twitch Chat IRC: ошибка отправки: {e!r}")
        return False

    async def _irc_loop(self):
        backoff = 5

        while self._chat_running:
            reader, writer = None, None
            try:
                await self.plugin._ensure_token_valid()
                if not self.plugin.token:
                    await asyncio.sleep(10)
                    continue

                login = await self.plugin._fetch_user_login()
                if not login:
                    await asyncio.sleep(10)
                    continue

                logger.info(f"Twitch Chat IRC: Подключение к SSL-порту для #{login}...")
                ssl_context = ssl.create_default_context()

                proxy = http_client.get_proxy_settings()
                if proxy:
                    logger.debug(f"Twitch Chat IRC: Чат маршрутизируется через прокси-сервер {proxy}")
                    reader, writer = await http_client.open_proxied_connection(
                        "irc.chat.twitch.tv", 6697, proxy_url=proxy, ssl_context=ssl_context
                    )
                else:
                    reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6697, ssl=ssl_context)

                self._writer = writer
                backoff = 5

                writer.write("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n".encode())
                writer.write(f"PASS oauth:{self.plugin.token}\r\n".encode())
                writer.write(f"NICK {login}\r\n".encode())
                await writer.drain()

                await asyncio.sleep(0.5)
                writer.write(f"JOIN #{login}\r\n".encode())
                await writer.drain()

                logger.info("Twitch Chat IRC: авторизация в сокете выполнена.")

                asyncio.create_task(self._fetch_and_load_chat_history(login))

                while self._chat_running:
                    line_bytes = await reader.readline()
                    if not line_bytes:
                        break

                    line = line_bytes.decode("utf-8", errors="ignore").strip()

                    if line.startswith("PING"):
                        writer.write("PONG :tmi.twitch.tv\r\n".encode())
                        await writer.drain()
                        continue

                    self._parse_line(line, login)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Twitch Chat IRC: ошибка сокета: {e!r}. Реконнект через {backoff}с...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
            finally:
                if writer:
                    try:
                        writer.close()
                    except Exception:
                        pass

    def _parse_line(self, line: str, login: str):
        from app.core.service_container import container
        bus = container.get("event_bus")
        if not bus:
            return

        if "USERSTATE" in line and "GLOBALUSERSTATE" not in line:
            try:
                tag_str = line.split(" ", 1)[0][1:]
                tags = dict(item.split("=", 1) for item in tag_str.split(";") if "=" in item)
                real_id = tags.get("id")
                if real_id and self._sent_echoes:
                    old_id = self._sent_echoes.pop(0)
                    bus.emit("chat.message_id_updated", {
                        "platform": "twitch",
                        "old_id": old_id,
                        "new_id": real_id
                    })
            except Exception:
                pass

        elif "CLEARMSG" in line:
            try:
                tag_str = line.split(" ", 1)[0][1:]
                tags = dict(item.split("=", 1) for item in tag_str.split(";") if "=" in item)
                target_msg_id = tags.get("target-msg-id")
                if target_msg_id:
                    bus.emit("chat.message_deleted", {"platform": "twitch", "msg_id": target_msg_id})
            except Exception:
                pass

        elif "CLEARCHAT" in line:
            try:
                parts = line.split(" :", 1)
                if len(parts) >= 2:
                    target_user = parts[1].strip()
                    if target_user:
                        bus.emit("chat.user_banned", {"platform": "twitch", "username": target_user})
            except Exception:
                pass

        elif "PRIVMSG" in line:
            msg = self._parse_irc_message(line, login)
            if msg:
                bus.emit("chat.message_received", msg.to_dict())

    def _parse_irc_message(self, line: str, channel_login: str) -> ChatMessage | None:
        """Отказоустойчивый парсинг IRC-сообщений, исключающий срез первой буквы."""
        try:
            if " PRIVMSG " not in line:
                return None

            tags = {}
            if line.startswith("@"):
                tag_part, rest = line[1:].split(" ", 1)
                for item in tag_part.split(";"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        tags[k] = v
            else:
                rest = line

            prefix_and_msg = rest.split(" PRIVMSG ", 1)
            if len(prefix_and_msg) < 2:
                return None
            prefix_part = prefix_and_msg[0]
            msg_part = prefix_and_msg[1]

            msg_id = tags.get("id", "")

            display_name = tags.get("display-name")
            if not display_name:
                nick = prefix_part
                if nick.startswith(":"):
                    nick = nick[1:]
                if "!" in nick:
                    nick = nick.split("!", 1)[0]
                display_name = nick

            user_id = tags.get("user-id", "")

            # Извлечение точного сообщения с сохранением первой буквы
            chan_and_text = msg_part.split(" :", 1)
            if len(chan_and_text) == 2:
                message_text = chan_and_text[1]
            else:
                message_text = msg_part.split(" ", 1)[1] if " " in msg_part else msg_part

            # Серверное время отправки Twitch (в миллисекундах)
            ts_raw = tags.get("tmi-sent-ts")
            try:
                timestamp = int(ts_raw) if ts_raw and ts_raw.isdigit() else int(time.time() * 1000)
            except Exception:
                timestamp = int(time.time() * 1000)

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
            if is_sub:
                badges_list.append("subscriber")

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
                timestamp=timestamp
            )
        except Exception as e:
            logger.debug(f"Ошибка парсинга Twitch сообщения: {e!r}")
            return None

    async def _fetch_and_load_chat_history(self, channel_login: str):
        try:
            url = f"https://recent-messages.robotty.de/api/v2/recent-messages/{channel_login}"
            headers = {"User-Agent": f"StreamTail/{version}"}
            async with http_client.create_client(timeout=10.0) as client:
                resp = await client.get(url, headers=headers, params={"limit": 50})
                if resp.status_code == 200:
                    data = resp.json()
                    messages = data.get("messages", [])

                    from app.core.service_container import container
                    bus = container.get("event_bus")
                    if not bus:
                        return

                    for raw_line in messages:
                        msg = self._parse_irc_message(raw_line.strip(), channel_login)
                        if msg:
                            bus.emit("chat.message_received", msg.to_dict())
        except Exception as e:
            logger.debug(f"Twitch Chat: не удалось получить историю чата: {e!r}")
        finally:
            # Гарантированное событие завершения выгрузки истории
            from app.core.service_container import container
            bus = container.get("event_bus")
            if bus:
                bus.emit("chat.history_loaded", {"platform": "twitch"})
