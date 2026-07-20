# GoodGame API Map

Интеграция с платформой GoodGame осуществляется через официальное публичное API v4, а также через вычисленный с помощью HAR-анализа внутренний студийный эндпоинт вещания.

## 1. Получение Stream ID из токена (Для авторизованных)
* **Запрос**: `GET https://goodgame.ru/api/4/user`
* **Заголовки**: `Authorization: Bearer <token>`
* **Ответ**: 
  ```json
  {
    "id": 123456,
    "stream": {
      "id": 221841,
      "title": "Название трансляции"
    }
  }
  ```

## 2. Чтение статуса канала (По ID стрима)
* **Запрос**: `GET https://goodgame.ru/api/4/streams/{stream_id}`
* **Ответ**:
  ```json
  {
    "online": true,
    "viewers": 150,
    "title": "Стрим по Minecraft",
    "gameObj": {
      "title": "Minecraft"
    }
  }
  ```

## 3. Поиск игр
* **Запрос**: `GET https://goodgame.ru/api/4/games?query={game_name}`
* **Ответ**:
  ```json
  {
    "games": {
      "list": {
        "list": [
          {
            "id": 27812,
            "title": "Minecraft"
          }
        ]
      }
    }
  }
  ```

## 4. Обновление метаданных трансляции (Студийный эндпоинт)
*Выявлено в ходе анализа трафика официального веб-интерфейса во вкладке «Студия».*
* **Запрос**: `POST https://goodgame.ru/api/4/streams/for-helpers/game-title?id={stream_id}`
* **Заголовки**: 
  * `Authorization: Bearer <token>`
  * `Content-Type: application/json`
* **Тело запроса (JSON)**:
  ```json
  {
    "id": 221841,
    "title": "Новое название трансляции",
    "gameId": 27812
  }
  ```
> **Важно**: Платформа требует одновременной отправки названия и игры, поэтому плагин использует стратегию Read-Modify-Write (RMW), предварительно считывая текущие параметры перед записью.
