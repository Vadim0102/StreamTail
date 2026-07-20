import asyncio
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.utils.logger import logger

app = FastAPI(title="StreamTail API")
core_app_ref = None
server_instance = None


def get_core_app():
    global core_app_ref
    return core_app_ref


# Монтирование локальной директории статики для инкапсуляции веб-модуля
try:
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
except Exception as e:
    logger.error(f"Web Server: ошибка монтирования статики: {e!r}")


from app.ui.web.routes import router as routes_router
from app.ui.web.websocket import router as ws_router
from app.ui.web.overlay import router as overlay_router

app.include_router(routes_router)
app.include_router(ws_router)
app.include_router(overlay_router)


def start_web_server(app_core):
    global core_app_ref, server_instance
    core_app_ref = app_core
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, loop="asyncio", log_level="warning")
    server_instance = uvicorn.Server(config)
    asyncio.create_task(server_instance.serve())
    logger.info("🌐 FastAPI Web-сервер запущен на http://127.0.0.1:8000")


async def stop_web_server():
    global server_instance
    if server_instance:
        logger.info("🌐 Останавливаем FastAPI Web-сервер...")
        server_instance.should_exit = True
        await server_instance.shutdown()
        server_instance = None
