# RUTUBE Studio API Map

Интеграция со Студией RUTUBE (`studio.rutube.ru`) использует куки авторизованного пользователя и извлечение необходимых CSRF-токенов (`x-csrftoken`) для обхода авторизационных защит и фильтров Cloudflare.

## 1. Автоматический парсинг кук и CSRF
Плагин принимает куки пользователя в любом формате (JSON, Netscape, HTTP Raw) из поля «Токен» и извлекает:
* Значение куки `sessionid` и `x-csrftoken` (или `csrftoken`).
* Значение заголовка `X-CSRFToken` для прохождения авторизационной сигнатуры.

## 2. Чтение статуса канала (Публичный API)
Для быстрого и бесперебойного получения онлайна без авторизации плагин опрашивает публичный API видеохостинга.
* **Запрос**: `GET https://rutube.ru/api/video/person/{channel_id}/` (или `GET https://rutube.ru/api/play/v2/thumbnail/{video_id}/`)
* **Ответ**: Данные о последнем видео канала или статус активной трансляции.

## 3. Чтение и обновление данных трансляции (Studio API)
Используются приватные эндпоинты Студии RUTUBE:
* **Запрос**: `GET https://studio.rutube.ru/api/v2/stream/{broadcast_id}/`
* **Заголовки**:
  * `Cookie: <parsed_cookies>`
  * `X-CSRFToken: <extracted_csrf_token>`
  * `Referer: https://studio.rutube.ru/`
* **Ответ (Данные стрима)**:
  ```json
  {
    "id": "f290551824869de96ec29760e731385d",
    "title": "Текущий заголовок",
    "description": "Описание стрима",
    "category": {
      "id": 15,
      "name": "Игры"
    },
    "is_live": true
  }
  ```

* **Обновление заголовка и игры (PUT/PATCH)**:
  * **Запрос**: `PUT https://studio.rutube.ru/api/v2/stream/{broadcast_id}/`
  * **Тело запроса (JSON)**:
    ```json
    {
      "title": "Новое название трансляции",
      "category": 15
    }
    ```
