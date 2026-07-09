import sys
import asyncio
from app.core.app import StreamTailApp
from app.utils.logger import logger
from async_tkinter_loop import async_mainloop


def main():
    logger.info("Запуск StreamTail...")

    # Устанавливаем WindowsSelectorEventLoopPolicy только для старых версий Python (< 3.12).
    # Начиная с Python 3.12+, ProactorEventLoop используется по умолчанию и работает стабильно.
    if sys.platform == "win32" and sys.version_info < (3, 12):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = StreamTailApp()

    # Планируем фоновую задачу загрузки плагинов
    loop.create_task(app.start_background())

    try:
        # Передаем event_loop=loop, чтобы фоновые задачи выполнялись на одном loop с Tkinter
        async_mainloop(app.gui.root, event_loop=loop)
    except KeyboardInterrupt:
        logger.warning("Приложение завершено пользователем (Ctrl+C).")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
