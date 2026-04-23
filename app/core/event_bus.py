import asyncio
import inspect
from typing import Callable, Dict, List, Set
from app.utils.logger import logger


class EventBus:
    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}
        self._background_tasks: Set[asyncio.Task] = set() # Хранилище задач

    def subscribe(self, event_pattern: str, callback: Callable):
        self.listeners.setdefault(event_pattern,[]).append(callback)

    def unsubscribe(self, event_pattern: str, callback: Callable):
        if event_pattern in self.listeners:
            self.listeners[event_pattern] = [
                cb for cb in self.listeners[event_pattern] if cb != callback
            ]

    def emit(self, event_name: str, data: dict = None):
        for pattern, callbacks in list(self.listeners.items()):
            if pattern == event_name or (pattern.endswith("*") and event_name.startswith(pattern[:-1])):
                for callback in callbacks:
                    try:
                        if inspect.iscoroutinefunction(callback):
                            try:
                                loop = asyncio.get_running_loop()
                                task = loop.create_task(callback(data))
                                # Защита от Garbage Collector
                                self._background_tasks.add(task)
                                task.add_done_callback(self._background_tasks.discard)
                            except RuntimeError:
                                logger.warning(f"EventBus: нет loop для async-события {event_name}")
                        else:
                            callback(data)
                    except Exception as e:
                        logger.error(f"Ошибка в '{event_name}' ({callback.__qualname__}): {e}")
