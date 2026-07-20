# VK Video Live API Map

Пакет интеграции совместим с трансляциями VK Видео Live и платформой VK Play Live.

## 1. Чтение статуса (Публичный продакшн эндпоинт)
* **Запрос**: `GET https://api.live.vkvideo.ru/v1/blog/{owner_id}/public_video_stream`
* **Ответ**:
  ```json
  {
    "isOnline": true,
    "title": "Название трансляции",
    "category": {
      "id": "31b402fb-...",
      "title": "Dota 2"
    },
    "count": {
      "viewers": 150
    }
  }
  ```

## 2. Поиск категорий
* **Запрос**: `GET https://api.live.vkvideo.ru/v1/public_video_stream/category/?search={game_name}`
* **Ответ**:
  ```json
  {
    "data": [
      {
        "id": "aa7162db-...",
        "title": "Dota 2"
      }
    ]
  }
  ```

## 3. Обновление стрима (Защищенный Студийный эндпоинт)
* **Метод**: `PUT`
* **Запрос**: `https://api.live.vkvideo.ru/v1/channel/{owner_id}/manage/stream`
* **Заголовки**:
  * `Authorization: Bearer <accessToken_из_localStorage>`
  * `X-From-Id: vkplay.live` (Официальный Client ID сайта)
  * `Content-Type: application/x-www-form-urlencoded`
* **Тело запроса (Form-Data)**:
  * `category_id`: `"aa7162db-..."`
  * `title_data`: Сериализованный в JSON блок rich-text текста VK Video:
    ```json
    [{"type":"text","content":"[\"Stream title\",\"unstyled\",[]]","modificator":""}]
    ```
