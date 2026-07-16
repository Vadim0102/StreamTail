import sys
from loguru import logger
from app.utils.paths import get_app_data_dir

# Очищаем дефолтные обработчики Loguru
logger.remove()

# Добавляем вывод в консоль, только если поток stdout существует и доступен для записи
if sys.stdout is not None and hasattr(sys.stdout, "write"):
    try:
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
            backtrace=True,
            diagnose=True
        )
    except Exception:
        pass

# Настройка записи логов в файл внутри директории AppData
try:
    log_file = get_app_data_dir() / "logs" / "streamtail.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_file),
        rotation="5 MB",
        retention="10 days",
        level="DEBUG",
        encoding="utf-8",
        backtrace=True,
        diagnose=True
    )
except Exception as e:
    # Резервный вывод ошибки инициализации в stderr, если он доступен
    if sys.stderr is not None and hasattr(sys.stderr, "write"):
        sys.stderr.write(f"Failed to initialize file logger: {e}\n")

__all__ = ["logger"]
