import sys
import asyncio
from app.core.app import StreamTailApp
from app.utils.logger import logger
from async_tkinter_loop import async_mainloop


def main():
    logger.info("Запуск StreamTail...")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # ИЗМЕНЕНО: Правильная инициализация event loop без Warning'ов
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Инициализируем ядро и GUI
    app = StreamTailApp()

    # Планируем фоновую задачу загрузки плагинов
    loop.create_task(app.start_background())

    try:
        # Запуск Tkinter + asyncio
        async_mainloop(app.gui.root)
    except KeyboardInterrupt:
        logger.warning("Приложение завершено пользователем (Ctrl+C).")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        # Корректно завершаем работу
        app.shutdown()


if __name__ == "__main__":
    main()
