from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import uvicorn
from app.utils.logger import logger

app = FastAPI(title="StreamTail API")
core_app_ref = None

class StreamUpdate(BaseModel):
    platform: str | None = None
    title: str | None = None
    game: str | None = None

@app.get("/api/status")
async def get_status():
    status_data = {}
    for name, plugin in core_app_ref.plugin_manager.all().items():
        if plugin.enabled:
            status_data[name] = await plugin.get_status()
    return status_data

@app.post("/api/update")
async def update_stream(req: StreamUpdate):
    platforms =[req.platform] if req.platform else[n for n, p in core_app_ref.plugin_manager.all().items() if p.enabled]
    results = {}
    for p in platforms:
        if req.title:
            results[f"{p}_title"] = await core_app_ref.stream_service.update_title(p, req.title)
        if req.game:
            results[f"{p}_game"] = await core_app_ref.stream_service.update_game(p, req.game)
    return results

def start_web_server(app_core):
    global core_app_ref
    core_app_ref = app_core
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, loop="asyncio", log_level="warning")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())
    logger.info("🌐 FastAPI Web-сервер запущен на http://127.0.0.1:8000")
