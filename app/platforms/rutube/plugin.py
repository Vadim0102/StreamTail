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

6. ОПУБЛИКОВАТЬ СТРИМ (Перевод из приватного в публичный режим - Выявлено по HAR-анализу!):
   • POST https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/
   • Headers: Cookie: ...; X-CSRFToken: ...; Idempotency-Key: "..."
   • Body (JSON): {"access_status": "public"}
   • Response (200): {"video": "...", "access_status": "public", "stream_status": "actual"/"wait"}

7. СЧЕТЧИК ЛАЙКОВ И ДИЗЛАЙКОВ (Выявлено по HAR-анализу!):
   • GET https://studio.rutube.ru/api/numerator/video/{broadcast_id}/vote
   • Response (200): {"positive": 10, "negative": 1}

8. ЗАВЕРШЕНИЕ СТРИМА (Перевод в статус done - Выявлено по HAR-анализу!):
   • POST https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/
   • Headers: Cookie: ...; X-CSRFToken: ...; Idempotency-Key: "..."
   • Body (JSON): {"stream_status": "done"}
   • Response (200): {"video": "...", "stream_status": "done", "input_servers": {"primary": null, "secondary": null}}
========================================================================================

# 📖 Техническая документация RUTUBE Studio API (Создание стрима)

Все запросы к RUTUBE Studio требуют прохождения Django-защиты и авторизации. Для этого необходимо передавать куки (включая `session_id`, `jwt`, `csrftoken`) и обязательно дублировать защитный токен в заголовке `x-csrftoken`.

---

### 1. Инициализация (создание) трансляции
Используется для первичной регистрации трансляции в Студии RUTUBE.

* **URL**: `POST https://studio.rutube.ru/api/v2/video/create/stream/`
* **Заголовки (Headers)**:
  * `Content-Type`: `application/json`
  * `Cookie`: `<заголовок кук пользователя>`
  * `x-csrftoken`: `<значение csrftoken из кук>`
  * `Idempotency-Key`: `"<20-значное уникальное число в двойных кавычках>"` (например: `"12614868624085865171"`). **Обязательный заголовок**. Если его не передать или прислать в неверном формате, RUTUBE отклонит запрос.
* **Тело запроса (Payload)**:

  {
    "stream_status": "wait",
    "title": "название стрима",
    "description": "описание стрима",
    "category": 22,
    "is_adult": false,
    "is_hidden": false
  }

  *(где `category` — ID категории, например `22` для «Видеоигры»)*
* **Ответ (Response, код 200)**:

  {
    "video": "fc61f2fd749a31fea6cd022c75f0e04e"
  }

  Поле `"video"` содержит в себе уникальный **`broadcast_id`** созданной трансляции.

---

### 2. Генерация / Активация ключа трансляции (Stream Key)
Сразу после инициализации видео RUTUBE требует отправить POST-запрос для генерации и активации постоянного (или переменного) ключа трансляции (Stream Key).

* **URL**: `POST https://studio.rutube.ru/api/v1/video/stream/{broadcast_id}/permkey/`
* **Заголовки (Headers)**:
  * `Content-Type`: `application/json`
  * `Cookie`: `<куки>`
  * `x-csrftoken`: `<csrftoken>`
  * `Idempotency-Key`: `"<новый уникальный 20-значный ID в кавычках>"`
* **Тело запроса (Payload)**:

  {
    "is_active": true
  }

* **Ответ (Response, код 200)**:

  {
    "id": 21481,
    "previous_video_id": "62a597d646ebed34301cd93c9c1a4dc3",
    "channel_id": 79465289,
    "perm_key": "perm_e0bc988502a045668a69d64e78784866?sinfo=P2Vwr1UwkYpe7SVdm57esQna24QWa9OR",
    "generate_count": 3
  }

  Поле **`"perm_key"`** содержит искомый ключ трансляции (Stream Key), который стример вставляет в OBS Studio.

