import sys
from loguru import logger
from app.utils.paths import get_app_data_dir

# Настройка единого логгера
logger.remove()
logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>")

# Логи сохраняются в AppData
log_file = get_app_data_dir() / "logs" / "streamtail.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logger.add(str(log_file), rotation="5 MB", retention="10 days", level="DEBUG")

__all__ = ["logger"]
