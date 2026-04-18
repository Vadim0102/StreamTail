class GameService:
    def __init__(self, config: dict):
        self.favorites = config.get("favorites", {}).get("games",[])

    def get_favorites(self) -> list:
        return self.favorites

    def add_favorite(self, game_name: str):
        if game_name and game_name not in self.favorites:
            self.favorites.append(game_name)
