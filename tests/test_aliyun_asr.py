from __future__ import annotations

import base64

import pytest

from server.providers.asr import AliyunASR, ASRError

FIXED_NONCE = "0123456789abcdef0123456789abcdef"
FIXED_TS = "2026-10-17T12:00:00Z"


def make() -> AliyunASR:
    return AliyunASR(
        appkey="appkey-123",
        access_key_id="AKID",
        access_key_secret="SECRET",
        region="cn-shanghai",
    )


def test_percent_encode():
    encode = AliyunASR._percent_encode
    assert encode("a b") == "a%20b"
    assert encode("a*b") == "a%2Ab"
    assert encode("~") == "~"
    assert encode("/") == "%2F"
    assert encode(":") == "%3A"


def test_signed_params_are_deterministic():
    signer = make()
    first = signer._signed_params(nonce=FIXED_NONCE, timestamp=FIXED_TS)
    second = signer._signed_params(nonce=FIXED_NONCE, timestamp=FIXED_TS)
    assert first == second
    assert first["Action"] == "CreateToken"
    assert first["Version"] == "2019-02-28"
    assert first["RegionId"] == "cn-shanghai"
    assert base64.b64decode(first["Signature"]) != b""


def test_signature_changes_with_secret():
    a = make()._signed_params(nonce=FIXED_NONCE, timestamp=FIXED_TS)
    other = AliyunASR("appkey-123", "AKID", "OTHER-SECRET")
    b = other._signed_params(nonce=FIXED_NONCE, timestamp=FIXED_TS)
    assert a["Signature"] != b["Signature"]


def test_hosts_follow_region():
    signer = AliyunASR("k", "id", "secret", region="cn-beijing")
    assert signer.token_host == "https://nls-meta.cn-beijing.aliyuncs.com/"
    assert signer.gateway == "https://nls-gateway-cn-beijing.aliyuncs.com/stream/v1/asr"


def test_parse_accepts_20000000():
    assert AliyunASR._parse_response({"status": 20000000, "result": "سالام"}) == "سالام"
    assert AliyunASR._parse_response({"status": 200, "result": "سالام"}) == "سالام"


def test_parse_keeps_empty_result():
    assert AliyunASR._parse_response({"status": 20000000, "result": ""}) == ""


def test_parse_rejects_error_status():
    with pytest.raises(ASRError):
        AliyunASR._parse_response({"status": 40000000, "message": "bad"})


def test_parse_rejects_missing_status():
    with pytest.raises(ASRError):
        AliyunASR._parse_response({"result": "x"})
