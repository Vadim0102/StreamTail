import asyncio
import inspect
from typing import Callable, Dict, List
from app.utils.logger import logger

class EventBus:
    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}

    def subscribe(self, event_pattern: str, callback: Callable):
        self.listeners.setdefault(event_pattern,[]).append(callback)

    def emit(self, event_name: str, data: dict = None):
        """Асинхронный вызов с поддержкой wildcard (например stream.*)"""
        for pattern, callbacks in self.listeners.items():
            # Проверка на точное совпадение или wildcard
            if pattern == event_name or (pattern.endswith('*') and event_name.startswith(pattern[:-1])):
                for callback in callbacks:
                    try:
                        if inspect.iscoroutinefunction(callback):
                            asyncio.create_task(callback(data))
                        else:
                            # Оборачиваем синхронные функции в thread, чтобы не блочить Event Loop
                            asyncio.get_running_loop().run_in_executor(None, callback, data)
                    except Exception as e:
                        logger.error(f"Ошибка в обработчике события {event_name}: {e}")
