import asyncio
import base64
import ipaddress
import json
import logging
import re
import socket
import wave
from io import BytesIO
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger("bookecho.tts")
settings = get_settings()

_user_semaphores: dict[int, asyncio.Semaphore] = {}
_lock = asyncio.Lock()

_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata", "0.0.0.0", "::1"})
_PRIVATE_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)
MAX_TTS_TEXT_CHARS = 8000

DEFAULT_MIMO_STYLE = (
    "用自然、清晰、稳定的中文朗读。语速适中，情感贴合小说叙述，不要额外解释。"
)


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "***"
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}***{api_key[-4:]}"


def normalize_base_url(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def detect_provider(base_url: str, model: str, provider: str | None = None) -> str:
    """Return 'mimo' or 'openai'."""
    explicit = (provider or "").strip().lower()
    if explicit in {"mimo", "xiaomi", "xiaomimimo"}:
        return "mimo"
    if explicit in {"openai", "openai_speech", "speech"}:
        return "openai"

    host = (urlparse(base_url).hostname or "").lower()
    model_l = (model or "").lower()
    if "xiaomimimo" in host or "mimo" in host:
        return "mimo"
    if model_l.startswith("mimo") or "mimo-" in model_l or model_l.endswith("-tts") and "mimo" in model_l:
        return "mimo"
    return "openai"


def build_speech_url(base_url: str) -> str:
    """OpenAI-compatible /v1/audio/speech endpoint."""
    base = normalize_base_url(base_url)
    lower = base.lower()
    if lower.endswith("/audio/speech"):
        return base
    if lower.endswith("/v1"):
        return f"{base}/audio/speech"
    return f"{base}/v1/audio/speech"


def build_chat_completions_url(base_url: str) -> str:
    """OpenAI-compatible /v1/chat/completions (Xiaomi Mimo TTS)."""
    base = normalize_base_url(base_url)
    lower = base.lower()
    if lower.endswith("/chat/completions"):
        return base
    if lower.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if IP is private/special, including IPv4-mapped IPv6."""
    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ip]
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        candidates.append(ip.ipv4_mapped)
    for candidate in candidates:
        if any(candidate in network for network in _PRIVATE_NETWORKS):
            return True
    return False


def _is_blocked_host(hostname: str) -> bool:
    host = hostname.strip().lower().strip("[]")
    if not host:
        return True
    if host in _BLOCKED_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return _is_blocked_ip(ip)


def _hostname_resolves_to_blocked(hostname: str) -> bool:
    """DNS-resolve hostname and reject if any address is private/special."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS base_url 主机无法解析",
        ) from exc
    if not infos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS base_url 主机无法解析",
        )
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            return True
    return False


def validate_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS base_url 无效",
        )

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS base_url 必须是 http 或 https",
        )

    host = parsed.hostname
    if not host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS base_url 主机无效",
        )

    allow_private = get_settings().tts_allow_private_urls
    if not allow_private:
        if _is_blocked_host(host):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TTS base_url 不允许访问内网或元数据地址",
            )
        # Literal IPs already checked; resolve hostnames to block DNS rebinding.
        try:
            ipaddress.ip_address(host.strip().lower().strip("[]"))
        except ValueError:
            if _hostname_resolves_to_blocked(host):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="TTS base_url 不允许访问内网或元数据地址",
                )
    return raw


def pcm16_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    """Wrap raw PCM16 LE into a WAV container for browser playback."""
    if not pcm_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TTS 返回空音频",
        )
    # Ensure even length for 16-bit samples.
    if len(pcm_data) % 2 == 1:
        pcm_data = pcm_data[:-1]
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _extract_base64_chunks(obj, in_audio_context: bool = False) -> list[str]:
    found: list[str] = []
    if obj is None:
        return found
    if isinstance(obj, str):
        # Heuristic: long base64-looking payloads only when parent path suggests audio.
        return found
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if key_l in {"audio", "data", "b64_json", "b64", "delta"} and isinstance(value, str):
                # Prefer keys that commonly carry audio.
                if key_l in {"b64_json", "b64"} or (
                    key_l == "data" and (in_audio_context or len(value) > 64)
                ):
                    found.append(value)
                elif key_l == "audio" and re.fullmatch(r"[A-Za-z0-9+/=\s]+", value or "") and len(value) > 64:
                    found.append(value)
            if isinstance(value, dict):
                found.extend(_extract_base64_chunks(value, in_audio_context or key_l == "audio"))
            elif isinstance(value, list):
                found.extend(_extract_base64_chunks(value, in_audio_context or key_l == "audio"))
        return found
    if isinstance(obj, list):
        for item in obj:
            found.extend(_extract_base64_chunks(item, in_audio_context))
    return found


