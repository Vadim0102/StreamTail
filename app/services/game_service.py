class GameService:
    def __init__(self, config):
        self.favorites = config.get("favorites", {}).get("games", [])

    def get_favorites(self):
        return self.favorites

    def add_favorite(self, game_name):
        if game_name and game_name not in self.favorites:
            self.favorites.append(game_name)
            