import importlib
import inspect
import os

from app.plugins.base import BasePlugin


class PluginManager:
    def __init__(self, plugins_path="app/platforms"):
        self.plugins_path = plugins_path
        self.plugins = {}

    def load_plugins(self):
        for platform in os.listdir(self.plugins_path):
            path = os.path.join(self.plugins_path, platform)
            if not os.path.isdir(path):
                continue

            try:
                module = importlib.import_module(
                    f"app.platforms.{platform}.plugin"
                )

                for _, cls in inspect.getmembers(module, inspect.isclass):
                    if issubclass(cls, BasePlugin) and cls != BasePlugin:
                        instance = cls()
                        self.plugins[instance.name] = instance

            except Exception as e:
                print(f"Plugin load error: {platform}: {e}")

    def get(self, name):
        return self.plugins.get(name)

    def all(self):
        return self.plugins