def _decode_base64_list(chunks: list[str]) -> bytes:
    out = bytearray()
    for chunk in chunks:
        raw = re.sub(r"\s+", "", chunk or "")
        if not raw:
            continue
        try:
            out.extend(base64.b64decode(raw, validate=False))
        except Exception:
            continue
    return bytes(out)


def parse_mimo_audio_response(content_type: str, body: bytes) -> tuple[bytes, str]:
    """Parse Xiaomi Mimo / chat-completions TTS response into playable audio bytes."""
    ctype = (content_type or "").lower()
    if not body:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="TTS 返回空响应")

    # Direct binary audio.
    if "audio/" in ctype or "octet-stream" in ctype:
        if "wav" in ctype:
            return body, "audio/wav"
        if "mpeg" in ctype or "mp3" in ctype:
            return body, "audio/mpeg"
        # Assume pcm16 if labeled generically.
        return pcm16_to_wav(body), "audio/wav"

    text = body.decode("utf-8", errors="ignore").strip()
    if not text:
        # Raw pcm body without content-type.
        return pcm16_to_wav(body), "audio/wav"

    # SSE stream: data: {...}\n\n
    b64_chunks: list[str] = []
    if "text/event-stream" in ctype or text.startswith("data:"):
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            b64_chunks.extend(_extract_base64_chunks(obj))
            # Some gateways put pure base64 after data:
            if not b64_chunks and re.fullmatch(r"[A-Za-z0-9+/=]+", payload) and len(payload) > 64:
                b64_chunks.append(payload)
        audio = _decode_base64_list(b64_chunks)
        if audio:
            # If already RIFF/WAVE or ID3/mp3, pass through.
            if audio[:4] == b"RIFF":
                return audio, "audio/wav"
            if audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb":
                return audio, "audio/mpeg"
            return pcm16_to_wav(audio), "audio/wav"

    # JSON object body.
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: treat whole body as pcm.
        return pcm16_to_wav(body), "audio/wav"

    b64_chunks = _extract_base64_chunks(obj)
    audio = _decode_base64_list(b64_chunks)
    if not audio:
        # Sometimes choices[0].message.audio.data
        try:
            choices = obj.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                audio_obj = msg.get("audio") or {}
                data = audio_obj.get("data")
                if isinstance(data, str):
                    audio = base64.b64decode(re.sub(r"\s+", "", data), validate=False)
        except Exception:
            audio = b""

    if not audio:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="无法从 Mimo TTS 响应中解析音频数据",
        )
    if audio[:4] == b"RIFF":
        return audio, "audio/wav"
    if audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb":
        return audio, "audio/mpeg"
    return pcm16_to_wav(audio), "audio/wav"


async def _get_user_semaphore(user_id: int) -> asyncio.Semaphore:
    async with _lock:
        sem = _user_semaphores.get(user_id)
        if sem is None:
            sem = asyncio.Semaphore(settings.tts_max_concurrent_per_user)
            _user_semaphores[user_id] = sem
        return sem


