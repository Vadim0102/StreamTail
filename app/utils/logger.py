import sys
from loguru import logger

# Настройка единого логгера
logger.remove()
logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>")
logger.add("logs/streamtail.log", rotation="5 MB", retention="10 days", level="DEBUG")

__all__ = ["logger"]
