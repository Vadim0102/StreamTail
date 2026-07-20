from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class StreamUpdate(BaseModel):
    platform: str | None = None
    title: str | None = None
    game: str | None = None


@router.get("/api/status")
async def get_status():
    from app.ui.web.server import get_core_app
    core_app = get_core_app()
    status_data = {}
    if core_app:
        for name, plugin in core_app.plugin_manager.all().items():
            if plugin.enabled:
                status_data[name] = await plugin.get_status()
    return status_data


@router.post("/api/update")
async def update_stream(req: StreamUpdate):
    from app.ui.web.server import get_core_app
    core_app = get_core_app()
    results = {}
    if core_app:
        platforms = [req.platform] if req.platform else [n for n, p in core_app.plugin_manager.all().items() if p.enabled]
        for p in platforms:
            if req.title:
                results[f"{p}_title"] = await core_app.stream_service.update_title(p, req.title)
            if req.game:
                results[f"{p}_game"] = await core_app.stream_service.update_game(p, req.game)
    return results
