"""
YouTube Data API v3 Integration Plugin.

========================================================================================
                                     YOUTUBE API MAP
========================================================================================

1. ЧТЕНИЕ СТАТУСА ТРАНСЛЯЦИИ:
   • GET https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={broadcast_id}
   • Headers: Authorization: Bearer <token>
   • Response: {"items": [{"status": {"lifeCycleStatus": "live"}, "snippet": {"title": "Stream Title"}}]}

2. ПОЛУЧЕНИЕ ЧИСЛА ЗРИТЕЛЕЙ И ЛАЙКОВ:
   • GET https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet,statistics&id={broadcast_id}
   • Response: {"items": [{"liveStreamingDetails": {"concurrentViewers": "150"}, "statistics": {"likeCount": "12"}}]}

3. СПИСОК ВСЕХ ТРАНСЛЯЦИЙ:
   • GET https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=id,snippet,status&broadcastStatus=all&maxResults=15
   • Response: Список всех трансляций пользователя для окна «Выбор стрима».

4. ОБНОВЛЕНИЕ ТИТЛА ТРАНСЛЯЦИИ (Метод PUT, паттерн Read-Modify-Write):
   • PUT https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet
   • Body (JSON): {"id": "{broadcast_id}", "snippet": { ... "title": "New Title" ... }}

5. СОЗДАНИЕ ЗАПЛАНИРОВАННОЙ ТРАНСЛЯЦИИ (Метод POST):
   • POST https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status,contentDetails
   • Body (JSON): {"snippet": {"title": "...", "scheduledStartTime": "ISO_8601"}, "status": {"privacyStatus": "public"}, "contentDetails": {"latencyPreference": "ultraLow"}}

6. СВЯЗЫВАНИЕ ТРАНСЛЯЦИИ С ПОТОКОМ (Метод POST):
   • POST https://youtube.googleapis.com/youtube/v3/liveBroadcasts/bind?id={broadcast_id}&streamId={stream_id}&part=id,contentDetails

7. ОПУБЛИКОВАТЬ ТРАНСЛЯЦИЮ (Перевод в public - Метод PUT):
   • PUT https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status
   • Body (JSON): {"id": "...", "snippet": {...}, "status": {"privacyStatus": "public"}}

8. ЗАВЕРШЕНИЕ ТРАНСЛЯЦИИ (Метод POST):
   • POST https://youtube.googleapis.com/youtube/v3/liveBroadcasts/transition?id={broadcast_id}&broadcastStatus=complete&part=id,status

9. ЗАГРУЗКА ОБЛОЖКИ/ПРЕВЬЮ (Метод POST):
   • POST https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={broadcast_id}
========================================================================================
"""

import datetime
import mimetypes
import os
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger
from app.utils import http_client


class YouTubePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.innertube_context = {
            "client": {"clientName": 62, "clientVersion": "1.20260422.03.00", "hl": "ru", "gl": "RU"}
        }

    @property
    def token_data(self):
        return get_token("youtube") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def broadcast_id(self):
        return self.token_data.get("broadcast_id") or self.config.get("broadcast_id")

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def _ensure_token_valid(self) -> bool:
        if is_token_valid("youtube"):
            return True

        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id")
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import youtube_auth
            logger.info("YouTube: токен истек. Выполняем автоматический refresh...")
            return await youtube_auth.refresh(c_id, c_sec, r_token)
        return False

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
        if not self.token:
            return status

        await self._ensure_token_valid()

        # Автовыбор, если broadcast_id отсутствует
        broadcast_id = self.broadcast_id
        if not broadcast_id:
            from app.auth.youtube_auth import _fetch_broadcast_id
            from app.auth.token_store import set_token
            bid = await _fetch_broadcast_id(self.token)
            if bid:
                broadcast_id = bid
                tdata = self.token_data
                tdata["broadcast_id"] = bid
                set_token("youtube", tdata)
            else:
                return status

        try:
            async with http_client.create_client() as client:
                url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={broadcast_id}"
                resp = await client.get(url, headers=self.headers)
                data = resp.json()

                if data.get("items"):
                    item = data["items"][0]
                    lifecycle = item["status"]["lifeCycleStatus"]  # live, upcoming, completed, testing
                    privacy = item["status"].get("privacyStatus", "public")

                    status["is_live"] = (lifecycle == "live")
                    status["title"] = item["snippet"]["title"]
                    # Если стрим скрытый или приватный, предлагаем Опубликовать
                    status["needs_publish"] = (privacy in ("private", "unlisted"))
                    status["can_stop"] = (lifecycle == "live")

                    # Трактуем кастомные статусы [2.1]
                    if lifecycle == "upcoming":
                        status["custom_status"] = "🟡 НА ПОДГОТОВКЕ"
                    elif lifecycle == "live":
                        status["custom_status"] = "🟢 В ЭФИРЕ"
                    elif lifecycle == "completed":
                        status["custom_status"] = "🔴 ЗАВЕРШЕН"
                    else:
                        status["custom_status"] = "🔴 ОФФЛАЙН"

                    # Получаем статистику видео (зрители, лайки, дизлайки) [2.1, 2.1]
                    video_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet,statistics&id={item['id']}"
                    v_resp = await client.get(video_url, headers=self.headers)
                    v_data = v_resp.json()

                    if v_data.get("items"):
                        v_item = v_data["items"][0]
                        lsd = v_item.get("liveStreamingDetails", {})
                        stats = v_item.get("statistics", {})

                        status["viewers"] = int(lsd.get("concurrentViewers", 0))
                        status["likes"] = int(stats.get("likeCount", 0))
                        status["dislikes"] = int(stats.get("dislikeCount", 0))
                        status["game"] = v_item["snippet"].get("categoryId", "")
        except Exception as e:
            logger.error(f"Ошибка статуса YouTube: {e!r}")
        return status

    async def get_broadcasts(self) -> list:
        if not self.token:
            return []
        await self._ensure_token_valid()
        try:
            async with http_client.create_client(timeout=10) as client:
                resp = await client.get(
                    "https://youtube.googleapis.com/youtube/v3/liveBroadcasts",
                    params={
                        "part": "id,snippet,status",
                        "broadcastStatus": "all",
                        "maxResults": 15,
                    },
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    return [
                        {
                            "id": item["id"],
                            "title": item["snippet"]["title"],
                            "status": f"{item['status']['lifeCycleStatus']} | {item['status'].get('privacyStatus', 'public')}"
                        }
                        for item in items
                    ]
        except Exception as e:
            logger.error(f"YouTube: Ошибка получения списка трансляций: {e}")
        return []

    async def set_title(self, title: str) -> str:
        if not self.token: return "YouTube: Нет токена"
        await self._ensure_token_valid()
        async with http_client.create_client() as client:
            url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&id={self.broadcast_id}"
            current = await client.get(url, headers=self.headers)
            data = current.json()
            if not data.get("items"): return "YouTube: Трансляция не найдена"

            snippet = data["items"][0]["snippet"]
            snippet["title"] = title
            update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet"
            resp = await client.put(update_url, headers=self.headers,
                                    json={"id": self.broadcast_id, "snippet": snippet})
            return "YouTube: Заголовок изменен" if resp.status_code == 200 else f"YouTube Ошибка: {resp.text}"

    async def set_game(self, game: str) -> str:
        """Реализовано: Изменение категории (игры) YouTube-трансляции через endpoint Videos по паттерну RMW."""
        if not self.token:
            return "YouTube: Нет токена"
        await self._ensure_token_valid()

        broadcast_id = self.broadcast_id
        if not broadcast_id:
            return "YouTube: Не определен ID трансляции"

        # Нормализация популярных имен категорий в ID категорий YouTube
        categories_map = {
            "gaming": "20",
            "games": "20",
            "игры": "20",
            "people": "22",
            "blogs": "22",
            "блоги": "22",
            "entertainment": "24",
            "развлечения": "24",
            "music": "10",
            "музыка": "10",
            "education": "27",
            "образование": "27",
            "tech": "28",
            "science": "28",
            "наука": "28",
            "технологии": "28"
        }

        normalized = game.lower().strip()
        category_id = "20"  # Игры по умолчанию
        for k, v in categories_map.items():
            if k in normalized:
                category_id = v
                break

        if normalized.isdigit():
            category_id = normalized

        try:
            async with http_client.create_client() as client:
                # Читаем данные видео
                url = f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet&id={broadcast_id}"
                resp = await client.get(url, headers=self.headers)
                if resp.status_code != 200:
                    return f"YouTube Ошибка чтения метаданных ({resp.status_code}): {resp.text}"

                data = resp.json()
                if not data.get("items"):
                    return "YouTube: Объект видеотрансляции не найден"

                video_item = data["items"][0]
                snippet = video_item["snippet"]
                snippet["categoryId"] = category_id

                # Обновляем категорию на YouTube
                update_url = "https://youtube.googleapis.com/youtube/v3/videos?part=snippet"
                update_resp = await client.put(
                    update_url,
                    headers=self.headers,
                    json={
                        "id": broadcast_id,
                        "snippet": snippet
                    }
                )
                if update_resp.status_code == 200:
                    return f"YouTube: Категория успешно изменена на ID {category_id}"
                return f"YouTube Ошибка обновления категории ({update_resp.status_code}): {update_resp.text[:150]}"
        except Exception as e:
            return f"YouTube Исключение при обновлении: {e!r}"

    # ── Получение списка liveStreams (потоков) для выбора ──

    async def get_live_streams(self) -> list:
        """Возвращает список доступных RTMP-ключей (liveStreams) пользователя."""
        if not self.token:
            return []
        await self._ensure_token_valid()
        try:
            async with http_client.create_client(timeout=10.0) as client:
                url = "https://youtube.googleapis.com/youtube/v3/liveStreams"
                resp = await client.get(
                    url,
                    params={"part": "id,snippet,cdn", "mine": "true", "maxResults": 25},
                    headers=self.headers
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    return [
                        {
                            "id": item["id"],
                            "title": item["snippet"]["title"],
                            "stream_key": item.get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")
                        }
                        for item in items
                    ]
        except Exception as e:
            logger.error(f"YouTube: ошибка получения liveStreams: {e}")
        return []

    # ── Создание стрима ──

    async def create_stream(self, title: str, game: str = "20", description: str = "", stream_id: str = None, latency: str = "ultraLow", is_shorts: bool = False) -> dict:
        """
        Создает запланированную трансляцию на YouTube с выбором задержки, ключа потока и режима Shorts [2.1].
        """
        if not self.token:
            return {"success": False, "error": "YouTube: Требуется авторизация"}

        await self._ensure_token_valid()

        # Если включен двойной стрим (Shorts), добавляем тег #shorts к описанию и названию
        if is_shorts:
            if "#shorts" not in title.lower():
                title = f"{title} #shorts"
            if "#shorts" not in description.lower():
                description = f"{description}\n\n#shorts"

        start_time = (datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            async with http_client.create_client(timeout=15.0) as client:
                selected_stream_id = stream_id
                stream_key = ""

                # 1. Поиск/выбор liveStream
                if not selected_stream_id:
                    streams_url = "https://youtube.googleapis.com/youtube/v3/liveStreams"
                    streams_resp = await client.get(
                        streams_url,
                        params={"part": "id,cdn", "mine": "true"},
                        headers=self.headers
                    )
                    if streams_resp.status_code == 200:
                        items = streams_resp.json().get("items", [])
                        if items:
                            selected_stream_id = items[0]["id"]
                            stream_key = items[0].get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")
                else:
                    # Если ID передан, получаем его ключ
                    streams_url = "https://youtube.googleapis.com/youtube/v3/liveStreams"
                    streams_resp = await client.get(
                        streams_url,
                        params={"part": "id,cdn", "id": selected_stream_id},
                        headers=self.headers
                    )
                    if streams_resp.status_code == 200:
                        items = streams_resp.json().get("items", [])
                        if items:
                            stream_key = items[0].get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")

                # Если потоков вообще нет, создаем дефолтный
                if not selected_stream_id:
                    streams_url = "https://youtube.googleapis.com/youtube/v3/liveStreams"
                    create_stream_resp = await client.post(
                        streams_url,
                        params={"part": "snippet,cdn"},
                        headers=self.headers,
                        json={
                            "snippet": {"title": "StreamTail Stream"},
                            "cdn": {"format": "1080p", "ingestionType": "rtmp"}
                        }
                    )
                    if create_stream_resp.status_code == 200:
                        stream_data = create_stream_resp.json()
                        selected_stream_id = stream_data["id"]
                        stream_key = stream_data.get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")

                if not selected_stream_id:
                    return {"success": False, "error": "YouTube: Не удалось получить поток трансляции (liveStream)"}

                # 2. Создаем запланированную трансляцию (liveBroadcast) как private по умолчанию
                broadcast_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts"
                payload = {
                    "snippet": {
                        "title": title,
                        "description": description or "Запланированная трансляция создана через StreamTail",
                        "scheduledStartTime": start_time
                    },
                    "status": {
                        "privacyStatus": "private"  # Начинаем с приватного, чтобы была кнопка «Опубликовать»!
                    },
                    "contentDetails": {
                        "latencyPreference": latency,  # Передаем "ultraLow", "low" или "normal"
                        "enableAutoStart": True,
                        "enableAutoStop": True,
                        "monitorStream": {
                            "enableMonitorStream": False
                        }
                    }
                }
                b_resp = await client.post(
                    broadcast_url,
                    params={"part": "snippet,status,contentDetails"},
                    headers=self.headers,
                    json=payload
                )
                if b_resp.status_code not in (200, 201):
                    return {"success": False, "error": f"YouTube: Ошибка создания события ({b_resp.status_code}): {b_resp.text[:100]}"}

                broadcast_data = b_resp.json()
                broadcast_id = broadcast_data["id"]

                # 3. Связываем (bind) созданное событие с потоком
                bind_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts/bind"
                bind_resp = await client.post(
                    bind_url,
                    params={"id": broadcast_id, "part": "id,contentDetails", "streamId": selected_stream_id},
                    headers=self.headers
                )
                if bind_resp.status_code != 200:
                    return {"success": False, "error": f"YouTube: Ошибка привязки потока ({bind_resp.status_code}): {bind_resp.text[:100]}"}

                return {
                    "success": True,
                    "broadcast_id": broadcast_id,
                    "perm_key": stream_key,
                    "title": title
                }
        except Exception as e:
            return {"success": False, "error": f"YouTube: Исключение при создании стрима: {e!r}"}

    # ── Публикация трансляции (Перевод в public) ─────────────────────────────

    async def publish_stream(self) -> str:
        """
        Делает трансляцию публичной (privacyStatus="public") на YouTube.
        """
        if not self.token:
            return "YouTube: Требуется авторизация"

        await self._ensure_token_valid()

        broadcast_id = self.broadcast_id
        if not broadcast_id:
            return "YouTube: Не задан ID трансляции"

        try:
            async with http_client.create_client(timeout=15.0) as client:
                # 1. Читаем текущие параметры события
                url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status&id={broadcast_id}"
                current = await client.get(url, headers=self.headers)
                data = current.json()
                if not data.get("items"):
                    return "YouTube: Трансляция не найдена"

                item = data["items"][0]
                snippet = item["snippet"]
                status = item["status"]

                # Переключаем статус приватности на public
                status["privacyStatus"] = "public"

                # 2. Сохраняем обновленные параметры
                update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status"
                resp = await client.put(
                    update_url,
                    headers=self.headers,
                    json={
                        "id": broadcast_id,
                        "snippet": snippet,
                        "status": status
                    }
                )
                if resp.status_code == 200:
                    return "YouTube: Стрим успешно опубликован!"
                return f"YouTube Ошибка публикации ({resp.status_code}): {resp.text[:100]}"
        except Exception as e:
            return f"YouTube Исключение при публикации: {e!r}"

    # ── Завершение трансляции ─────────────────────────────────────────

    async def stop_stream(self) -> str:
        """
        Завершает трансляцию на YouTube (переводит в статус completed).
        """
        if not self.token:
            return "YouTube: Требуется авторизация"

        await self._ensure_token_valid()

        broadcast_id = self.broadcast_id
        if not broadcast_id:
            return "YouTube: Не задан ID трансляции"

        try:
            async with http_client.create_client(timeout=15.0) as client:
                transition_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts/transition"
                resp = await client.post(
                    transition_url,
                    params={
                        "id": broadcast_id,
                        "broadcastStatus": "complete",
                        "part": "id,status"
                    },
                    headers=self.headers
                )
                if resp.status_code == 200:
                    return "YouTube: Трансляция успешно завершена!"
                return f"YouTube: Ошибка завершения ({resp.status_code}): {resp.text[:100]}"
        except Exception as e:
            return f"YouTube: Исключение при завершении трансляции: {e!r}"

    # ── Загрузка обложки (thumbnails) ──

    async def upload_thumbnail(self, image_path: str) -> str:
        """
        Загружает картинку-превью (thumbnail) для текущей трансляции на YouTube.
        """
        if not self.token:
            return "YouTube: Требуется авторизация"

        await self._ensure_token_valid()

        broadcast_id = self.broadcast_id
        if not broadcast_id:
            return "YouTube: Сначала привяжите или создайте трансляцию"

        if not os.path.exists(image_path):
            return f"YouTube: Файл обложки '{image_path}' не найден"

        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"

        try:
            with open(image_path, "rb") as f:
                image_data = f.read()

            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": mime_type,
                "Content-Length": str(len(image_data))
            }

            async with http_client.create_client(timeout=30.0) as client:
                url = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
                resp = await client.post(
                    url,
                    params={"videoId": broadcast_id},
                    headers=headers,
                    content=image_data
                )
                if resp.status_code == 200:
                    return "YouTube: Обложка трансляции успешно обновлена!"
                return f"YouTube: Ошибка загрузки обложки ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            return f"YouTube: Исключение при загрузке обложки: {e!r}"
