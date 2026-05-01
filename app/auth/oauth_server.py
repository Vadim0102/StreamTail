import asyncio
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

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


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    result_code: str | None = None
    result_error: str | None = None
    result_access_token: str | None = None
    result_expires_in: int = 0

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # ПЕРЕХВАТЧИК ДЛЯ IMPLICIT FLOW:
        # Браузер не отправляет то, что после # на сервер. Если параметров нет, отдаем JS-скрипт,
        # который превратит # в ? и перезагрузит страницу, чтобы Python увидел токен.
        if not parsed.query and self.path == "/callback":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"""
                <!DOCTYPE html><html><body><script>
                if (window.location.hash) {
                    window.location.replace("/callback?" + window.location.hash.substring(1));
                } else {
                    document.body.innerHTML = "No token data received in URL.";
                }
                </script></body></html>
            """)
            return

        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        access_token = params.get("access_token", [None])[0]
        expires_in = params.get("expires_in", ["0"])[0]

        _OAuthCallbackHandler.result_code = code
        _OAuthCallbackHandler.result_error = error
        _OAuthCallbackHandler.result_access_token = access_token
        try:
            _OAuthCallbackHandler.result_expires_in = int(expires_in)
        except:
            _OAuthCallbackHandler.result_expires_in = 0

        if code or access_token:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(_ERROR_HTML)

    def log_message(self, *args):
        pass


async def wait_for_oauth_code(port: int = 19234, timeout: int = 120) -> dict | None:
    _OAuthCallbackHandler.result_code = None
    _OAuthCallbackHandler.result_error = None
    _OAuthCallbackHandler.result_access_token = None
    _OAuthCallbackHandler.result_expires_in = 0

    server = HTTPServer(("localhost", port), _OAuthCallbackHandler)
    server.timeout = 1
    loop = asyncio.get_event_loop()

    def _serve():
        start = time.monotonic()
        while (
            _OAuthCallbackHandler.result_code is None
            and _OAuthCallbackHandler.result_access_token is None
            and _OAuthCallbackHandler.result_error is None
            and time.monotonic() - start < timeout
        ):
            server.handle_request()
        server.server_close()

    await loop.run_in_executor(None, _serve)

    if _OAuthCallbackHandler.result_error:
        logger.warning(f"OAuth callback: ошибка платформы: {_OAuthCallbackHandler.result_error}")
        return None

    if not _OAuthCallbackHandler.result_code and not _OAuthCallbackHandler.result_access_token:
        logger.warning("OAuth callback: таймаут ожидания.")
        return None

    logger.debug("OAuth callback: данные получены успешно.")
    # Теперь сервер возвращает словарь со всеми возможными параметрами!
    return {
        "code": _OAuthCallbackHandler.result_code,
        "access_token": _OAuthCallbackHandler.result_access_token,
        "expires_in": _OAuthCallbackHandler.result_expires_in
    }
