from app.plugins.base import BasePlugin

class YouTubePlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.name = "YouTube"

    def execute(self, action, *args, **kwargs):
        if action == "set_title":
            return f"Успешно: Трансляция на YouTube теперь называется '{kwargs.get('title')}'"
        elif action == "set_game":
            return f"Успешно: Игра на YouTube изменена на '{kwargs.get('game')}'"
        elif action == "is_live":
            return False # Заглушка: оффлайн
        return "Неизвестное действие"
