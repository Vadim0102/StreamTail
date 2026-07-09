import httpx
from app.utils import db

def get_proxy_settings() -> str | None:
    """Извлекает глобальный адрес прокси-сервера из зашифрованной базы данных настроек."""
    config = db.get_setting("app_config") or {}
    proxy_url = config.get("app", {}).get("proxy_url", "").strip()
    return proxy_url if proxy_url else None

def create_client(timeout: float = 10.0) -> httpx.AsyncClient:
    """Создает асинхронный HTTPX-клиент, автоматически настроенный на работу через прокси."""
    proxy = get_proxy_settings()
    return httpx.AsyncClient(proxy=proxy, timeout=timeout)
