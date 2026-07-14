"""Secret helpers for at-rest encryption of sensitive user settings."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_ENC_PREFIX = "enc:"


def _fernet() -> Fernet:
    # Derive a stable 32-byte urlsafe key from the app secret.
    digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str:
    plain = (value or "").strip()
    if not plain:
        return ""
    if plain.startswith(_ENC_PREFIX):
        return plain
    token = _fernet().encrypt(plain.encode("utf-8")).decode("ascii")
    return f"{_ENC_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str:
    raw = value or ""
    if not raw:
        return ""
    if not raw.startswith(_ENC_PREFIX):
        # Legacy plaintext rows remain readable until next save.
        return raw
    token = raw[len(_ENC_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""


def mask_secret(value: str | None) -> str:
    plain = (value or "").strip()
    if not plain:
        return ""
    if len(plain) <= 4:
        return "*" * len(plain)
    return f"{'*' * max(4, len(plain) - 4)}{plain[-4:]}"
