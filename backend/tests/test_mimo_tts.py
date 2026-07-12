from app.services.tts import (
    build_chat_completions_url,
    build_speech_url,
    detect_provider,
    parse_mimo_audio_response,
    pcm16_to_wav,
)
import base64
import json
from io import BytesIO
import wave


def test_detect_provider_mimo_host():
    assert detect_provider("https://api.xiaomimimo.com/v1", "mimo-v2.5-tts") == "mimo"
    assert detect_provider("https://api.openai.com/v1", "tts-1") == "openai"
    assert detect_provider("https://api.example.com/v1", "foo", provider="mimo") == "mimo"


def test_build_urls():
    assert build_chat_completions_url("https://api.xiaomimimo.com/v1") == (
        "https://api.xiaomimimo.com/v1/chat/completions"
    )
    assert build_speech_url("https://api.openai.com/v1") == (
        "https://api.openai.com/v1/audio/speech"
    )


def test_pcm16_to_wav_header():
    pcm = b"\x00\x00" * 100
    wav = pcm16_to_wav(pcm, sample_rate=24000)
    assert wav[:4] == b"RIFF"
    assert b"WAVE" in wav[:16]


def test_parse_mimo_sse_audio():
    pcm = b"\x01\x00" * 50
    b64 = base64.b64encode(pcm).decode()
    event = {
        "choices": [
            {
                "delta": {
                    "audio": {
                        "data": b64,
                    }
                }
            }
        ]
    }
    body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode()
    audio, ctype = parse_mimo_audio_response("text/event-stream", body)
    assert ctype == "audio/wav"
    assert audio[:4] == b"RIFF"


def test_parse_mimo_sse_audio_keeps_each_pcm_chunk_once():
    pcm = b"\x01\x00\xfe\xff" * 50
    b64 = base64.b64encode(pcm).decode()
    event = {
        "choices": [
            {
                "delta": {
                    "audio": {
                        "data": b64,
                    }
                }
            }
        ]
    }
    body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode()

    audio, ctype = parse_mimo_audio_response("text/event-stream", body)

    assert ctype == "audio/wav"
    with wave.open(BytesIO(audio), "rb") as wav:
        assert wav.getnframes() == len(pcm) // 2
        assert wav.readframes(wav.getnframes()) == pcm


def test_parse_mimo_sse_audio_keeps_short_nested_audio_data():
    pcm = b"\x01\x00\xfe\xff" * 4
    b64 = base64.b64encode(pcm).decode()
    assert len(b64) < 64
    event = {
        "choices": [
            {
                "delta": {
                    "audio": {
                        "data": b64,
                    }
                }
            }
        ]
    }
    body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode()

    audio, ctype = parse_mimo_audio_response("text/event-stream", body)

    assert ctype == "audio/wav"
    with wave.open(BytesIO(audio), "rb") as wav:
        assert wav.getnframes() == len(pcm) // 2
        assert wav.readframes(wav.getnframes()) == pcm


def test_parse_mimo_sse_audio_keeps_identical_chunks_from_separate_events():
    pcm = b"\x01\x00\xfe\xff" * 4
    b64 = base64.b64encode(pcm).decode()
    event = {"choices": [{"delta": {"audio": {"data": b64}}}]}
    body = (
        f"data: {json.dumps(event)}\n\ndata: {json.dumps(event)}\n\ndata: [DONE]\n\n"
    ).encode()

    audio, ctype = parse_mimo_audio_response("text/event-stream", body)

    assert ctype == "audio/wav"
    with wave.open(BytesIO(audio), "rb") as wav:
        assert wav.getnframes() == len(pcm + pcm) // 2
        assert wav.readframes(wav.getnframes()) == pcm + pcm


def test_parse_mimo_sse_audio_ignores_short_non_audio_metadata_data():
    pcm = b"\x01\x00\xfe\xff" * 4
    event = {
        "metadata": {"data": base64.b64encode(b"metadata").decode()},
        "choices": [
            {
                "delta": {
                    "audio": {"data": base64.b64encode(pcm).decode()},
                }
            }
        ],
    }
    body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode()

    audio, ctype = parse_mimo_audio_response("text/event-stream", body)

    assert ctype == "audio/wav"
    with wave.open(BytesIO(audio), "rb") as wav:
        assert wav.getnframes() == len(pcm) // 2
        assert wav.readframes(wav.getnframes()) == pcm
