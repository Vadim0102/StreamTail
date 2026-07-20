# Twitch Helix & Chat API Map

Взаимодействие с платформой Twitch разделено на две части: работа со статистикой и метаданными через HTTP API Helix и двунаправленный асинхронный обмен сообщениями чата по протоколу IRC поверх защищенного сокета SSL.

## 1. Чтение статуса трансляции (Helix API)
* **Запрос**: `GET https://api.twitch.tv/helix/streams?user_id={broadcaster_id}`
* **Заголовки**:
  * `Client-Id: <client_id>`
  * `Authorization: Bearer <access_token>`
* **Ответ (Стрим активен)**:
  ```json
  {
    "data": [
      {
        "id": "1234567890",
        "user_id": "987654321",
        "user_login": "streamtail",
        "user_name": "StreamTail",
        "game_id": "509658",
        "game_name": "Just Chatting",
        "type": "live",
        "title": "Стрим по программированию",
        "viewer_count": 1420,
        "started_at": "2026-07-20T16:00:00Z"
      }
    ]
  }
  ```

## 2. Чтение метаданных канала в оффлайне (Helix API)
Если стрим оффлайн, плагин запрашивает последние метаданные канала через эндпоинт каналов.
* **Запрос**: `GET https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}`

## 3. Обновление заголовка и категории (Helix API)
* **Метод**: `PATCH`
* **Запрос**: `https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}`
* **Тело запроса (JSON)**:
  ```json
  {
    "title": "Новый заголовок трансляции",
    "game_id": "509658"
  }
  ```

## 4. Чат-подключение (IRC TLS)
* **Адрес**: `irc.chat.twitch.tv`
* **Порт**: `6697` (с принудительным включением SSL)
* **Аутентификация**:
  ```text
  PASS oauth:<access_token>
  NICK <broadcaster_login>
  ```

## 5. Команды модерации чата (Helix API)
* **Удаление сообщения**: `DELETE https://api.twitch.tv/helix/moderation/chat` (параметры: `broadcaster_id`, `moderator_id`, `message_id`)
* **Закрепление сообщения**: `PUT https://api.twitch.tv/helix/chat/pins` (параметры: `broadcaster_id`, `moderator_id`, `message_id`)
* **Блокировка / таймаут**: `POST https://api.twitch.tv/helix/moderation/bans` (параметры: `broadcaster_id`, `moderator_id`, тело: `user_id`, `duration`, `reason`)
