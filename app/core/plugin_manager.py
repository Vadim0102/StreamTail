import importlib
import inspect
import pkgutil
import app.platforms
from app.plugins.base import BasePlugin
from app.utils.logger import logger


class PluginManager:
    def __init__(self, config: dict, plugins_path: str = None):
        self.config = config
        self.plugins = {}

    def load_plugins(self):
        platforms_config = self.config.get("platforms", {})

        for item in pkgutil.iter_modules(app.platforms.__path__):
            if item.ispkg and not item.name.startswith("__"):
                platform_name = item.name
                try:
                    module = importlib.import_module(f"app.platforms.{platform_name}.plugin")
                    for _, cls in inspect.getmembers(module, inspect.isclass):
                        if issubclass(cls, BasePlugin) and cls != BasePlugin:
                            platform_cfg = platforms_config.get(platform_name.lower(), {})
                            instance = cls(config=platform_cfg)
                            self.plugins[instance.name] = instance
                            logger.debug(f"Загружен плагин: {instance.name}")
                except Exception as e:
                    logger.error(f"Ошибка загрузки плагина {platform_name}: {e}")

    def get(self, name: str) -> BasePlugin:
        return self.plugins.get(name)

    def all(self) -> dict:
        return self.plugins