def _auth_headers(api_key: str, provider: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 API Key")
    # Xiaomi sample uses `api-key`; many OpenAI-compatible gateways use Bearer.
    if provider == "mimo":
        headers["api-key"] = key
        headers["Authorization"] = f"Bearer {key}"
    else:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def _synthesize_openai(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    text: str,
    voice: str | None,
    speed: float | None,
) -> tuple[bytes, str]:
    url = build_speech_url(base_url)
    payload: dict = {
        "model": model,
        "input": text,
        "response_format": "mp3",
    }
    if voice:
        payload["voice"] = voice
    if speed is not None:
        payload["speed"] = speed

    resp = await client.post(url, json=payload, headers=_auth_headers(api_key, "openai"))
    if resp.status_code >= 400:
        logger.warning(
            "OpenAI TTS failed status=%s url=%s key=%s body=%s",
            resp.status_code,
            url,
            _mask_key(api_key),
            (resp.text or "")[:300],
        )
        msg = f"TTS 服务错误: {resp.status_code}"
        if resp.status_code == 404:
            msg += f"（请确认 Base URL 与模型。实际请求: {url}）"
        elif resp.status_code in {401, 403}:
            msg += "（API Key 或权限无效）"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)
    return resp.content, resp.headers.get("content-type", "audio/mpeg")


async def _synthesize_mimo(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    text: str,
    voice: str | None,
    style: str | None,
    audio_format: str | None,
) -> tuple[bytes, str]:
    url = build_chat_completions_url(base_url)
    style_text = (style or "").strip() or DEFAULT_MIMO_STYLE
    voice_name = (voice or "").strip() or "Chloe"
    fmt = (audio_format or "pcm16").strip() or "pcm16"

    payload = {
        "model": model or "mimo-v2.5-tts",
        "messages": [
            {"role": "user", "content": style_text},
            {"role": "assistant", "content": text},
        ],
        "audio": {
            "format": fmt,
            "voice": voice_name,
        },
        # Official sample uses stream=true; we collect the full stream server-side.
        "stream": True,
    }

    headers = _auth_headers(api_key, "mimo")
    resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        # Retry once without stream if provider rejects stream.
        if resp.status_code in {400, 404, 415, 422}:
            payload_no_stream = dict(payload)
            payload_no_stream["stream"] = False
            resp2 = await client.post(url, json=payload_no_stream, headers=headers)
            if resp2.status_code < 400:
                return parse_mimo_audio_response(
                    resp2.headers.get("content-type", ""),
                    resp2.content,
                )
            resp = resp2

        logger.warning(
            "Mimo TTS failed status=%s url=%s key=%s body=%s",
            resp.status_code,
            url,
            _mask_key(api_key),
            (resp.text or "")[:300],
        )
        msg = f"TTS 服务错误: {resp.status_code}"
        if resp.status_code == 404:
            msg += f"（请确认 Base URL 与模型。实际请求: {url}）"
        elif resp.status_code in {401, 403}:
            msg += "（API Key 或权限无效；Mimo 需 header: api-key）"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)

    return parse_mimo_audio_response(resp.headers.get("content-type", ""), resp.content)


async def synthesize_speech(
    *,
    user_id: int,
    base_url: str,
    api_key: str,
    model: str,
    text: str,
    voice: str | None = None,
    speed: float | None = None,
    provider: str | None = None,
    style: str | None = None,
    audio_format: str | None = None,
) -> tuple[bytes, str]:
    base_url = validate_base_url(base_url)
    if not (text or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="段落内容为空")
    if len(text) > MAX_TTS_TEXT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"段落过长，上限 {MAX_TTS_TEXT_CHARS} 字符",
        )

    provider_name = detect_provider(base_url, model, provider)
    sem = await _get_user_semaphore(user_id)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=0.05)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="TTS 并发请求过多，请稍后重试",
        ) from exc

    try:
        logger.info(
            "TTS request user=%s provider=%s model=%s base_url=%s key=%s chars=%s",
            user_id,
            provider_name,
            model,
            base_url,
            _mask_key(api_key),
            len(text),
        )
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=False) as client:
            if provider_name == "mimo":
                return await _synthesize_mimo(
                    client=client,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    text=text,
                    voice=voice,
                    style=style,
                    audio_format=audio_format,
                )
            return await _synthesize_openai(
                client=client,
                base_url=base_url,
                api_key=api_key,
                model=model,
                text=text,
                voice=voice,
                speed=speed,
            )
    finally:
        sem.release()
