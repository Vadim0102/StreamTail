import sys
import subprocess
import uuid
import hashlib
import os
import base64


def get_hardware_id() -> str:
    """
    Получает стабильный уникальный идентификатор материнской платы / оборудования.
    """
    hw_id = ""
    try:
        if sys.platform == "win32":
            # Запрос UUID материнской платы через wmic
            out = subprocess.check_output("wmic csproduct get uuid", shell=True)
            lines = [line.strip() for line in out.decode().split("\n") if line.strip()]
            if len(lines) > 1:
                hw_id = lines[1]
        elif sys.platform == "darwin":
            out = subprocess.check_output("system_profiler SPHardwareDataType | grep 'Hardware UUID'", shell=True)
            hw_id = out.decode().split(":")[1].strip()
        else:  # Linux
            # Пробуем uuid продукта
            for path in ["/sys/class/dmi/id/product_uuid", "/etc/machine-id"]:
                try:
                    with open(path, "r") as f:
                        hw_id = f.read().strip()
                        if hw_id:
                            break
                except Exception:
                    pass
    except Exception:
        pass

    if not hw_id or hw_id.upper() == "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF":
        # Резервный вариант на основе MAC-адреса и платформы
        fallback = f"{uuid.getnode()}-{sys.platform}"
        hw_id = hashlib.sha256(fallback.encode()).hexdigest()

    return hw_id


def _get_key() -> bytes:
    # Генерируем 32-байтный ключ на основе ID оборудования
    return hashlib.sha256(get_hardware_id().encode("utf-8")).digest()


def encrypt_text(plain_text: str) -> str:
    """
    Шифрует строку с использованием стабильного ключа оборудования (без внешних зависимостей).
    """
    if not plain_text:
        return ""
    key = _get_key()
    iv = os.urandom(16)
    data = plain_text.encode("utf-8")

    # Кастомный безопасный потоковый шифр на базе SHA256 (аналог ChaCha с обратной связью)
    encrypted = bytearray()
    keystream = hashlib.sha256(key + iv).digest()
    for i in range(len(data)):
        if i > 0 and i % 32 == 0:
            keystream = hashlib.sha256(key + keystream).digest()
        encrypted.append(data[i] ^ keystream[i % 32])

    # Склеиваем IV и шифротекст, кодируем в Base64
    combined = iv + encrypted
    return base64.b64encode(combined).decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    """
    Расшифровывает строку. В случае изменения железа возвращает пустую строку во избежание крашей.
    """
    if not cipher_text:
        return ""
    try:
        raw = base64.b64decode(cipher_text.encode("utf-8"))
        if len(raw) < 16:
            return ""
        iv = raw[:16]
        encrypted = raw[16:]
        key = _get_key()

        decrypted = bytearray()
        keystream = hashlib.sha256(key + iv).digest()
        for i in range(len(encrypted)):
            if i > 0 and i % 32 == 0:
                keystream = hashlib.sha256(key + keystream).digest()
            decrypted.append(encrypted[i] ^ keystream[i % 32])

        return decrypted.decode("utf-8")
    except Exception:
        return ""
