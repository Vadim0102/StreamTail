import socket
import struct
import base64
import urllib.parse
import asyncio
import contextlib
import httpx
from app.utils import db

_shared_client: httpx.AsyncClient | None = None
_last_proxy_url: str | None = None
_client_lock: asyncio.Lock | None = None


def get_proxy_settings() -> str | None:
    config = db.get_setting("app_config") or {}
    proxy_url = config.get("app", {}).get("proxy_url", "").strip()
    return proxy_url if proxy_url else None


async def get_shared_client() -> httpx.AsyncClient:
    global _shared_client, _last_proxy_url, _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()

    current_proxy = get_proxy_settings()
    async with _client_lock:
        if _shared_client is None or current_proxy != _last_proxy_url:
            if _shared_client:
                try:
                    await _shared_client.aclose()
                except Exception:
                    pass
            # Пул соединений: увеличен дефолтный таймаут до 20.0 секунд для предотвращения ложных таймаутов
            _shared_client = httpx.AsyncClient(proxy=current_proxy, timeout=20.0)
            _last_proxy_url = current_proxy
        return _shared_client


async def close_shared_client():
    global _shared_client, _client_lock
    if _shared_client:
        try:
            await _shared_client.aclose()
        except Exception:
            pass
        _shared_client = None


@contextlib.asynccontextmanager
async def create_client(timeout: float = 20.0):
    client = await get_shared_client()
    yield client


def connect_via_proxy_sync(target_host: str, target_port: int, proxy_url: str) -> socket.socket:
    parsed = urllib.parse.urlparse(proxy_url)
    proxy_scheme = parsed.scheme.lower()
    proxy_host = parsed.hostname
    proxy_port = parsed.port or (1080 if "socks" in proxy_scheme else 8080)

    sock = socket.create_connection((proxy_host, proxy_port), timeout=15.0)
    sock.setblocking(True)

    try:
        if "socks5" in proxy_scheme:
            sock.sendall(b"\x05\x01\x00")
            res = sock.recv(2)
            if len(res) < 2 or res[0] != 5 or res[1] != 0:
                raise Exception(f"SOCKS5 greeting failed: {res}")

            host_bytes = target_host.encode("utf-8")
            request = (
                    struct.pack("!BBBB", 5, 1, 0, 3) +
                    struct.pack("!B", len(host_bytes)) +
                    host_bytes +
                    struct.pack("!H", target_port)
            )
            sock.sendall(request)

            reply = sock.recv(4)
            if len(reply) < 4 or reply[1] != 0:
                raise Exception(f"SOCKS5 proxy connection failed: {reply[1] if len(reply) >= 2 else 'unknown'}")

            atyp = reply[3]
            if atyp == 1:
                sock.recv(4 + 2)
            elif atyp == 3:
                len_byte = sock.recv(1)
                if len_byte:
                    sock.recv(len_byte[0] + 2)
            elif atyp == 4:
                sock.recv(16 + 2)

        elif "http" in proxy_scheme:
            auth_header = ""
            if parsed.username and parsed.password:
                auth_str = f"{parsed.username}:{parsed.password}"
                encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
                auth_header = f"Proxy-Authorization: Basic {encoded_auth}\r\n"

            connect_req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n{auth_header}\r\n"
            sock.sendall(connect_req.encode("utf-8"))

            resp_data = b""
            while b"\r\n\r\n" not in resp_data:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                resp_data += chunk

            first_line = resp_data.split(b"\r\n")[0].decode("utf-8")
            if "200" not in first_line:
                raise Exception(f"HTTP Proxy CONNECT failed: {first_line}")
        else:
            raise Exception(f"Unsupported proxy scheme: {proxy_scheme}")

        return sock
    except Exception as e:
        sock.close()
        raise e


async def open_proxied_connection(target_host: str, target_port: int, proxy_url: str, ssl_context=None):
    loop = asyncio.get_running_loop()
    sock = await loop.run_in_executor(None, connect_via_proxy_sync, target_host, target_port, proxy_url)
    reader, writer = await asyncio.open_connection(
        sock=sock,
        ssl=ssl_context,
        server_hostname=target_host if ssl_context else None
    )
    return reader, writer
