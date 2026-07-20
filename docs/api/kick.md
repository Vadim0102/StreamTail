# Kick.com API Map

Взаимодействие с платформой Kick поддерживает как официальный протокол авторизации (User Access Token), так и резервный неофициальный метод через cookies браузера для обхода защиты Cloudflare.

## 1. Чтение статуса (Официальный API)
*Работает стабильно, Cloudflare не блокирует авторизованные запросы.*
* **Запрос**: `GET https://api.kick.com/public/v1/channels?slug={slug}`
* **Заголовки**: `Authorization: Bearer <access_token>`
* **Ответ**:
  ```json
  {
    "data": [
      {
        "stream_title": "Метаданные стрима",
        "category": {
          "name": "Just Chatting"
        },
        "stream": {
          "is_live": true,
          "viewer_count": 15,
          "title": "Текущий стрим"
        }
      }
    ]
  }
  ```

## 2. Чтение статуса (Неофициальный веб-интерфейс)
*Используется в качестве резервного, подвержен TLS-инспекциям Cloudflare.*
* **Запрос**: `GET https://kick.com/api/v1/channels/{slug}`
* **Заголовки**: 
  * `Cookie: <сессия>`
  * `Referer: https://kick.com/`
* **Ответ**:
  ```json
  {
    "livestream": {
      "viewer_count": 15,
      "session_title": "Название",
      "categories": [
        {
          "name": "Talk Shows"
        }
      ]
    }
  }
  ```

## 3. Поиск категорий (Официальный API)
* **Запрос**: `GET https://api.kick.com/public/v2/categories?name={game_name}`
* **Ответ**:
  ```json
  {
    "categories": [
      {
        "id": 101,
        "name": "Just Chatting"
      }
    ]
  }
  ```

## 4. Обновление стрима (Официальный API)
* **Метод**: `PATCH`
* **Запрос**: `https://api.kick.com/public/v1/channels`
* **Заголовки**: `Authorization: Bearer <token_с_правами_channel:write>`
* **Тело запроса (JSON)**:
  ```json
  {
    "stream_title": "Новое название",
    "category_id": 101
  }
  ```

## 5. Обновление стрима (Неофициальный метод через cookies)
* **Метод**: `PUT`
* **Запрос**: `https://kick.com/api/v2/channels/{slug}`
* **Заголовки**:
  * `Cookie: <куки_авторизации>`
  * `X-XSRF-TOKEN: <токен_извлеченный_из_кук>`
* **Тело запроса (JSON)**:
  ```json
  {
    "stream_title": "Новое название"
  }
  ```
  или
  ```json
  {
    "category_id": 101
  }
  ```
