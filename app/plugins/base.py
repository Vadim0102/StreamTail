from abc import ABC, abstractmethod


class BasePlugin(ABC):
    name = "base"
    version = "1.0.0"
    description = "Base plugin"

    def __init__(self):
        self.enabled = False

    def enable(self):
        self.enabled = True
        self.on_enable()

    def disable(self):
        self.enabled = False
        self.on_disable()

    def on_enable(self):
        pass

    def on_disable(self):
        pass

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass