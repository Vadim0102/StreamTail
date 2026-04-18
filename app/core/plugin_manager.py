import importlib
import inspect
import os
from app.plugins.base import BasePlugin
from app.utils.logger import logger


class PluginManager:
    def __init__(self, config: dict, plugins_path: str = "app/platforms"):
        self.config = config
        self.plugins_path = plugins_path
        self.plugins = {}

    def load_plugins(self):
        platforms_config = self.config.get("platforms", {})

        for platform in os.listdir(self.plugins_path):
            path = os.path.join(self.plugins_path, platform)
            if not os.path.isdir(path) or platform.startswith("__"):
                continue

            try:
                module = importlib.import_module(f"app.platforms.{platform}.plugin")
                for _, cls in inspect.getmembers(module, inspect.isclass):
                    if issubclass(cls, BasePlugin) and cls != BasePlugin:
                        platform_cfg = platforms_config.get(platform.lower(), {})
                        instance = cls(config=platform_cfg)
                        self.plugins[instance.name] = instance
                        logger.debug(f"Загружен плагин: {instance.name}")
            except Exception as e:
                logger.error(f"Ошибка загрузки плагина {platform}: {e}")

    def get(self, name: str) -> BasePlugin:
        return self.plugins.get(name)

    def all(self) -> dict:
        return self.plugins
