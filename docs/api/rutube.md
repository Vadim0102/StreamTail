# RUTUBE Studio API Map

Интеграция со Студией RUTUBE (`studio.rutube.ru`) использует куки авторизованного пользователя и извлечение необходимых CSRF-токенов (`x-csrftoken`) для прохождения авторизационной сигнатуры и отправки сообщений.

## 1. Автоматический парсинг кук и CSRF
Плагин принимает куки пользователя в любом формате (JSON, Netscape, HTTP Raw) из поля «Токен» и извлекает:
* Значение куки `sessionid` и `x-csrftoken` (или `csrftoken`).
* Значение заголовка `X-CSRFToken` для прохождения авторизационной сигнатуры.

## 2. Чтение статуса канала (Публичный API)
Для быстрого и бесперебойного получения онлайна без авторизации плагин опрашивает публичный API видеохостинга.
* **Запрос**: `GET https://rutube.ru/api/video/person/{channel_id}/`
* **Ответ**: Данные о последнем видео канала или статус активной трансляции.

## 3. Чтение и обновление данных трансляции (Studio API)
Используются приватные эндпоинты Студии RUTUBE:
* **Запрос**: `GET https://studio.rutube.ru/api/v2/stream/{broadcast_id}/`
* **Обновление заголовка и игры (POST)**:
  * **Запрос**: `POST https://studio.rutube.ru/api/v2/video/stream/{broadcast_id}/`

## 4. Чат трансляции (Poll & Send API)
Взаимодействие с чатом происходит через открытый и защищенный REST API:
* **Получение истории / Опрос новых сообщений**:
  * **Запрос**: `GET https://rutube.ru/api/chat/{broadcast_id}?time={timestamp}&direction=present&format=json&only_active=true`
  * **Ответ**: Возвращает `timestamp` для следующей итерации опроса и массив `results` с сообщениями.

* **Отправка сообщения**:
  * **Запрос**: `POST https://rutube.ru/api/chat/{broadcast_id}/`
  * **Заголовки**: `X-CSRFToken`, `Cookie`, `Origin: https://rutube.ru`, `Content-Type: application/json`
  * **Тело запроса (JSON)**:
    ```json
    {
      "text": "Текст сообщения",
      "parent_id": "1784802120766181260"
    }
    ```
