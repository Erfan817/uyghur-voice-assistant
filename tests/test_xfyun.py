from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

from server.config import Settings
from server.providers.xfyun import XunfeiConfig, build_auth_url, build_payload

DATE = "Thu, 01 Jan 1970 00:00:00 GMT"


def make_config() -> XunfeiConfig:
    return XunfeiConfig(
        app_id="appid123",
        api_key="key123",
        api_secret="secret123",
        vcn="x4_dilare",
        speed=45,
    )


def test_auth_url_shape():
    url = build_auth_url(make_config(), date=DATE)
    assert url.startswith("wss://tts-api.xfyun.cn/v2/tts?")
    query = parse_qs(urlparse(url).query)
    assert query["host"] == ["tts-api.xfyun.cn"]
    assert query["date"] == [DATE]
    assert "authorization" in query


def test_authorization_is_signed_origin():
    url = build_auth_url(make_config(), date=DATE)
    query = parse_qs(urlparse(url).query)
    inner = base64.b64decode(query["authorization"][0]).decode("utf-8")
    assert 'api_key="key123"' in inner
    assert 'algorithm="hmac-sha256"' in inner
    assert 'headers="host date request-line"' in inner
    assert "signature=" in inner


def test_signature_changes_with_secret():
    a = build_auth_url(make_config(), date=DATE)
    cfg = make_config()
    cfg.api_secret = "other"
    b = build_auth_url(cfg, date=DATE)
    assert a != b


def test_payload_encodes_text():
    payload = build_payload(make_config(), "ياخشىمۇسىز")
    assert payload["business"]["vcn"] == "x4_dilare"
    assert payload["business"]["aue"] == "lame"
    assert base64.b64decode(payload["data"]["text"]).decode("utf-8") == "ياخشىمۇسىز"


def test_config_detects_xunfei():
    settings = Settings()
    settings.xf_app_id = "a"
    settings.xf_api_key = "b"
    settings.xf_api_secret = "c"
    settings.xf_vcn = "x4_dilare"
    assert settings.has_xunfei()
    assert settings.ug_tts() == "xunfei"
    assert settings.has_ug_voice()


def test_config_without_voice():
    settings = Settings()
    settings.xf_app_id = ""
    settings.tts_voice_ug = ""
    settings.tts_url = ""
    assert settings.ug_tts() == "none"
    assert not settings.has_ug_voice()
