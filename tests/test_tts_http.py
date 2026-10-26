from __future__ import annotations

import asyncio
import io
import wave

import httpx
import pytest

from server.config import Settings
from server.providers import tts


def wav_audio() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 24)
    return buffer.getvalue()


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "DATA_DIR", tmp_path)
    settings = Settings()
    settings.xf_app_id = ""
    settings.tts_provider = "http"
    settings.tts_url = "http://tts.test/tts"
    settings.tts_voice_ug = "sister-v1"
    settings.tts_api_key = ""
    return tts.TTSService(settings)


@pytest.mark.parametrize(
    ("audio", "content_type", "suffix", "mime"),
    [
        (wav_audio(), "audio/wav", ".wav", "audio/wav"),
        (b"ID3mock-mp3-audio", "audio/mpeg", ".mp3", "audio/mpeg"),
    ],
)
def test_http_audio_format_cache_and_voice_change(
    service, monkeypatch, audio, content_type, suffix, mime
):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=audio, headers={"Content-Type": content_type})

    client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        tts.httpx, "AsyncClient", lambda **kwargs: client(transport=transport, **kwargs)
    )
    first = asyncio.run(service.speak("ياخشىمۇسىز", "ug"))
    assert first.path.suffix == suffix
    assert first.mime == mime
    assert first.path.read_bytes() == audio
    assert not first.cached

    cached = asyncio.run(service.speak("ياخشىمۇسىز", "ug"))
    assert cached.cached
    assert cached.path == first.path
    assert cached.mime == mime
    assert len(requests) == 1

    service.settings.tts_voice_ug = "sister-v2"
    changed = asyncio.run(service.speak("ياخشىمۇسىز", "ug"))
    assert not changed.cached
    assert changed.path != first.path
    assert len(requests) == 2


def test_legacy_wav_cache_is_reused_with_correct_extension(service, monkeypatch):
    audio = wav_audio()
    key = tts._digest("http", service.settings.tts_voice_ug, "ياخشىمۇسىز")
    legacy_path = service.cache_dir / f"{key}.mp3"
    legacy_path.write_bytes(audio)

    async def unexpected_request(*args):
        pytest.fail("A cached reference must not require another TTS request")

    monkeypatch.setattr(service, "_http", unexpected_request)
    result = asyncio.run(service.speak("ياخشىمۇسىز", "ug"))
    assert result.cached
    assert result.path.suffix == ".wav"
    assert result.mime == "audio/wav"
    assert result.path.read_bytes() == audio
