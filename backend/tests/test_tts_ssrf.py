import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.config import get_settings
from app.services.tts import validate_base_url


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TTS_ALLOW_PRIVATE_URLS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com",
        "http://tts.example.com/v1",
        "https://cdn.example.org:8443/path",
    ],
)
def test_validate_base_url_allows_public(base_url: str):
    assert validate_base_url(base_url) == base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://api.example.com",
        "file:///etc/passwd",
        "not-a-url",
        "",
        "http://",
    ],
)
def test_validate_base_url_rejects_scheme_or_empty(base_url: str):
    with pytest.raises(HTTPException) as exc:
        validate_base_url(base_url)
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost/v1",
        "http://127.0.0.1:8080",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://10.1.2.3/tts",
        "http://172.16.0.1",
        "http://172.31.255.255",
        "http://192.168.1.10",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata/",
    ],
)
def test_validate_base_url_rejects_private_by_default(base_url: str):
    with pytest.raises(HTTPException) as exc:
        validate_base_url(base_url)
    assert exc.value.status_code == 400
    assert "内网" in str(exc.value.detail) or "元数据" in str(exc.value.detail)


def test_validate_base_url_allows_private_when_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TTS_ALLOW_PRIVATE_URLS", "true")
    get_settings.cache_clear()
    assert validate_base_url("http://127.0.0.1:9000") == "http://127.0.0.1:9000"
    assert validate_base_url("http://192.168.0.5") == "http://192.168.0.5"


def test_validate_base_url_still_requires_http_when_private_allowed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TTS_ALLOW_PRIVATE_URLS", "true")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        validate_base_url("ftp://127.0.0.1")
    assert exc.value.status_code == 400


def test_validate_base_url_rejects_dns_rebinding_to_loopback(monkeypatch: pytest.MonkeyPatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (None, None, None, None, ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr("app.services.tts.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException) as exc:
        validate_base_url("http://evil.example.com/v1")
    assert exc.value.status_code == 400
    assert "内网" in str(exc.value.detail) or "元数据" in str(exc.value.detail)


def test_validate_base_url_rejects_dns_rebinding_to_metadata(monkeypatch: pytest.MonkeyPatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (None, None, None, None, ("169.254.169.254", 0)),
        ]

    monkeypatch.setattr("app.services.tts.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException) as exc:
        validate_base_url("https://metadata.example.org/latest")
    assert exc.value.status_code == 400


def test_validate_base_url_allows_public_hostname_when_dns_public(monkeypatch: pytest.MonkeyPatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (None, None, None, None, ("93.184.216.34", 0)),
        ]

    monkeypatch.setattr("app.services.tts.socket.getaddrinfo", fake_getaddrinfo)
    assert validate_base_url("https://tts.example.com/v1") == "https://tts.example.com/v1"

