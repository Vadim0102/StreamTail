import httpx
from app.utils.config import save_config


class GameService:
    def __init__(self, config: dict, plugin_manager):
        self.config = config
        self.plugin_manager = plugin_manager
        self.favorites = self.config.get("favorites", {}).get("games", [])

    def get_favorites(self) -> list:
        return self.favorites

    def add_favorite(self, game_name: str):
        if game_name and game_name not in self.favorites:
            self.favorites.append(game_name)
            if "favorites" not in self.config:
                self.config["favorites"] = {}
            self.config["favorites"]["games"] = self.favorites
            save_config(self.config)
            return True
        return False

    async def search_games(self, query: str) -> list:
        """Поиск игр через API Twitch (самая большая база игр)."""
        twitch_plugin = self.plugin_manager.get("twitch")
        if twitch_plugin and twitch_plugin.enabled and twitch_plugin.token:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    url = f"https://api.twitch.tv/helix/search/categories?query={query}"
                    resp = await client.get(url, headers=twitch_plugin.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        return [item["name"] for item in data.get("data", [])]
            except Exception as e:
                from app.utils.logger import logger
                logger.error(f"Ошибка поиска игр: {e}")

        # Резервный поиск по локальному избранному
        return [g for g in self.favorites if query.lower() in g.lower()]
