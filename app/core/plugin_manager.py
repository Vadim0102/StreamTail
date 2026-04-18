import importlib
import inspect
import os
from app.plugins.base import BasePlugin


class PluginManager:
    def __init__(self, config, plugins_path="app/platforms"):
        self.config = config
        self.plugins_path = plugins_path
        self.plugins = {}

    def load_plugins(self):
        platforms_config = self.config.get("platforms", {})

        for platform in os.listdir(self.plugins_path):
            path = os.path.join(self.plugins_path, platform)
            if not os.path.isdir(path):
                continue

            try:
                module = importlib.import_module(f"app.platforms.{platform}.plugin")
                for _, cls in inspect.getmembers(module, inspect.isclass):
                    if issubclass(cls, BasePlugin) and cls != BasePlugin:
                        # Передаем специфичный конфиг платформы в плагин
                        platform_cfg = platforms_config.get(platform.lower(), {})
                        instance = cls(config=platform_cfg)
                        self.plugins[instance.name] = instance
            except Exception as e:
                print(f"Plugin load error: {platform}: {e}")

    def get(self, name):
        return self.plugins.get(name)

    def all(self):
        return self.plugins
