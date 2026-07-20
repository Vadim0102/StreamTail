import sys
import subprocess
import uuid
import hashlib
import hmac
import os
import base64


def get_hardware_id() -> str:
    hw_id = ""
    try:
        if sys.platform == "win32":
            kwargs = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.DEVNULL,
                "shell": True
            }
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            try:
                out = subprocess.check_output("wmic csproduct get uuid", **kwargs)
                lines = [line.strip() for line in out.decode().split("\n") if line.strip()]
                if len(lines) > 1:
                    hw_id = lines[1]
            except Exception:
                pass

            if not hw_id or hw_id.upper() == "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF":
                try:
                    import winreg
                    registry_key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Microsoft\Cryptography",
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY
                    )
                    value, _ = winreg.QueryValueEx(registry_key, "MachineGuid")
                    winreg.CloseKey(registry_key)
                    if value:
                        hw_id = str(value).strip()
                except Exception:
                    pass
        elif sys.platform == "darwin":
            out = subprocess.check_output("system_profiler SPHardwareDataType | grep 'Hardware UUID'", shell=True)
            hw_id = out.decode().split(":")[1].strip()
        else:  # Linux
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
        fallback = f"{uuid.getnode()}-{sys.platform}"
        hw_id = hashlib.sha256(fallback.encode()).hexdigest()

    return hw_id


def _get_derived_keys() -> tuple[bytes, bytes]:
    """Генерирует два раздельных ключа: для шифрования данных и для проверки целостности HMAC."""
    base_key = hashlib.sha256(get_hardware_id().encode("utf-8")).digest()
    enc_key = hashlib.sha256(base_key + b"encryption-key-salt-v1").digest()
    mac_key = hashlib.sha256(base_key + b"hmac-key-salt-v1").digest()
    return enc_key, mac_key


def encrypt_text(plain_text: str) -> str:
    """Шифрует строку и вычисляет HMAC-SHA256 подпись целостности (Encrypt-then-MAC)."""
    if not plain_text:
        return ""

    enc_key, mac_key = _get_derived_keys()
    iv = os.urandom(16)
    data = plain_text.encode("utf-8")

    # Потоковый шифр на базе SHA256
    encrypted = bytearray()
    keystream = hashlib.sha256(enc_key + iv).digest()
    for i in range(len(data)):
        if i > 0 and i % 32 == 0:
            keystream = hashlib.sha256(enc_key + keystream).digest()
        encrypted.append(data[i] ^ keystream[i % 32])

    encrypted_bytes = bytes(encrypted)
    # Вычисление подписи HMAC поверх IV и зашифрованных данных
    signature = hmac.new(mac_key, iv + encrypted_bytes, hashlib.sha256).digest()

    combined = iv + signature + encrypted_bytes
    return base64.b64encode(combined).decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    """Проверяет HMAC-подпись и расшифровывает строку при совпадении тега целостности."""
    if not cipher_text:
        return ""
    try:
        raw = base64.b64decode(cipher_text.encode("utf-8"))
        if len(raw) < 48:  # 16 (IV) + 32 (HMAC SHA256)
            return ""

        iv = raw[:16]
        signature = raw[16:48]
        encrypted_bytes = raw[48:]

        enc_key, mac_key = _get_derived_keys()

        # Проверка целостности данных
        expected_signature = hmac.new(mac_key, iv + encrypted_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_signature):
            return ""

        # Дешифрование
        decrypted = bytearray()
        keystream = hashlib.sha256(enc_key + iv).digest()
        for i in range(len(encrypted_bytes)):
            if i > 0 and i % 32 == 0:
                keystream = hashlib.sha256(enc_key + keystream).digest()
            decrypted.append(encrypted_bytes[i] ^ keystream[i % 32])

        return decrypted.decode("utf-8")
    except Exception:
        return ""
