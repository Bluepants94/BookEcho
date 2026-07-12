from app.services.tts import build_speech_url, validate_base_url
from fastapi import HTTPException
import pytest


def test_build_speech_url_with_v1_suffix():
    assert (
        build_speech_url("https://api.xiaomimimo.com/v1")
        == "https://api.xiaomimimo.com/v1/audio/speech"
    )
    assert (
        build_speech_url("https://api.xiaomimimo.com/v1/")
        == "https://api.xiaomimimo.com/v1/audio/speech"
    )


def test_build_speech_url_root_host():
    assert (
        build_speech_url("https://api.openai.com")
        == "https://api.openai.com/v1/audio/speech"
    )


def test_build_speech_url_full_endpoint():
    assert (
        build_speech_url("https://api.example.com/v1/audio/speech")
        == "https://api.example.com/v1/audio/speech"
    )


def test_validate_public_url():
    assert validate_base_url("https://api.xiaomimimo.com/v1").startswith("https://")


def test_validate_blocks_localhost(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("TTS_ALLOW_PRIVATE_URLS", "false")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as ei:
        validate_base_url("http://127.0.0.1:8080/v1")
    assert ei.value.status_code == 400
    get_settings.cache_clear()
