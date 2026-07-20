import time
import httpx
from app.auth.goodgame_auth import TOKEN_URL
from app.plugins.base import BasePlugin
from app.auth.token_store import get_token, is_token_valid
from app.utils.logger import logger
from app.utils import http_client


class GoodGamePlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)

    @property
    def token_data(self):
        return get_token("goodgame") or {}

    @property
    def token(self):
        return self.token_data.get("access_token")

    @property
    def channel_slug(self) -> str:
        raw = self.config.get("channel", "").strip()
        if not raw:
            return ""
        if "/" in raw:
            return raw.rstrip("/").split("/")[-1]
        return raw

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }

    async def _ensure_token_valid(self) -> bool:
        if is_token_valid("goodgame"):
            return True

        tdata = self.token_data
        r_token = tdata.get("refresh_token")
        c_id = tdata.get("client_id")
        c_sec = tdata.get("client_secret")

        if r_token and c_id and c_sec:
            from app.auth import goodgame_auth
            logger.info("GoodGame: токен истек. Выполняем автоматический refresh...")
            return await goodgame_auth.refresh(c_id, c_sec, r_token)
        return False

    async def _get_stream_id(self, client: httpx.AsyncClient) -> str:
        """Автоматически получает точный ID трансляции из профиля /user."""
        if self.token:
            try:
                resp = await client.get("https://goodgame.ru/api/4/user", headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    stream_id = data.get("stream_id") or data.get("stream", {}).get("id") or data.get("channel", {}).get("id")
                    if stream_id:
                        logger.info(f"GoodGame: Успешно получен ID стрима {stream_id} напрямую из профиля /user")
                        return str(stream_id)
            except Exception as e:
                logger.debug(f"GoodGame: Не удалось получить ID из профиля: {e!r}")

        slug = self.channel_slug
        if slug:
            try:
                url = f"https://goodgame.ru/api/4/users/{slug}/stream"
                resp = await client.get(url)
                if resp.status_code == 200:
                    stream_id = resp.json().get("id")
                    if stream_id:
                        return str(stream_id)
            except Exception as e:
                logger.debug(f"GoodGame: Не удалось получить ID по имени канала {slug}: {e!r}")

        return ""

    async def _update_stream_info(self, client: httpx.AsyncClient, stream_id: str, title: str = None, game_id: int = None) -> str:
        """
        Обновляет название и категорию трансляции на GoodGame, используя
        официальный приватный эндпоинт из HAR-лога во избежание 404 ошибок.
        """
        get_url = "https://goodgame.ru/api/4/streams/for-helpers/game-title"
        get_params = {"id": stream_id}

        current_title = ""
        current_game_id = 0

        try:
            get_resp = await client.get(get_url, headers=self.headers, params=get_params)
            if get_resp.status_code == 200:
                data = get_resp.json()
                current_title = data.get("title") or ""
                current_game_id = data.get("gameId") or 0
        except Exception as e:
            logger.debug(f"GoodGame: Не удалось прочитать текущие данные стрима перед записью: {e!r}")

        final_title = title if title is not None else current_title
        final_game_id = game_id if game_id is not None else current_game_id

        # Формируем Payload в формате JSON в строгом соответствии с HAR-логом
        payload = {
            "id": int(stream_id),
            "title": final_title,
            "gameId": int(final_game_id)
        }

        try:
            resp = await client.post(get_url, headers=self.headers, params=get_params, json=payload)
            if resp.status_code == 200 and resp.json().get("success") is True:
                return "GoodGame: Данные трансляции успешно обновлены"
            return f"GoodGame Ошибка ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            return f"GoodGame Исключение при записи: {e!r}"

    # ── Чтение статуса ────────────────────────────────────────────────────────

    async def get_status(self):
        status = {"is_live": False, "viewers": 0, "title": "", "game": ""}

        try:
            async with http_client.create_client() as client:
                stream_id = await self._get_stream_id(client)

                if stream_id:
                    url = f"https://goodgame.ru/api/4/streams/{stream_id}"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        stream = data if isinstance(data, dict) else (data[0] if isinstance(data, list) else {})
                        status.update({
                            "is_live": stream.get("online", False),
                            "viewers": stream.get("viewers", 0),
                            "title": stream.get("title", ""),
                            "game": stream.get("gameObj", {}).get("title", "") if stream.get("gameObj") else ""
                        })
                        return status

                slug = self.channel_slug
                if slug:
                    url = f"https://goodgame.ru/api/4/users/{slug}/stream"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        status.update({
                            "is_live": data.get("online", False),
                            "viewers": data.get("viewers", 0),
                            "title": data.get("title", ""),
                            "game": data.get("gameObj", {}).get("title", "") if data.get("gameObj") else ""
                        })
        except Exception as e:
            logger.error(f"GoodGame: ошибка получения статуса: {e!r}")
        return status

    # ── Запись ────────────────────────────────────────────────────────────────

    async def set_title(self, title: str) -> str:
        if not self.token:
            return "GoodGame: Нет токена авторизации"
        await self._ensure_token_valid()

        try:
            async with http_client.create_client() as client:
                stream_id = await self._get_stream_id(client)
                if not stream_id:
                    return "GoodGame: Не удалось определить ID трансляции (проверьте авторизацию/slug)"

                return await self._update_stream_info(client, stream_id, title=title)
        except Exception as e:
            return f"GoodGame Ошибка: {e!r}"

    async def set_game(self, game: str) -> str:
        if not self.token:
            return "GoodGame: Нет токена авторизации"
        await self._ensure_token_valid()

        try:
            async with http_client.create_client() as client:
                # 1. Поиск ID игры
                search_url = "https://goodgame.ru/api/4/games"
                search_resp = await client.get(search_url, params={"query": game})
                game_id = None
                if search_resp.status_code == 200:
                    data = search_resp.json()
                    games_list = data.get("games", {}).get("list", {}).get("list", [])
                    if games_list and isinstance(games_list, list):
                        game_id = games_list[0].get("id")

                if not game_id:
                    return f"GoodGame: Игра '{game}' не найдена"

                stream_id = await self._get_stream_id(client)
                if not stream_id:
                    return "GoodGame: Не удалось определить ID трансляции"

                return await self._update_stream_info(client, stream_id, game_id=game_id)
        except Exception as e:
            return f"GoodGame Ошибка: {e!r}"

    async def refresh(self, client_id: str, client_secret: str, refresh_token: str) -> bool:
        """Перенаправление во избежание сбоев устаревшего API."""
        from app.auth import goodgame_auth
        return await goodgame_auth.refresh(client_id, client_secret, refresh_token)
