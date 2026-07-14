import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services.crypto import decrypt_secret, encrypt_secret, mask_secret

_DEFAULTS: dict[str, Any] = {
    "base_url": "",
    "api_key": "",
    "model": "",
    "voice": "",
    "provider": "auto",
    "style": "",
    "audio_format": "pcm16",
    "cache_chapters": 3,
}


def _normalize_fields(src: dict[str, Any], api_key: str) -> dict[str, Any]:
    provider = str(src.get("provider") or "auto")[:32] or "auto"
    audio_format = str(src.get("audio_format") or "pcm16")[:32] or "pcm16"
    try:
        cache_chapters = int(src.get("cache_chapters", 3))
    except (TypeError, ValueError):
        cache_chapters = 3
    cache_chapters = max(0, min(10, cache_chapters))
    return {
        "base_url": str(src.get("base_url") or "")[:512],
        "api_key": str(api_key or "")[:512],
        "model": str(src.get("model") or "")[:128],
        "voice": str(src.get("voice") or "")[:64],
        "provider": provider,
        "style": str(src.get("style") or "")[:1000],
        "audio_format": audio_format,
        "cache_chapters": cache_chapters,
    }


def get_user_tts_settings(user: User) -> dict[str, Any]:
    raw = getattr(user, "tts_settings_json", None)
    if not raw:
        return dict(_DEFAULTS)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(_DEFAULTS)
    if not isinstance(parsed, dict):
        return dict(_DEFAULTS)
    plain_key = decrypt_secret(str(parsed.get("api_key") or ""))
    return _normalize_fields(parsed, plain_key)


def get_user_tts_settings_public(user: User) -> dict[str, Any]:
    data = get_user_tts_settings(user)
    data["api_key"] = mask_secret(data.get("api_key") or "")
    return data


def _should_keep_existing_key(incoming_key: str, current_key: str) -> bool:
    key = (incoming_key or "").strip()
    if not key:
        return True
    if key == mask_secret(current_key):
        return True
    # Accept any fully/mostly masked placeholder (e.g. "********ab12").
    if "*" in key and all(ch == "*" or ch.isalnum() for ch in key):
        visible = key.replace("*", "")
        if not visible:
            return True
        if current_key and current_key.endswith(visible):
            return True
    return False


def save_user_tts_settings(db: Session, user: User, data: dict[str, Any]) -> dict[str, Any]:
    incoming = data if isinstance(data, dict) else {}
    current = get_user_tts_settings(user)
    current_key = current.get("api_key") or ""
    incoming_key = str(incoming.get("api_key") or "")
    plain_key = current_key if _should_keep_existing_key(incoming_key, current_key) else incoming_key

    normalized = _normalize_fields(incoming, plain_key)
    store = dict(normalized)
    store["api_key"] = encrypt_secret(normalized.get("api_key") or "")
    user.tts_settings_json = json.dumps(store, ensure_ascii=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    public = dict(normalized)
    public["api_key"] = mask_secret(normalized.get("api_key") or "")
    return public
