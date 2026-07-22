import json
import re
import urllib.parse
from app.utils.logger import logger


def is_cookie_format(text: str) -> bool:
    """Проверяет, является ли строка набором кук."""
    val = text.strip()
    return ";" in val or "=" in val or "\t" in val or "Name raw" in val or "Host raw" in val or ".vkvideo.ru" in val or "\n" in val


def parse_netscape_cookie_file(text: str) -> str:
    """
    Преобразует многострочный Netscape cookie файл в единую плоскую HTTP-строку кук [1].
    Игнорирует комментарии и корректно разбирает табы и пробелы.
    """
    cookie_pairs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Сначала пробуем разделить по табуляции, затем по множественным пробелам
        parts = line.split("\t")
        if len(parts) < 6:
            parts = re.split(r'\s+', line)

        if len(parts) >= 6:
            name = parts[5].strip()
            value = parts[6].strip() if len(parts) > 6 else ""
            if name:
                cookie_pairs.append(f"{name}={value}")

    return "; ".join(cookie_pairs)


def parse_any_cookie_format(raw_input: str) -> str:
    """
    Универсальный парсер кук. Гарантированно исключает возвращение многострочных строк [1].
    """
    raw_input = raw_input.strip()
    if not raw_input:
        return ""

    # Если есть переносы строк, это однозначно файл кук (Netscape/Header text) [1]
    if "\n" in raw_input:
        parsed_netscape = parse_netscape_cookie_file(raw_input)
        if parsed_netscape:
            return parsed_netscape

    # Если это JSON формат (EditThisCookie / Cookie Quick Manager)
    if raw_input.startswith("[") or raw_input.startswith("{"):
        try:
            json_to_parse = raw_input
            if json_to_parse.startswith("[") and not json_to_parse.endswith("]"):
                json_to_parse = json_to_parse.rstrip().rstrip(",")
                if not json_to_parse.endswith("]"):
                    json_to_parse += "]"

            cookies_list = json.loads(json_to_parse)
            if isinstance(cookies_list, dict):
                cookies_list = [cookies_list]

            cookie_pairs = []
            for c in cookies_list:
                name = c.get("Name raw") or c.get("name") or c.get("Name")
                value = c.get("Content raw") or c.get("value") or c.get("Content") or c.get("value raw")
                if name and value is not None:
                    cookie_pairs.append(f"{name}={value}")
            if cookie_pairs:
                return "; ".join(cookie_pairs)
        except Exception as e:
            logger.debug(f"TokenParser: ошибка парсинга JSON кук: {e!r}")

    # Удаляем случайные оставшиеся символы переноса строк для безопасности HTTP-заголовков [1]
    return raw_input.replace("\r", "").replace("\n", " ")


def extract_cookie(cookie_str: str, name: str) -> str:
    """Извлекает значение конкретной куки из строки с декодированием и очисткой кавычек [1]."""
    try:
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                if k.strip().lower() == name.lower():
                    val = urllib.parse.unquote(v.strip())
                    return val.strip('"').strip("'")
    except Exception:
        pass
    return ""


def parse_local_storage(json_str: str, key: str) -> str:
    """Безопасно парсит JSON-строку LocalStorage/куки и возвращает значение ключа [1]."""
    json_str = json_str.strip().strip('"').strip("'")
    if not json_str.startswith("{") or not json_str.endswith("}"):
        return ""
    try:
        data = json.loads(json_str)
        for k, v in data.items():
            if k.lower() == key.lower():
                return str(v).strip()
    except Exception:
        pass
    return ""
