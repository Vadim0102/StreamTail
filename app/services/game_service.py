from app.utils.config import save_config
from app.core.service_container import container


class GameService:
    def __init__(self, config: dict):
        self.config = config
        self.favorites = self.config.get("favorites", {}).get("games", [])

    def get_favorites(self) -> list:
        return self.favorites

    def add_favorite(self, game_name: str):
        if game_name and game_name not in self.favorites:
            self.favorites.append(game_name)
            # Обновляем словарь и сохраняем
            if "favorites" not in self.config:
                self.config["favorites"] = {}
            self.config["favorites"]["games"] = self.favorites

            # Сохраняем в файл
            save_config(self.config)
            return True
        return False