"""

import re
import json
import random
import httpx
from app.plugins.base import BasePlugin
from app.utils.logger import logger
from app.utils import token_parser
from app.utils import http_client


class RutubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)

    @property
    def channel_id(self) -> str:
        """Динамически возвращает ID канала (исправляет баг кэширования при сохранении настроек)."""
        raw = self.config.get("channel_id", "").strip()
        if not raw:
            return ""
        if "/" in raw:
            return raw.rstrip("/").split("/")[-1]
        return raw

    @property
    def token(self) -> str:
        """Динамически возвращает токен из измененного интерфейса настроек."""
        return self.config.get("token", "").strip()

    @property
    def broadcast_id(self) -> str:
        """Возвращает зафиксированный ID стрима из настроек (если задан вручную)."""
        return self.config.get("broadcast_id", "").strip()

    @property
    def headers(self) -> dict:
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
                # Извлекаем защитный csrftoken из кук (регистронезависимо)
                csrf = token_parser.extract_cookie(cleaned_cookies, "csrftoken") or \
                       token_parser.extract_cookie(cleaned_cookies, "x-csrftoken")
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

        # Поиск блока ReduxState (улучшенное регулярное выражение)
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
        status = {
            "is_live": False,
            "viewers": 0,
            "title": "",
            "game": "",
            "likes": 0,
            "dislikes": 0,
            "custom_status": "",
            "needs_publish": False,
            "can_stop": False
        }
        if not self.channel_id:
            return status

        # Если у нас есть API токен/куки и задан broadcast_id, запрашиваем расширенный статус из Студии
        if self.token and self.broadcast_id:
            try:
                async with http_client.create_client(timeout=10.0) as client:
                    # 1. Запрос параметров трансляции
                    stream_url = f"https://studio.rutube.ru/api/v2/video/stream/{self.broadcast_id}/"
                    resp = await client.get(stream_url, headers=self.headers)

                    # 2. Запрос счетчика лайков/дизлайков
                    vote_url = f"https://studio.rutube.ru/api/numerator/video/{self.broadcast_id}/vote"
                    vote_resp = await client.get(vote_url, headers=self.headers)

                    likes = 0
                    dislikes = 0
                    if vote_resp.status_code == 200:
                        vote_data = vote_resp.json()
                        likes = vote_data.get("positive", 0)
                        dislikes = vote_data.get("negative", 0)

                    if resp.status_code == 200:
                        stream_data = resp.json()

                        # Состояния из API: wait - На подготовке, actual - В эфире, done - Завершен
                        stream_state = stream_data.get("stream_status", "wait")
                        access_state = stream_data.get("access_status", "private")

                        is_live = (stream_state == "actual")
                        needs_publish = (access_state == "private" and stream_state == "wait")
                        can_stop = (stream_state == "actual")

                        # Маппинг кастомных статусов
                        if stream_state == "wait":
                            custom_status = "🟡 НА ПОДГОТОВКЕ"
                        elif stream_state == "actual":
                            custom_status = "🟢 В ЭФИРЕ"
                        elif stream_state == "done":
                            custom_status = "🔴 ЗАВЕРШЕН"
                        else:
                            custom_status = "🔴 ОФФЛАЙН"

                        # Оптимизация получения категории (сначала берем из структуры ответа)
                        category_val = stream_data.get("category")
                        category_name = "Разное"

                        if isinstance(category_val, dict):
                            category_name = category_val.get("name", "Разное")
                        elif category_val:
                            # Метод-дублер, если пришел только числовой ID
                            cat_url = "https://rutube.ru/api/video/category/"
                            cat_resp = await client.get(cat_url)
                            if cat_resp.status_code == 200:
                                categories_list = cat_resp.json()
                                if isinstance(categories_list, list):
                                    for cat in categories_list:
                                        if cat.get("id") == category_val:
                                            category_name = cat.get("name", "Разное")
                                            break

                        # Пытаемся получить число зрителей, если стрим запущен в эфир
                        viewers = 0
                        if is_live:
                            try:
                                url_person = f"https://rutube.ru/api/video/person/{self.channel_id}/"
                                person_resp = await client.get(url_person, headers=self.headers)
                                if person_resp.status_code == 200:
                                    results = person_resp.json().get("results", [])
                                    for item in results:
                                        if isinstance(item, dict) and str(item.get("id")) == str(self.broadcast_id):
                                            viewers = item.get("viewers_count", 0)
                                            break
                            except Exception:
                                pass

                        status.update({
                            "is_live": is_live,
                            "viewers": viewers,
                            "title": stream_data.get("title", ""),
                            "game": category_name,
                            "likes": likes,
                            "dislikes": dislikes,
                            "custom_status": custom_status,
                            "needs_publish": needs_publish,
                            "can_stop": can_stop
                        })
                        return status
            except Exception as e:
                logger.debug(f"RUTUBE Studio API: ошибка расширенного опроса: {e!r}")

        # Публичный опрос через HTML-парсер (если нет авторизации/токена)
        try:
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
                    # Приоритизируем живые (публичные) стримы
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
                resp = await client.get(url, headers=self.headers)
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
        """Возвращает список трансляций, совмещая данные Студии и публичной страницы."""
        # Улучшение: если есть токен, сначала запрашиваем список напрямую в Студии (видны даже приватные/wait стримы)
        if self.token:
            try:
                async with http_client.create_client(timeout=10.0) as client:
                    resp = await client.get("https://studio.rutube.ru/api/v2/video/stream/", headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", []) if isinstance(data, dict) else data
                        if isinstance(results, list) and results:
                            return [
                                {
                                    "id": str(item.get("id") or item.get("video")),
                                    "title": item.get("title", "Без названия"),
                                    "status": item.get("stream_status", "offline")
                                }
                                for item in results
                            ]
            except Exception as ex:
                logger.debug(f"RUTUBE Студия: Сбой получения приватного списка трансляций: {ex!r}")

        # Fallback на парсинг публичной страницы
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

                # Очищаем поле категории от словаря, переводя в ID во избежание ошибки HTTP 400
                category_val = stream_data.get("category")
                if isinstance(category_val, dict):
                    category_id = category_val.get("id")
                else:
                    category_id = category_val

                # Формируем полный пакет настроек для сохранения
                payload = {
                    "title": stream_data.get("title", ""),
                    "category": category_id,
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

            # Приоритизируем live-стрим при автовыборе
            target = None
            for b in broadcasts:
                if b.get("status") == "live" or b.get("status") == "actual":
                    target = b
                    break
            if not target and broadcasts:
                target = broadcasts[0]

            broadcast_id = target["id"] if target else ""

        if not broadcast_id:
            return "RUTUBE: Не удалось определить ID трансляции"

        return await self._update_stream_info(broadcast_id, title=title)

    async def set_game(self, game: str) -> str:
        if not self.token:
            return "RUTUBE: Смена категории недоступна (требуется API Token или Cookies)"

        # 1. Поиск ID категории на RUTUBE
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

            # Приоритизируем live-стрим при автовыборе
            target = None
            for b in broadcasts:
                if b.get("status") == "live" or b.get("status") == "actual":
                    target = b
                    break
            if not target and broadcasts:
                target = broadcasts[0]

            broadcast_id = target["id"] if target else ""

        if not broadcast_id:
            return "RUTUBE: Не удалось определить ID трансляции"

        # 3. Обновление категории
        return await self._update_stream_info(broadcast_id, category=category_id)

    # ── Создание стрима ─────────────────────────────────────────────────────

    async def create_stream(self, title: str, game: str = "Видеоигры", description: str = "") -> dict:
        """
        Создает новую трансляцию на RUTUBE Studio.
        """
        if not self.token:
            return {"success": False, "error": "RUTUBE: Требуется API токен или Cookies"}

        # 1. Поиск ID категории
        category_id = 22  # Видеоигры по умолчанию
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
            logger.debug(f"RUTUBE: Ошибка поиска категории стрима: {e!r}")

        # 2. Формируем заголовки создания (включая Idempotency-Key и CSRF)
        headers = dict(self.headers)
        headers["Idempotency-Key"] = f'"{random.randint(10 ** 19, 10 ** 20 - 1)}"'
        headers["Content-Type"] = "application/json"

        payload = {
            "stream_status": "wait",
            "title": title,
            "description": description,
            "category": int(category_id),
            "is_adult": False,
            "is_hidden": False
        }

        try:
            async with http_client.create_client(timeout=10.0) as client:
                create_url = "https://studio.rutube.ru/api/v2/video/create/stream/"
                resp = await client.post(create_url, headers=headers, json=payload)

                if resp.status_code not in (200, 201):
                    return {"success": False, "error": f"Ошибка создания ({resp.status_code}): {resp.text[:100]}"}

                data = resp.json()
                broadcast_id = data.get("video")
                if not broadcast_id:
                    return {"success": False, "error": "RUTUBE API не вернул ID созданной трансляции"}

                # 3. Получение / активация постоянного Stream Key (permkey)
                permkey_url = f"https://studio.rutube.ru/api/v1/video/stream/{broadcast_id}/permkey/"
                headers_pk = dict(self.headers)
                headers_pk["Idempotency-Key"] = f'"{random.randint(10 ** 19, 10 ** 20 - 1)}"'
                headers_pk["Content-Type"] = "application/json"

                perm_resp = await client.post(permkey_url, headers=headers_pk, json={"is_active": True})
                perm_key = ""
                if perm_resp.status_code == 200:
                    perm_key = perm_resp.json().get("perm_key", "")

                return {
                    "success": True,
                    "broadcast_id": broadcast_id,
                    "perm_key": perm_key,
                    "title": title
                }
        except Exception as e:
            return {"success": False, "error": f"Исключение при обращении к API RUTUBE: {e!r}"}

    # ── Публикация стрима ──────────────────────────────────────────────────

    async def publish_stream(self) -> str:
        """
        Переводит трансляцию из приватного состояния подготовки ("wait")
        в публичный эфир ("actual", access_status="public").
        """
        if not self.token:
            return "RUTUBE: Смена статуса недоступна (требуется API Token или Cookies)"

        broadcast_id = self.broadcast_id
        if not broadcast_id:
            broadcasts = await self.get_broadcasts()
            if not broadcasts:
                return "RUTUBE: Активные трансляции не найдены"
            broadcast_id = broadcasts[0]["id"]

        headers = dict(self.headers)
        headers["Idempotency-Key"] = f'"{random.randint(10 ** 19, 10 ** 20 - 1)}"'
        headers["Content-Type"] = "application/json"

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/"
                resp = await client.post(url, headers=headers, json={"access_status": "public"})
                if resp.status_code == 200:
                    return "RUTUBE: Трансляция успешно опубликована!"
                return f"RUTUBE Ошибка публикации ({resp.status_code}): {resp.text[:100]}"
        except Exception as e:
            return f"RUTUBE Исключение при публикации: {e!r}"

    # ── Завершение стрима ──────────────────────────────────────────────────

    async def stop_stream(self) -> str:
        """
        Переводит трансляцию в статус "done" (Завершено) на RUTUBE Studio.
        """
        if not self.token:
            return "RUTUBE: Завершение трансляции недоступно (требуется API Token или Cookies)"

        broadcast_id = self.broadcast_id
        if not broadcast_id:
            broadcasts = await self.get_broadcasts()
            if not broadcasts:
                return "RUTUBE: Активные трансляции не найдены"
            broadcast_id = broadcasts[0]["id"]

        headers = dict(self.headers)
        headers["Idempotency-Key"] = f'"{random.randint(10 ** 19, 10 ** 20 - 1)}"'
        headers["Content-Type"] = "application/json"

        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = f"https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/"
                resp = await client.post(url, headers=headers, json={"stream_status": "done"})
                if resp.status_code == 200:
                    return "RUTUBE: Трансляция успешно завершена!"
                return f"RUTUBE Ошибка завершения ({resp.status_code}): {resp.text[:100]}"
        except Exception as e:
            return f"RUTUBE Исключение при завершении: {e!r}"
