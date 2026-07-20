import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.utils.logger import logger

router = APIRouter()


class ChatWebSocketManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


ws_manager = ChatWebSocketManager()


@router.websocket("/api/chat/ws")
async def chat_websocket_endpoint(websocket: WebSocket):
    from app.ui.web.server import get_core_app
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                action = payload.get("action")
                platform = payload.get("platform")
                core_app = get_core_app()

                if core_app:
                    if action == "delete" and platform:
                        msg_id = payload.get("msg_id")
                        await core_app.chat_service.delete_message(platform, msg_id)
                    elif action == "timeout" and platform:
                        user_id = payload.get("user_id")
                        duration = payload.get("duration", 600)
                        await core_app.chat_service.ban_user(platform, user_id, duration=duration)
                    elif action == "ban" and platform:
                        user_id = payload.get("user_id")
                        await core_app.chat_service.ban_user(platform, user_id)
            except Exception as e:
                logger.debug(f"Web Chat WS: ошибка разбора команды: {e!r}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


async def broadcast_chat_message_to_web(data: dict):
    """Транслирует сообщение во все активные веб-оверлеи."""
    await ws_manager.broadcast(json.dumps(data, ensure_ascii=False))
