import sys
import asyncio
from app.core.app import StreamTailApp
from app.utils.logger import logger
from async_tkinter_loop import async_mainloop


def main():
    logger.info("Запуск StreamTail...")

    # Для Windows обязательно ставим правильную политику до создания цикла
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Инициализируем ядро и GUI (пока синхронно)
    app = StreamTailApp()

    # Планируем фоновую задачу загрузки плагинов.
    # Она начнет выполняться сразу, как только async_mainloop запустит цикл.
    loop.create_task(app.start_background())

    try:
        # async_mainloop блокирует поток, запускает asyncio и Tkinter одновременно!
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
