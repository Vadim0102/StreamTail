import asyncio
from urllib.parse import urlparse, parse_qs
from app.utils.logger import logger

_SUCCESS_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{font-family:sans-serif;background:#0e0e1a;color:#cdd6f4;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{text-align:center;padding:40px;background:#1e1e2e;border-radius:12px}
h1{color:#a6e3a1;font-size:2rem}p{color:#89b4fa}</style></head>
<body><div class="box">
<h1>✅ Авторизация успешна!</h1>
<p>Вернитесь в StreamTail — окно браузера можно закрыть.</p>
</div></body></html>
""".encode("utf-8")

_ERROR_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{font-family:sans-serif;background:#0e0e1a;color:#cdd6f4;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{text-align:center;padding:40px;background:#1e1e2e;border-radius:12px}
h1{color:#f38ba8;font-size:2rem}p{color:#fab387}</style></head>
<body><div class="box">
<h1>❌ Ошибка авторизации</h1>
<p>Попробуйте ещё раз в StreamTail.</p>
</div></body></html>
""".encode("utf-8")


async def wait_for_oauth_code(port: int = 19234, timeout: int = 120) -> dict | None:
    result = {}
    event = asyncio.Event()

    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await reader.read(4096)
            if not data:
                return

            request_line = data.decode("utf-8", errors="ignore").split("\r\n")[0]
            parts = request_line.split(" ")
            if len(parts) < 2:
                return

            path = parts[1]
            parsed = urlparse(path)

            # Перехватчик implicit flow (VK Live)
            if not parsed.query and parsed.path == "/callback":
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    "Connection: close\r\n\r\n"
                    "<!DOCTYPE html><html><body><script>\n"
                    "if (window.location.hash) {\n"
                    "    window.location.replace('/callback?' + window.location.hash.substring(1));\n"
                    "} else {\n"
                    "    document.body.innerHTML = 'No token data received.';\n"
                    "}\n"
                    "</script></body></html>"
                )
                writer.write(response.encode("utf-8"))
                await writer.drain()
                return

            if parsed.path == "/callback":
                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                error = params.get("error", [None])[0]
                access_token = params.get("access_token", [None])[0]
                expires_in = params.get("expires_in", ["0"])[0]
                state = params.get("state", [None])[0]

                result.update({
                    "code": code,
                    "error": error,
                    "access_token": access_token,
                    "expires_in": int(expires_in) if expires_in.isdigit() else 0,
                    "state": state
                })

                if code or access_token:
                    html = _SUCCESS_HTML
                    status_line = "200 OK"
                else:
                    html = _ERROR_HTML
                    status_line = "400 Bad Request"

                response = (
                    f"HTTP/1.1 {status_line}\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(html)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("utf-8") + html

                writer.write(response)
                await writer.drain()
                event.set()

        except Exception as e:
            logger.debug(f"Ошибка обработки OAuth запроса: {e!r}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handle_connection, "127.0.0.1", port)
    logger.debug(f"Временный OAuth сервер запущен на порту {port}")

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("OAuth callback: Превышено время ожидания авторизации.")
        return None
    finally:
        server.close()
        await server.wait_closed()
        logger.debug("Временный OAuth сервер успешно остановлен.")

    if result.get("error"):
        logger.warning(f"OAuth callback: ошибка платформы: {result['error']}")
        return None

    return result
