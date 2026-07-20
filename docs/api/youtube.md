# YouTube Data API v3 Map

Управление трансляциями на YouTube требует авторизации с областью видимости `youtube.force-ssl` и использует каскадные запросы к API v3.

## 1. Чтение статуса трансляции
* **Запрос**: `GET https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=status,snippet&id={broadcast_id}`
* **Заголовки**: `Authorization: Bearer <token>`
* **Ответ**:
  ```json
  {
    "items": [
      {
        "status": {
          "lifeCycleStatus": "live",
          "privacyStatus": "public"
        },
        "snippet": {
          "title": "Название трансляции"
        }
      }
    ]
  }
  ```

## 2. Получение числа зрителей и лайков
* **Запрос**: `GET https://youtube.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet,statistics&id={broadcast_id}`
* **Ответ**:
  ```json
  {
    "items": [
      {
        "liveStreamingDetails": {
          "concurrentViewers": "150"
        },
        "statistics": {
          "likeCount": "12",
          "dislikeCount": "0"
        }
      }
    ]
  }
  ```

## 3. Обновление названия трансляции (RMW)
* **Метод**: `PUT`
* **Запрос**: `https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet`
* **Тело запроса (JSON)**:
  ```json
  {
    "id": "{broadcast_id}",
    "snippet": {
      "title": "Новое название",
      "scheduledStartTime": "ISO_8601"
    }
  }
  ```

## 4. Создание запланированной трансляции
* **Метод**: `POST`
* **Запрос**: `https://youtube.googleapis.com/youtube/v3/liveBroadcasts?part=snippet,status,contentDetails`
* **Тело запроса (JSON)**:
  ```json
  {
    "snippet": {
      "title": "Запланированный стрим",
      "scheduledStartTime": "2026-07-20T20:00:00Z"
    },
    "status": {
      "privacyStatus": "private"
    },
    "contentDetails": {
      "latencyPreference": "ultraLow",
      "enableAutoStart": true,
      "enableAutoStop": true
    }
  }
  ```

## 5. Связывание трансляции с потоком вещания (liveStream)
* **Метод**: `POST`
* **Запрос**: `https://youtube.googleapis.com/youtube/v3/liveBroadcasts/bind?id={broadcast_id}&streamId={stream_id}&part=id,contentDetails`

## 6. Завершение трансляции
* **Метод**: `POST`
* **Запрос**: `https://youtube.googleapis.com/youtube/v3/liveBroadcasts/transition?id={broadcast_id}&broadcastStatus=complete&part=id,status`

## 7. Загрузка обложки трансляции
* **Метод**: `POST`
* **Запрос**: `https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={broadcast_id}`
* **Заголовки**:
  * `Content-Type: image/jpeg` (или другой mime-тип файла)
  * `Content-Length: <размер_файла>`
