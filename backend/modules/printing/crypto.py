"""Fernet encryption for printer API credentials."""
from cryptography.fernet import Fernet, InvalidToken
from core.config import get_settings


def _get_fernet() -> Fernet | None:
    key = get_settings().printer_credential_encryption_key
    if not key:
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_credential(value: str) -> str:
    f = _get_fernet()
    if not f:
        return value  # no encryption key configured – store as-is (dev only)
    return f.encrypt(value.encode()).decode()


def decrypt_credential(value: str) -> str:
    f = _get_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        return ""
