# app/ui/web/api.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import asyncio
import json
import uvicorn
from app.utils.logger import logger

app = FastAPI(title="StreamTail API")
core_app_ref = None


class StreamUpdate(BaseModel):
    platform: str | None = None
    title: str | None = None
    game: str | None = None


# ── Секция Веб-Сокетов и Оверлея Чат-Системы ──

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
        # Копируем список для безопасного удаления элементов во время итерации
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


ws_manager = ChatWebSocketManager()


@app.websocket("/api/chat/ws")
async def chat_websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                action = payload.get("action")
                platform = payload.get("platform")

                if action == "delete" and platform:
                    msg_id = payload.get("msg_id")
                    await core_app_ref.chat_service.delete_message(platform, msg_id)
                elif action == "timeout" and platform:
                    user_id = payload.get("user_id")
                    duration = payload.get("duration", 600)
                    await core_app_ref.chat_service.ban_user(platform, user_id, duration=duration)
                elif action == "ban" and platform:
                    user_id = payload.get("user_id")
                    await core_app_ref.chat_service.ban_user(platform, user_id)
            except Exception as e:
                logger.debug(f"Web Chat WS: ошибка разбора команды: {e!r}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


async def broadcast_chat_message_to_web(data: dict):
    await ws_manager.broadcast(json.dumps(data, ensure_ascii=False))


# Красивый HTML-оверлей чата с полной синхронизацией удалений и банов
OVERLAY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>StreamTail Chat Overlay</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: transparent;
            margin: 0;
            padding: 15px;
            overflow: hidden;
            color: #ffffff;
            text-shadow: 1px 1px 2px #000, -1px -1px 2px #000, 1px -1px 2px #000, -1px 1px 2px #000;
        }
        #chat-container {
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            height: 95vh;
            max-width: 450px;
        }
        .message-box {
            background: rgba(30, 30, 46, 0.80);
            border-radius: 8px;
            padding: 8px 12px;
            margin-top: 6px;
            border-left: 4px solid #89b4fa;
            animation: slideIn 0.3s ease-out forwards;
            font-size: 14px;
            line-height: 1.4;
            transition: all 0.4s ease;
        }
        .platform-twitch { border-left-color: #a28cf2; }
        .platform-youtube { border-left-color: #f28c8c; }
        .platform-kick { border-left-color: #8cf290; }
        .platform-livevk { border-left-color: #8caef2; }
        .platform-goodgame { border-left-color: #f2b58c; }
        .platform-rutube { border-left-color: #8ce2f2; }

        .author-name {
            font-weight: bold;
            margin-right: 6px;
        }
        .badge {
            display: inline-block;
            padding: 1px 4px;
            font-size: 9px;
            border-radius: 3px;
            margin-right: 4px;
            text-transform: uppercase;
            font-weight: 800;
            color: #11111b;
        }
        .badge-owner { background-color: #f38ba8; }
        .badge-moderator { background-color: #a6e3a1; }
        .badge-subscriber { background-color: #fab387; }

        .text-content {
            word-wrap: break-word;
        }

        @keyframes slideIn {
            from { transform: translateX(-30px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
    </style>
</head>
<body>
    <div id="chat-container"></div>
    <script>
        const container = document.getElementById("chat-container");
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(protocol + "//" + window.location.host + "/api/chat/ws");

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            // 1. ОБНОВЛЕНИЕ ID ЛОКАЛЬНОГО СООБЩЕНИЯ НА РЕАЛЬНЫЙ TWITCH ID
            if (data.action === "update_id") {
                const el = document.getElementById("msg-" + data.old_id);
                if (el) {
                    el.id = "msg-" + data.new_id;
                }
                return;
            }

            // 2. ПОЛУЧЕНО СОБЫТИЕ УДАЛЕНИЯ СООБЩЕНИЯ
            if (data.action === "delete") {
                const el = document.getElementById("msg-" + data.msg_id);
                if (el) {
                    el.style.opacity = "0.35";
                    const textEl = el.querySelector(".text-content");
                    if (textEl) {
                        textEl.innerHTML = "<i>&lt;сообщение удалено модератором&gt;</i>";
                    }
                }
                return;
            }
            
            // 3. ПОЛУЧЕНО СОБЫТИЕ БАНА / ТАЙМАУТА ПОЛЬЗОВАТЕЛЯ
            if (data.action === "ban_user") {
                const authorClass = "author-" + data.username.toLowerCase();
                const elements = document.getElementsByClassName(authorClass);
                for (let el of elements) {
                    el.style.opacity = "0.35";
                    const textEl = el.querySelector(".text-content");
                    if (textEl) {
                        textEl.innerHTML = "<i>&lt;сообщение удалено модератором&gt;</i>";
                    }
                }
                return;
            }
            
            // 4. ОБЫЧНОЕ СООБЩЕНИЕ
            const msg = data;
            
            // Защита от дубликатов на веб-странице
            if (document.getElementById("msg-" + msg.id)) {
                return;
            }
            
            const box = document.createElement("div");
            box.id = "msg-" + msg.id;
            
            const authorClass = msg.author ? "author-" + msg.author.name.toLowerCase() : "author-anon";
            box.className = "message-box platform-" + msg.platform + " " + authorClass;
            
            let badgesHtml = "";
            if (msg.author && msg.author.badges) {
                msg.author.badges.forEach(b => {
                    badgesHtml += `<span class="badge badge-${b}">${b}</span>`;
                });
            }
            
            const platformLabel = `<span style="font-size:10px; opacity:0.6; text-transform:uppercase; margin-right:5px;">[${msg.platform}]</span>`;
            
            box.innerHTML = `
                <div>
                    ${platformLabel}
                    ${badgesHtml}
                    <span class="author-name" style="color: ${msg.platform === 'twitch' ? '#cba6f7' : '#89b4fa'}">${msg.author ? msg.author.name : 'Аноним'}</span>:
                    <span class="text-content">${escapeHTML(msg.text)}</span>
                </div>
            `;
            
            container.appendChild(box);
            
            if (container.children.length > 25) {
                container.removeChild(container.firstChild);
            }
            
            setTimeout(() => {
                if (box.parentNode) {
                    box.style.transition = "opacity 0.5s ease";
                    box.style.opacity = "0";
                    setTimeout(() => { if (box.parentNode) box.remove(); }, 500);
                }
            }, 30000);
        };

        function escapeHTML(str) {
            return str.replace(/[&<>'"]/g, 
                tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
            );
        }
    </script>
</body>
</html>
"""


@app.get("/chat", response_class=HTMLResponse)
async def get_chat_overlay():
    return HTMLResponse(content=OVERLAY_HTML)


# ── REST API ──

@app.get("/api/status")
async def get_status():
    status_data = {}
    for name, plugin in core_app_ref.plugin_manager.all().items():
        if plugin.enabled:
            status_data[name] = await plugin.get_status()
    return status_data


@app.post("/api/update")
async def update_stream(req: StreamUpdate):
    platforms = [req.platform] if req.platform else [n for n, p in core_app_ref.plugin_manager.all().items() if
                                                     p.enabled]
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
