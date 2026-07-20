from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.utils.logger import logger

router = APIRouter()


@router.get("/chat", response_class=HTMLResponse)
async def get_chat_overlay():
    try:
        # Локальное разрешение пути к файлу разметки
        static_dir = Path(__file__).resolve().parent / "static"
        html_path = static_dir / "overlay.html"
        if html_path.exists():
            with open(html_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
    except Exception as e:
        logger.error(f"Web Overlay: ошибка чтения файла overlay.html: {e!r}")

    return HTMLResponse(content="<h3>Ошибка: Файл overlay.html не найден в статике веб-модуля.</h3>")
