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

    async def publish_stream(self, platform: str) -> str:
        """Переводит трансляцию из подготовки (wait) в публичный доступ (actual)."""
        plugin = self.plugin_manager.get(platform)
        if plugin:
            if hasattr(plugin, "publish_stream"):
                return await plugin.publish_stream()
            return f"Платформа {platform} не поддерживает публикацию."
        return f"Платформа {platform} не найдена."

    async def stop_stream(self, platform: str) -> str:
        """Переводит трансляцию в статус 'done' (Завершено) [2.1]."""
        plugin = self.plugin_manager.get(platform)
        if plugin:
            if hasattr(plugin, "stop_stream"):
                return await plugin.stop_stream()
            return f"Платформа {platform} не поддерживает завершение стримов."
        return f"Платформа {platform} не найдена."

    async def upload_thumbnail(self, platform: str, image_path: str) -> str:
        """Загружает обложку-превью на целевую платформу."""
        plugin = self.plugin_manager.get(platform)
        if plugin:
            if hasattr(plugin, "upload_thumbnail"):
                return await plugin.upload_thumbnail(image_path)
            return f"Платформа {platform} не поддерживает загрузку обложек."
        return f"Платформа {platform} не найдена."
