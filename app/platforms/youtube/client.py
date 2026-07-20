import datetime
import mimetypes
import os
from app.utils import http_client
from app.utils.logger import logger


class YouTubeApiClient:
    def __init__(self, plugin):
        self.plugin = plugin

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.plugin.token}"}

    async def fetch_status(self, broadcast_id: str) -> dict:
        status = {
            "is_live": False, "viewers": 0, "title": "", "game": "",
            "likes": 0, "dislikes": 0, "custom_status": "",
            "needs_publish": False, "can_stop": False
        }

        # Ошибки таймаута пробрасываются в планировщик, не прерывая стабильное отображение в GUI
        async with http_client.create_client(timeout=20.0) as client:
            url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={broadcast_id}"
            resp = await client.get(url, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

            if data.get("items"):
                item = data["items"][0]
                lifecycle = item["status"]["lifeCycleStatus"]
                privacy = item["status"].get("privacyStatus", "public")

                status["is_live"] = (lifecycle == "live")
                status["title"] = item["snippet"]["title"]
                status["needs_publish"] = (privacy in ("private", "unlisted"))
                status["can_stop"] = (lifecycle == "live")

                if lifecycle == "upcoming":
                    status["custom_status"] = "🟡 НА ПОДГОТОВКЕ"
                elif lifecycle == "live":
                    status["custom_status"] = "🟢 В ЭФИРЕ"
                elif lifecycle == "completed":
                    status["custom_status"] = "🔴 ЗАВЕРШЕН"
                else:
                    status["custom_status"] = "🔴 ОФФЛАЙН"

                video_url = f"https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet,statistics&id={item['id']}"
                v_resp = await client.get(video_url, headers=self.headers)
                v_resp.raise_for_status()
                v_data = v_resp.json()

                if v_data.get("items"):
                    v_item = v_data["items"][0]
                    lsd = v_item.get("liveStreamingDetails", {})
                    stats = v_item.get("statistics", {})

                    status["viewers"] = int(lsd.get("concurrentViewers", 0))
                    status["likes"] = int(stats.get("likeCount", 0))
                    status["dislikes"] = int(stats.get("dislikeCount", 0))
                    status["game"] = v_item["snippet"].get("categoryId", "")
        return status

    async def fetch_broadcasts(self) -> list:
        try:
            async with http_client.create_client(timeout=15.0) as client:
                resp = await client.get(
                    "https://youtube.googleapis.com/youtube/v3/liveBroadcasts",
                    params={"part": "id,snippet,status", "broadcastStatus": "all", "maxResults": 15},
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
            logger.error(f"YouTube Client: ошибка получения списка трансляций: {e}")
        return []

    async def fetch_live_streams(self) -> list:
        try:
            async with http_client.create_client(timeout=15.0) as client:
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
            logger.error(f"YouTube Client: ошибка liveStreams: {e}")
        return []

    async def update_title(self, broadcast_id: str, title: str) -> str:
        async with http_client.create_client() as client:
            url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet&id={broadcast_id}"
            current = await client.get(url, headers=self.headers)
            data = current.json()
            if not data.get("items"):
                return "YouTube: Трансляция не найдена"

            snippet = data["items"][0]["snippet"]
            snippet["title"] = title
            update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet"
            resp = await client.put(update_url, headers=self.headers, json={"id": broadcast_id, "snippet": snippet})
            return "YouTube: Заголовок изменен" if resp.status_code == 200 else f"YouTube Ошибка: {resp.text}"

    async def update_category(self, broadcast_id: str, category_id: str) -> str:
        try:
            async with http_client.create_client() as client:
                url = f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet&id={broadcast_id}"
                resp = await client.get(url, headers=self.headers)
                if resp.status_code != 200:
                    return f"YouTube Ошибка чтения метаданных: {resp.text}"

                data = resp.json()
                if not data.get("items"):
                    return "YouTube: Объект видеотрансляции не найден"

                video_item = data["items"][0]
                snippet = video_item["snippet"]
                snippet["categoryId"] = category_id

                update_url = "https://youtube.googleapis.com/youtube/v3/videos?part=snippet"
                update_resp = await client.put(update_url, headers=self.headers,
                                               json={"id": broadcast_id, "snippet": snippet})
                if update_resp.status_code == 200:
                    return f"YouTube: Категория изменена на ID {category_id}"
                return f"YouTube Ошибка обновления категории: {update_resp.text}"
        except Exception as e:
            return f"YouTube Исключение при обновлении: {e!r}"

    async def create_broadcast(self, title: str, game_category_id: str, description: str, stream_id: str, latency: str,
                               is_shorts: bool) -> dict:
        if is_shorts:
            if "#shorts" not in title.lower():
                title = f"{title} #shorts"
            if "#shorts" not in description.lower():
                description = f"{description}\n\n#shorts"

        start_time = (datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            async with http_client.create_client(timeout=20.0) as client:
                selected_stream_id = stream_id
                stream_key = ""

                if not selected_stream_id:
                    streams_url = "https://youtube.googleapis.com/youtube/v3/liveStreams"
                    streams_resp = await client.get(streams_url, params={"part": "id,cdn", "mine": "true"},
                                                    headers=self.headers)
                    if streams_resp.status_code == 200:
                        items = streams_resp.json().get("items", [])
                        if items:
                            selected_stream_id = items[0]["id"]
                            stream_key = items[0].get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")
                else:
                    streams_url = "https://youtube.googleapis.com/youtube/v3/liveStreams"
                    streams_resp = await client.get(streams_url, params={"part": "id,cdn", "id": selected_stream_id},
                                                    headers=self.headers)
                    if streams_resp.status_code == 200:
                        items = streams_resp.json().get("items", [])
                        if items:
                            stream_key = items[0].get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")

                if not selected_stream_id:
                    streams_url = "https://youtube.googleapis.com/youtube/v3/liveStreams"
                    create_stream_resp = await client.post(
                        streams_url, params={"part": "snippet,cdn"}, headers=self.headers,
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
                    return {"success": False, "error": "YouTube: Не удалось создать поток трансляции"}

                broadcast_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts"
                payload = {
                    "snippet": {
                        "title": title,
                        "description": description or "Запланированная трансляция создана через StreamTail",
                        "scheduledStartTime": start_time
                    },
                    "status": {"privacyStatus": "private"},
                    "contentDetails": {
                        "latencyPreference": latency,
                        "enableAutoStart": True,
                        "enableAutoStop": True,
                        "monitorStream": {"enableMonitorStream": False}
                    }
                }
                b_resp = await client.post(broadcast_url, params={"part": "snippet,status,contentDetails"},
                                           headers=self.headers, json=payload)
                if b_resp.status_code not in (200, 201):
                    return {"success": False, "error": f"YouTube: Ошибка создания события: {b_resp.text}"}

                broadcast_data = b_resp.json()
                broadcast_id = broadcast_data["id"]

                bind_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts/bind"
                bind_resp = await client.post(bind_url, params={"id": broadcast_id, "part": "id,contentDetails",
                                                                "streamId": selected_stream_id}, headers=self.headers)
                if bind_resp.status_code != 200:
                    return {"success": False, "error": "YouTube: Ошибка связывания трансляции"}

                return {
                    "success": True,
                    "broadcast_id": broadcast_id,
                    "perm_key": stream_key,
                    "title": title
                }
        except Exception as e:
            return {"success": False, "error": f"YouTube: Ошибка при создании стрима: {e!r}"}

    async def publish_broadcast(self, broadcast_id: str) -> str:
        try:
            async with http_client.create_client(timeout=20.0) as client:
                url = f"https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status&id={broadcast_id}"
                current = await client.get(url, headers=self.headers)
                data = current.json()
                if not data.get("items"):
                    return "YouTube: Событие не найдено"

                item = data["items"][0]
                snippet = item["snippet"]
                status = item["status"]
                status["privacyStatus"] = "public"

                update_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status"
                resp = await client.put(update_url, headers=self.headers,
                                        json={"id": broadcast_id, "snippet": snippet, "status": status})
                if resp.status_code == 200:
                    return "YouTube: Стрим успешно опубликован!"
                return f"YouTube: Ошибка публикации: {resp.text}"
        except Exception as e:
            return f"YouTube: Ошибка публикации: {e!r}"

    async def stop_broadcast(self, broadcast_id: str) -> str:
        try:
            async with http_client.create_client(timeout=20.0) as client:
                transition_url = "https://youtube.googleapis.com/youtube/v3/liveBroadcasts/transition"
                resp = await client.post(
                    transition_url, params={"id": broadcast_id, "broadcastStatus": "complete", "part": "id,status"},
                    headers=self.headers
                )
                if resp.status_code == 200:
                    return "YouTube: Трансляция успешно завершена!"
                return f"YouTube: Ошибка завершения: {resp.text}"
        except Exception as e:
            return f"YouTube: Исключение при завершении трансляции: {e!r}"

    async def upload_thumbnail_image(self, broadcast_id: str, image_path: str) -> str:
        if not os.path.exists(image_path):
            return f"YouTube: Файл обложки '{image_path}' не найден"

        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"

        try:
            with open(image_path, "rb") as f:
                image_data = f.read()

            headers = {
                "Authorization": f"Bearer {self.plugin.token}",
                "Content-Type": mime_type,
                "Content-Length": str(len(image_data))
            }

            async with http_client.create_client(timeout=30.0) as client:
                url = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
                resp = await client.post(url, params={"videoId": broadcast_id}, headers=headers, content=image_data)
                if resp.status_code == 200:
                    return "YouTube: Обложка трансляции успешно обновлена!"
                return f"YouTube: Ошибка загрузки обложки: {resp.text}"
        except Exception as e:
            return f"YouTube: Исключение при загрузке обложки: {e!r}"
