from abc import ABC, abstractmethod

class BasePlugin(ABC):
    def __init__(self, config=None):
        self.enabled = False
        self.config = config or {}
        self.name = self.__class__.__name__.lower().replace("plugin", "")

    def enable(self):
        self.enabled = True
        print(f"[{self.name}] Plugin enabled")

    @abstractmethod
    def execute(self, action, *args, **kwargs):
        pass
