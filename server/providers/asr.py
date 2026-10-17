"""ASR：把一段 16k 单声道 WAV 变成维语文本。

- mock：演示用，返回脚本句（没有 key 时的默认）
- aliyun：阿里云智能语音交互「通用-维吾尔语」，一句话识别 RESTful 接口
- http：自建/第三方服务，POST multipart 字段 audio
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from ..config import Settings


class ASRError(RuntimeError):
    pass


@dataclass
class ASRResult:
    text: str
    provider: str
    gloss: str | None = None


class MockASR:
    """没有 key 时的演示 ASR。

    按顺序轮播脚本句，模拟"每句话都被听懂了"。
    """

    SCRIPT: tuple[tuple[str, str], ...] = (
        ("بۈگۈن ھاۋا قانداق؟", "今天天气怎么样？"),
        ("باشىم ئاغرىۋاتىدۇ، نېمە قىلسام بولىدۇ؟", "我头疼，怎么办？"),
        ("سىز كىم؟", "你是谁？"),
        ("بالىلىرىم يوقلاپ كەلمىدى.", "孩子们没来看我。"),
        ("دوختۇرخانىغا قانداق بارىمەن؟", "去医院怎么走？"),
        ("بىر ھېكايە ئوقۇپ بېرىڭ.", "给我讲个故事吧。"),
    )

    def __init__(self) -> None:
        self._index = 0

    async def transcribe(self, audio: bytes, filename: str = "audio.wav") -> ASRResult:
        index = self._index % len(self.SCRIPT)
        self._index += 1
        text, gloss = self.SCRIPT[index]
        return ASRResult(text=text, provider="mock", gloss=gloss)


class HttpASR:
    def __init__(self, url: str, api_key: str = "", provider: str = "http") -> None:
        self.url = url
        self.api_key = api_key
        self.provider = provider

    async def transcribe(self, audio: bytes, filename: str = "audio.wav") -> ASRResult:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.url,
                files={"audio": (filename, audio, "audio/wav")},
                headers=headers,
            )
        if resp.status_code >= 400:
            raise ASRError(f"ASR HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        text = data.get("text") or data.get("result") or ""
        if not text:
            raise ASRError("ASR 返回里没有 text 字段")
        return ASRResult(text=text, provider=self.provider)


class AliyunASR:
    """阿里云 ISI「通用-维吾尔语」一句话识别。

    token 需要用 AK/SK 走 RPC 签名换取（24 小时有效），只能在服务端做。
    注意：模型由控制台项目的 appkey 决定，请求里不带语言参数。
    """

    TOKEN_HOST = "https://nls-meta.cn-shanghai.aliyuncs.com/"
    GATEWAY = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"

    def __init__(self, appkey: str, access_key_id: str, access_key_secret: str) -> None:
        self.appkey = appkey
        self.ak_id = access_key_id
        self.ak_secret = access_key_secret
        self._token: str | None = None
        self._token_expire = 0.0

    # ---- RPC 签名 ----
    @staticmethod
    def _percent_encode(value: str) -> str:
        return (
            quote(str(value), safe="")
            .replace("+", "%20")
            .replace("*", "%2A")
            .replace("%7E", "~")
        )

    def _signed_params(self, extra: dict[str, str]) -> dict[str, str]:
        params = {
            "AccessKeyId": self.ak_id,
            "Action": "CreateToken",
            "Format": "JSON",
            "RegionId": "cn-shanghai",
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": uuid.uuid4().hex,
            "SignatureVersion": "1.0",
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2019-02-28",
        }
        params.update(extra)
        canonical = "&".join(
            f"{self._percent_encode(k)}={self._percent_encode(params[k])}"
            for k in sorted(params)
        )
        string_to_sign = f"GET&%2F&{self._percent_encode(canonical)}"
        digest = hmac.new(
            (self.ak_secret + "&").encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        params["Signature"] = base64.b64encode(digest).decode("ascii")
        return params

    async def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expire - 60:
            return self._token
        params = self._signed_params({})
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(self.TOKEN_HOST, params=params)
        if resp.status_code >= 400:
            raise ASRError(f"取 token 失败 {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        token = (data.get("Token") or {}).get("Id")
        if not token:
            raise ASRError(f"token 响应异常: {data}")
        self._token = token
        self._token_expire = float((data.get("Token") or {}).get("ExpireTime") or (now + 3600))
        return token

    async def transcribe(self, audio: bytes, filename: str = "audio.wav") -> ASRResult:
        token = await self._get_token()
        params = {
            "appkey": self.appkey,
            "format": "wav",
            "sample_rate": "16000",
            "enable_punctuation_prediction": "true",
            "enable_inverse_text_normalization": "true",
        }
        headers = {
            "X-NLS-Token": token,
            "Content-Type": "application/octet-stream",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.GATEWAY, params=params, content=audio, headers=headers
            )
        if resp.status_code >= 400:
            raise ASRError(f"ASR HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if int(data.get("status", 0)) != 200:
            raise ASRError(f"ASR 失败: {data}")
        return ASRResult(text=data.get("result") or "", provider="aliyun")


def build_asr(settings: Settings):
    kind = settings.resolved_asr()
    if kind == "aliyun":
        return AliyunASR(
            appkey=settings.asr_appkey,
            access_key_id=settings.asr_access_key_id,
            access_key_secret=settings.asr_access_key_secret,
        )
    if kind == "http":
        return HttpASR(settings.asr_url, settings.asr_api_key)
    return MockASR()
