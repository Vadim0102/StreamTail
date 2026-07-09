"""
RUTUBE Studio Integration Plugin.

========================================================================================
                                     RUTUBE API MAP
========================================================================================

1. ЧТЕНИЕ СТАТУСА (Публичный фид - Обход QRATOR-защиты):
   • GET https://rutube.ru/api/video/person/{channel_id}/
   • Response: {"results": [{"id": "stream_id", "is_live": true, "title": "...", "category": {"name": "..."}}]}

2. ЧТЕНИЕ СТАТУСА (HTML Redux State - 100% Автоматический поиск ID стрима, названия и игры):
   • GET https://rutube.ru/channel/{channel_id}/
   • HTML Parser: Находит блок `window.reduxState = {...};` в теге <script>.
   • JSON Path: `api.queries["streams({channel_id},)"].data.results`
   • Поля: `id` (ID стрима), `title` (Название), `category.name` (Имя игры), `is_livestream` (Булево)

3. ПОИСК ИГР/КАТЕГОРИЙ (Публичный эндпоинт):
   • GET https://rutube.ru/api/video/category/ (Возвращает плоский JSON-список категорий)
   • Response: [{"id": 22, "name": "Видеоигры"}, {"id": 78, "name": "Обзоры"}]

4. ЧТЕНИЕ ПАРАМЕТРОВ СТРИМА (Приватный Студийный эндпоинт):
   • GET https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/
   • Headers: Cookie: ...; X-CSRFToken: ...
   • Response: Полная JSON-структура параметров трансляции.

5. ОБНОВЛЕНИЕ ПАРАМЕТРОВ (Приватный Студийный эндпоинт - Метод POST!):
   • POST https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/
   • Headers: Cookie: ...; X-CSRFToken: ... (csrf-токен извлекается из куки csrftoken)
   • Body (JSON): Полный набор полей для предотвращения сброса настроек (Паттерн Read-Modify-Write)
     {
       "title": "...", "category": ID_число, "description": "...", 
       "hide_chat": bool, "push_auto_start": bool, "is_donate_allowed": bool, 
       "is_adult": bool, "is_hidden": bool, "is_chat_saved": bool
     }
========================================================================================
"""

import re
import json
import httpx
from app.plugins.base import BasePlugin
from app.utils.logger import logger
from app.utils import token_parser
from app.utils import http_client


class RutubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.channel_id = self.config.get("channel_id", "").strip()
        self.token = self.config.get("token", "").strip()

    @property
    def broadcast_id(self):
        """Возвращает зафиксированный ID стрима из настроек (если задан вручную)."""
        return self.config.get("broadcast_id", "").strip()

    @property
    def headers(self):
        hdrs = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://studio.rutube.ru",
            "Referer": "https://studio.rutube.ru/"
        }
        if self.token:
            cleaned_cookies = token_parser.parse_any_cookie_format(self.token)
            if token_parser.is_cookie_format(cleaned_cookies):
                hdrs["Cookie"] = cleaned_cookies
                # Извлекаем защитный csrftoken из кук для прохождения Django-защиты Студии RUTUBE
                csrf = token_parser.extract_cookie(cleaned_cookies, "csrftoken")
                if csrf:
                    hdrs["X-CSRFToken"] = csrf
            else:
                hdrs["Authorization"] = f"Token {self.token}"
        return hdrs

    async def _fetch_channel_html(self) -> str:
        """Скачивает публичную страницу канала RUTUBE без прохождения авторизации."""
        owner = self.channel_id
        if not owner:
            return ""

        urls = []
        if owner.isdigit():
            urls.append(f"https://rutube.ru/channel/{owner}/")
        urls.append(f"https://rutube.ru/video/person/{owner}/")

        async with http_client.create_client(timeout=10.0) as client:
            for url in urls:
                try:
                    resp = await client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    if resp.status_code == 200 and "window.reduxState" in resp.text:
                        return resp.text
                except Exception:
                    pass
        return ""

    def _parse_streams_from_html(self, html: str) -> list:
        """Извлекает и декодирует все данные о трансляциях из Redux-состояния страницы."""
        if not html:
            return []

        match = re.search(r"window\.reduxState\s*=\s*(\{.+?\})\s*;?\s*</script>", html, re.DOTALL)
        if not match:
            return []

        json_str = match.group(1)
        # Исправляем JS-специфичные hex-эскейпы (\x3d, \x26), ломающие json.loads
        json_str_cleaned = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), json_str)

        try:
            data = json.loads(json_str_cleaned, strict=False)
            queries = data.get("api", {}).get("queries", {})

            broadcasts = []
            for query_key, query_val in queries.items():
                if "streams(" in query_key:
                    results = query_val.get("data", {}).get("results", [])
                    for stream in results:
                        if isinstance(stream, dict):
                            broadcasts.append({
                                "id": str(stream.get("id")),
                                "title": stream.get("title") or "Без названия",
                                "game": stream.get("category", {}).get("name") or "Разное",
                                "is_live": stream.get("is_livestream", False)
                            })
            return broadcasts
        except Exception as e:
            logger.debug(f"RUTUBE HTML Parser: Ошибка декодирования ReduxState: {e!r}")

        return []

    # ── Чтение статуса ────────────────────────────────────────────────────────

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}
        if not self.channel_id:
            return status

        try:
            # 1. Загружаем и парсим данные прямо из HTML страницы (100% обход QRATOR)
            html = await self._fetch_channel_html()
            broadcasts = self._parse_streams_from_html(html)

            if broadcasts:
                target_id = self.broadcast_id
                target_stream = None

                if target_id:
                    for b in broadcasts:
                        if b["id"] == str(target_id):
                            target_stream = b
                            break

                if not target_stream:
                    for b in broadcasts:
                        if b["is_live"]:
                            target_stream = b
                            break
                    if not target_stream:
                        target_stream = broadcasts[0]

                status.update({
                    "is_live": target_stream["is_live"],
                    "title": target_stream["title"],
                    "game": target_stream["game"]
                })
                return status

            # Резервный опрос через старый JSON API
            async with http_client.create_client(timeout=10.0) as client:
                url = f"https://rutube.ru/api/video/person/{self.channel_id}/"
                resp = await client.get(url)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    for item in results:
                        if isinstance(item, dict):
                            is_stream = item.get("is_live", False) or item.get("is_online", False) or "stream" in str(
                                item.get("category", {}).get("short_name", "")).lower()
                            if is_stream:
                                status.update({
                                    "is_live": item.get("is_live", False) or item.get("is_online", False),
                                    "viewers": item.get("viewers_count", 0),
                                    "title": item.get("title") or "",
                                    "game": item.get("category", {}).get("name", "Разное")
                                })
                                return status
        except Exception as e:
            logger.error(f"RUTUBE: Ошибка get_status: {e!r}")
        return status

    # ── Получение списка трансляций ──────────────────────────────────────────

    async def get_broadcasts(self) -> list:
        """Загружает список трансляций из Redux-состояния страницы."""
        try:
            html = await self._fetch_channel_html()
            broadcasts = self._parse_streams_from_html(html)
            if broadcasts:
                return [
                    {
                        "id": b["id"],
                        "title": b["title"],
                        "status": "live" if b["is_live"] else "offline"
                    }
                    for b in broadcasts
                ]
        except Exception as e:
            logger.error(f"RUTUBE: Ошибка get_broadcasts: {e!r}")
        return []

    # ── Вспомогательный метод записи (Паттерн Read-Modify-Write) ──

    async def _update_stream_info(self, broadcast_id: str, **kwargs) -> str:
        try:
            async with http_client.create_client(timeout=10.0) as client:
                # 1. Читаем текущее состояние стрима
                get_url = f"https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/"
                get_resp = await client.get(get_url, headers=self.headers)
                if get_resp.status_code != 200:
                    return f"RUTUBE: Ошибка чтения параметров ({get_resp.status_code}): {get_resp.text[:100]}"

                stream_data = get_resp.json()

                # 2. Перезаписываем изменившиеся поля
                for k, v in kwargs.items():
                    stream_data[k] = v

                # Формируем полный пакет настроек для сохранения
                payload = {
                    "title": stream_data.get("title", ""),
                    "category": stream_data.get("category"),
                    "description": stream_data.get("description", ""),
                    "hide_chat": stream_data.get("hide_chat", False),
                    "push_auto_start": stream_data.get("push_auto_start", False),
                    "is_donate_allowed": stream_data.get("is_donate_allowed", False),
                    "is_adult": stream_data.get("is_adult", False),
                    "is_hidden": stream_data.get("is_hidden", False),
                    "is_chat_saved": stream_data.get("is_chat_saved", True)
                }

                # 3. Отправляем полный пакет на сервер методом POST
                post_url = f"https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/"
                post_resp = await client.post(post_url, headers=self.headers, json=payload)

                if post_resp.status_code in (200, 201, 204):
                    return "RUTUBE: Настройки трансляции успешно обновлены"
                return f"RUTUBE Ошибка ({post_resp.status_code}): {post_resp.text[:150]}"
        except Exception as e:
            return f"RUTUBE Исключение при записи: {e!r}"

    # ── Запись ────────────────────────────────────────────────────────────────

    async def set_title(self, title: str) -> str:
        if not self.token:
            return "RUTUBE: Смена названия недоступна (требуется API Token или Cookies)"

        broadcast_id = self.broadcast_id
        if not broadcast_id:
            broadcasts = await self.get_broadcasts()
            if not broadcasts:
                return "RUTUBE: Активные трансляции не найдены (проверьте ID канала в настройках)"
            broadcast_id = broadcasts[0]["id"]

        return await self._update_stream_info(broadcast_id, title=title)

    async def set_game(self, game: str) -> str:
        if not self.token:
            return "RUTUBE: Смена категории недоступна (требуется API Token или Cookies)"

        # 1. Поиск ID категории на исправленном эндпоинте RUTUBE (единственное число)
        category_id = None
        try:
            async with http_client.create_client(timeout=10.0) as client:
                cat_url = "https://rutube.ru/api/video/category/"
                cat_resp = await client.get(cat_url)
                if cat_resp.status_code == 200:
                    categories_list = cat_resp.json()
                    if isinstance(categories_list, list):
                        for cat in categories_list:
                            if game.lower() in cat.get("name", "").lower():
                                category_id = cat.get("id")
                                break
        except Exception as e:
            logger.debug(f"RUTUBE: Ошибка поиска категории: {e!r}")

        if not category_id:
            return f"RUTUBE: Категория '{game}' не найдена в каталоге"

        # 2. Нахождение ID трансляции
        broadcast_id = self.broadcast_id
        if not broadcast_id:
            broadcasts = await self.get_broadcasts()
            if not broadcasts:
                return "RUTUBE: Трансляции не найдены"
            broadcast_id = broadcasts[0]["id"]

        # 3. Обновление
        return await self._update_stream_info(broadcast_id, category=category_id)
