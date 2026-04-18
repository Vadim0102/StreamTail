class StreamService:
    def __init__(self, plugin_manager):
        self.plugin_manager = plugin_manager

    async def update_title(self, platform: str, title: str) -> str:
        plugin = self.plugin_manager.get(platform)
        if plugin:
            return await plugin.set_title(title)
        return f"Платформа {platform} не найдена."

    async def update_game(self, platform: str, game: str) -> str:
        plugin = self.plugin_manager.get(platform)
        if plugin:
            return await plugin.set_game(game)
        return f"Платформа {platform} не найдена."
