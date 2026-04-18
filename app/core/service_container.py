from typing import Any, Dict

class ServiceContainer:
    def __init__(self):
        self._services: Dict[str, Any] = {}

    def register(self, name: str, service: Any):
        self._services[name] = service

    def get(self, name: str) -> Any:
        return self._services.get(name)

container = ServiceContainer()
