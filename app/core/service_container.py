# app/core/service_container.py
class ServiceContainer:
    def __init__(self):
        self._services = {}

    def register(self, name, service):
        self._services[name] = service

    def get(self, name):
        return self._services.get(name)

# Глобальный экземпляр
container = ServiceContainer()
