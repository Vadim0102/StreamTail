from app.plugins.base import BasePlugin


class TwitchPlugin(BasePlugin):
    name = "twitch"
    description = "Twitch platform integration"

    def execute(self, action, **kwargs):
        if action == "set_title":
            return self.set_title(kwargs["title"])

        if action == "set_game":
            return self.set_game(kwargs["game"])

        if action == "is_live":
            return self.is_live()

    def set_title(self, title):
        print(f"Twitch title updated: {title}")

    def set_game(self, game):
        print(f"Twitch game updated: {game}")

    def is_live(self):
        return True
