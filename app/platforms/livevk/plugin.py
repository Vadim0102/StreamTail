import json
import httpx
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, set_token
from app.utils import token_parser
from app.utils.logger import logger
from app.utils import http_client


class LiveVKPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.api_base = "https://api.live.vkvideo.ru/v1"
        self._last_real_id = None

        # Инициализация асинхронного Centrifugo чат-клиента
        from app.platforms.livevk.chat import LiveVKChatClient
        self.chat_client = LiveVKChatClient(self)

    @property
    def token_data(self):
        return get_token("livevk") or {}

    @property
    def token(self):
        config_token = self.config.get("token", "").strip()
        if not config_token:
            return self.token_data.get("access_token") or ""

        if token_parser.is_cookie_format(config_token):
            cleaned_cookies = token_parser.parse_any_cookie_format(config_token)
            auth_cookie = token_parser.extract_cookie(cleaned_cookies, "auth")
            if auth_cookie:
                token_val = token_parser.parse_local_storage(auth_cookie, "accessToken")
                if token_val:
                    return token_val
            token_val = token_parser.extract_cookie(cleaned_cookies, "accessToken")
            if token_val:
                return token_val

        parsed = token_parser.parse_local_storage(config_token, "accessToken")
        if parsed:
            return parsed

        return config_token

    @property
    def client_id(self):
        """Возвращает Client ID, автоматически извлекая его из кук или LocalStorage."""
        config_token = self.config.get("token", "").strip()

        if token_parser.is_cookie_format(config_token):
            cleaned_cookies = token_parser.parse_any_cookie_format(config_token)
            cid = token_parser.extract_cookie(cleaned_cookies, "_clientId") or \
                  token_parser.extract_cookie(cleaned_cookies, "clientId")
            if cid:
                return cid

        parsed_cid = token_parser.parse_local_storage(config_token, "clientId")
        if parsed_cid:
            return parsed_cid

        config_cid = self.config.get("client_id", "").strip()
        if config_cid:
            return config_cid

        db_cid = self.token_data.get("client_id")
        if db_cid:
            return db_cid

        return "vkplay.live"

    @property
    def owner_id(self) -> str:
        """Нормализует Owner ID и приводит к нижнему регистру во избежание 404 ошибок [1]."""
        raw = self.config.get("owner_id", "").strip()
        if not raw:
            return ""
        if "/" in raw:
            raw = raw.rstrip("/").split("/")[-1]
        return raw.lower()

    @property
    def headers(self):
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        active_client_id = self.client_id
        if active_client_id:
            headers["X-From-Id"] = active_client_id
        return headers

    # ── Чтение статуса ────────────────────────────────────────────────────────

    async def get_status(self):
        status = {
            "is_live": False,
            "viewers": 0,
            "title": "",
            "game": "",
            "needs_publish": False
        }
        if not self.owner_id:
            return status

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"{self.api_base}/blog/{self.owner_id}/public_video_stream"
                resp = await client.get(url)

                if resp.status_code == 200:
                    data = resp.json()
                    is_live = data.get("isOnline", False)
                    title = data.get("title") or ""

                    category_data = data.get("category") or {}
                    game = category_data.get("title") or ""

                    count_data = data.get("count") or {}
                    viewers = count_data.get("viewers") or 0

                    status.update({
                        "is_live": is_live,
                        "viewers": viewers,
                        "title": str(title).strip(),
                        "game": str(game).strip(),
                        "needs_publish": True
                    })
        except Exception as e:
            logger.error(f"Ошибка статуса VK: {e!r}")

        return status

    # ── Вспомогательный метод обновления ──

    async def _update_stream_info(self, title: str = None, category_id: str = None) -> str:
        current_title = ""
        current_cat_id = ""

        if title is None or category_id is None:
            status = await self.get_status()
            if title is None:
                current_title = status.get("title") or ""
            if category_id is None:
                current_game = status.get("game") or ""
                if current_game:
                    current_cat_id = await self._find_category_id(current_game)

        final_title = title if title is not None else current_title
        final_cat_id = category_id if category_id is not None else current_cat_id

        payload = {}
        if final_title:
            title_block = [
                {
                    "type": "text",
                    "content": json.dumps([final_title, "unstyled", []], ensure_ascii=False),
                    "modificator": ""
                }
            ]
            payload["title_data"] = json.dumps(title_block, ensure_ascii=False)

        if final_cat_id:
            payload["category_id"] = final_cat_id

        if not payload:
            return "VK Live: Нет данных для обновления"

        async with http_client.create_client(timeout=10.0) as client:
            url = f"{self.api_base}/channel/{self.owner_id}/manage/stream"
            resp = await client.put(url, headers=self.headers, data=payload)
            if resp.status_code in (200, 204):
                return "VK Live: Данные трансляции успешно сохранены"
            return f"VK Ошибка ({resp.status_code}): {resp.text}"

    # ── Запись ────────────────────────────────────────────────────────────────

    async def set_title(self, title: str) -> str:
        if not self.token:
            return "VK Live: Нет токена авторизации. Скопируйте куки или Local Storage VK!"
        if not self.owner_id:
            return "VK Live: Не задан Owner ID (ID или имя канала)"

        try:
            return await self._update_stream_info(title=title)
        except Exception as e:
            return f"VK Live Исключение: {e!r}"

    async def set_game(self, game: str) -> str:
        if not self.token:
            return "VK Live: Нет токена авторизации. Скопируйте куки или Local Storage VK!"
        if not self.owner_id:
            return "VK Live: Не задан Owner ID (ID или имя канала)"

        try:
            category_id = await self._find_category_id(game)
            if not category_id:
                return f"VK Live: Игра '{game}' не найдена в каталоге VK."

            return await self._update_stream_info(category_id=category_id)
        except Exception as e:
            return f"VK Live Исключение: {e!r}"

    async def _find_category_id(self, game: str) -> str | None:
        try:
            async with http_client.create_client(timeout=10.0) as client:
                cat_url = f"{self.api_base}/public_video_stream/category/"
                cat_resp = await client.get(cat_url, params={"search": game})

                if cat_resp.status_code == 200:
                    items = cat_resp.json().get("data", [])
                    if items:
                        return items[0].get("id")
        except Exception:
            pass
        return None

    # ── Публикация трансляции (Сделать публичной) ───────────────────────────

    async def publish_stream(self) -> str:
        if not self.token:
            return "VK Live: Нет токена авторизации"
        if not self.owner_id:
            return "VK Live: Не задан Owner ID"

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"{self.api_base}/channel/{self.owner_id}/manage/stream"
                payload = {
                    "publish": "1",
                    "access_status": "public",
                    "is_private": "0"
                }
                resp = await client.put(url, headers=self.headers, data=payload)
                if resp.status_code in (200, 204):
                    return "VK Live: Стрим успешно опубликован!"
                return f"VK Live Ошибка публикации ({resp.status_code}): {resp.text}"
        except Exception as e:
            return f"VK Live Исключение при публикации: {e!r}"

    # ── Методы чата ──

    async def start_chat_listener(self):
        await self.chat_client.start()

    async def stop_chat_listener(self):
        await self.chat_client.stop()

    async def _fetch_user_login(self) -> str:
        """Асинхронно получает и кэширует отображаемый никнейм стримера для локального эха."""
        cached_name = self.token_data.get("broadcaster_name")
        if cached_name:
            return cached_name

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"https://api.live.vkvideo.ru/v8/channel/{self.owner_id}/smile_sets"
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    nick = data.get("channel", {}).get("nick") or data.get("channel", {}).get("owner", {}).get(
                        "displayName")
                    if nick:
                        tdata = self.token_data
                        tdata["broadcaster_name"] = nick
                        set_token("livevk", tdata)
                        return nick
        except Exception:
            pass

        return self.owner_id

    async def send_chat_message(self, text: str, reply_parent_msg_id: str = None) -> bool:
        """Отправляет текстовое сообщение в чат VK Video Live, формируя Draft.js блоки."""
        if not self.token:
            return False

        try:
            payload_text = json.dumps([text, "unstyled", []], ensure_ascii=False)
            blocks = [
                {
                    "type": "text",
                    "content": payload_text,
                    "modificator": ""
                },
                {
                    "type": "text",
                    "content": "",
                    "modificator": "BLOCK_END"
                }
            ]
            payload_data = json.dumps(blocks, ensure_ascii=False)

            headers = {
                "Authorization": f"Bearer {self.token}",
                "X-From-Id": self.client_id,
                "X-App": "streams_web",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            async with http_client.create_client() as client:
                url = f"{self.api_base}/channel/{self.owner_id}/stream/slot/default/chat"
                resp = await client.post(url, headers=headers, data={"data": payload_data})
                if resp.status_code in (200, 201):
                    data = resp.json()
                    msg_id = data.get("id")
                    if msg_id:
                        self._last_real_id = str(msg_id)
                    return True
                else:
                    logger.error(f"VK Live Chat: ошибка отправки сообщения (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"VK Live Chat: исключение при отправке сообщения: {e!r}")
        return False

    def register_sent_echo(self, echo_id: str):
        if self._last_real_id:
            from app.core.service_container import container
            bus = container.get("event_bus")
            if bus:
                bus.emit("chat.message_id_updated", {
                    "platform": "livevk",
                    "old_id": echo_id,
                    "new_id": self._last_real_id
                })
            self._last_real_id = None

    async def ban_chat_user(self, user_id: str, reason: str = "", duration: int = None) -> bool:
        """Реализация интерфейса блокировки/таймаута пользователя для ChatService."""
        if not self.token:
            return False
        if duration:
            return await self.chat_client.mute_user(user_id, duration_seconds=duration, reason=reason)
        return await self.chat_client.ban_user(user_id, reason=reason)
