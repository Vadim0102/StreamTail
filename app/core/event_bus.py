class EventBus:
    def __init__(self):
        self.listeners = {}

    def subscribe(self, event_name, callback):
        self.listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name, data=None):
        for callback in self.listeners.get(event_name, []):
            callback(data)
