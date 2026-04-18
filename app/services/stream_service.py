class StreamService:
    def __init__(self, plugin_manager):
        self.plugin_manager = plugin_manager

    def update_title(self, platform, title):
        plugin = self.plugin_manager.get(platform)
        if plugin:
            return plugin.execute("set_title", title=title)
        return f"Платформа {platform} не найдена."

    def update_game(self, platform, game):
        plugin = self.plugin_manager.get(platform)
        if plugin:
            return plugin.execute("set_game", game=game)
        return f"Платформа {platform} не найдена."

    def check_live(self, platform):
        plugin = self.plugin_manager.get(platform)
        if plugin:
            status = plugin.execute("get_status")
            return status.get("is_live", False) if isinstance(status, dict) else False
        return False
