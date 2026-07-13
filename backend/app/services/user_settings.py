import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import User

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


def _normalize(data: dict[str, Any] | None) -> dict[str, Any]:
    src = data if isinstance(data, dict) else {}
    provider = str(src.get("provider") or "auto")[:32] or "auto"
    audio_format = str(src.get("audio_format") or "pcm16")[:32] or "pcm16"
    try:
        cache_chapters = int(src.get("cache_chapters", 3))
    except (TypeError, ValueError):
        cache_chapters = 3
    cache_chapters = max(0, min(10, cache_chapters))
    return {
        "base_url": str(src.get("base_url") or "")[:512],
        "api_key": str(src.get("api_key") or "")[:512],
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
    return _normalize(parsed)


def save_user_tts_settings(db: Session, user: User, data: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize(data)
    user.tts_settings_json = json.dumps(normalized, ensure_ascii=False)
    db.add(user)
    db.commit()
    db.refresh(user)
    return normalized
