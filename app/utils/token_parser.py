import json
import urllib.parse
from app.utils.logger import logger


def is_cookie_format(text: str) -> bool:
    """Проверяет, является ли строка набором кук (содержит ';' или '=' или 'Name raw' или '\t')."""
    val = text.strip()
    return ";" in val or "=" in val or "\t" in val or "Name raw" in val or "Host raw" in val


def parse_any_cookie_format(raw_input: str) -> str:
    """
    Универсальный парсер кук. Автоматически распознает и конвертирует в плоскую HTTP-строку Cookie:
    1. JSON-формат (Cookie Quick Manager / EditThisCookie)
    2. Netscape-формат (Get cookies.txt LOCALLY / Cookies.txt)
    3. Обычную HTTP-строку Cookie.
    """
    raw_input = raw_input.strip()
    if not raw_input:
        return ""

    is_json = False
    if raw_input.startswith("[") or raw_input.startswith("{"):
        is_json = True
    elif "Name raw" in raw_input or "Content raw" in raw_input or '"name"' in raw_input:
        is_json = True

    # --- 1. JSON формат ---
    if is_json:
        try:
            # Попытка автоматически закрыть скобки при обрезке файла
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
            logger.debug(f"TokenParser: стандартный JSON-импорт не удался ({e!r}). Запуск регулярных выражений...")

        # Резервное извлечение регулярными выражениями для поврежденных JSON-массивов
        try:
            import re
            blocks = re.findall(r'\{([^}]+)\}', raw_input)
            cookie_pairs = []
            for block in blocks:
                name_match = re.search(r'"(?:Name raw|name|Name)"\s*:\s*"([^"]*)"', block)
                value_match = re.search(r'"(?:Content raw|value|Content|value raw)"\s*:\s*"([^"]*)"', block)
                if name_match and value_match:
                    name = name_match.group(1).strip()
                    value = value_match.group(1).strip()
                    if name:
                        cookie_pairs.append(f"{name}={value}")
            if cookie_pairs:
                return "; ".join(cookie_pairs)
        except Exception as re_err:
            logger.debug(f"TokenParser: ошибка извлечения регулярным выражением JSON: {re_err!r}")

    # --- 2. Netscape формат ---
    elif "\t" in raw_input:
        try:
            cookie_pairs = []
            for line in raw_input.splitlines():
                line = line.strip()
                # Игнорируем пустые строки и комментарии
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 6:
                    name = parts[5].strip()
                    value = parts[6].strip() if len(parts) > 6 else ""
                    if name:
                        cookie_pairs.append(f"{name}={value}")
            if cookie_pairs:
                return "; ".join(cookie_pairs)
        except Exception as e:
            logger.debug(f"TokenParser: ошибка обработки формата Netscape: {e!r}")

    # --- 3. Возврат плоской строки по умолчанию ---
    return raw_input


def extract_cookie(cookie_str: str, name: str) -> str:
    """Извлекает значение конкретной куки из строки (регистронезависимо) с декодированием."""
    try:
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                if k.strip().lower() == name.lower():
                    return urllib.parse.unquote(v.strip())
    except Exception:
        pass
    return ""


def parse_local_storage(json_str: str, key: str) -> str:
    """Безопасно парсит JSON-строку LocalStorage и возвращает значение нужного ключа (регистронезависимо)."""
    json_str = json_str.strip()
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
