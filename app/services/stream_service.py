class StreamService:
    def __init__(self, plugin_manager):
        self.plugin_manager = plugin_manager

    def update_title(self, platform, title):
        plugin = self.plugin_manager.get(platform)
        return plugin.execute("set_title", title=title)

    def update_game(self, platform, game):
        plugin = self.plugin_manager.get(platform)
        return plugin.execute("set_game", game=game)

    def check_live(self, platform):
        plugin = self.plugin_manager.get(platform)
        return plugin.execute("is_live")
