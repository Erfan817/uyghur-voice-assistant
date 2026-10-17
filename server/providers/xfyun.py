"""讯飞在线语音合成（WebAPI 流式版）——目前唯一确认支持维吾尔语的商用 TTS。

要点（2026-10-17 从讯飞文档核实）：
- 支持语种里有维吾尔语，发音人示例：Dilare（维吾尔族语）、帕蒂古里（维吾尔语女声）
- **WebAPI 支持，SDK 不支持**维语/藏语/蒙古语 —— 我们走服务端，正好不受影响
- 必须先在讯飞控制台「添加发音人」，否则返回 11200；添加后控制台会给出 vcn 参数值
- 文档：https://www.xfyun.cn/doc/tts/online_tts/API.html

鉴权是 HMAC-SHA256 签 host/date/request-line，再 base64 成 authorization 放进 wss URL。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from email.utils import formatdate
from urllib.parse import urlencode

import websockets

HOST = "tts-api.xfyun.cn"
PATH = "/v2/tts"


class XunfeiError(RuntimeError):
    pass


@dataclass
class XunfeiConfig:
    app_id: str
    api_key: str
    api_secret: str
    vcn: str
    speed: int = 50  # 0–100，50 为正常语速；长辈场景建议 45 左右

    @property
    def ready(self) -> bool:
        return all([self.app_id, self.api_key, self.api_secret, self.vcn])


def build_auth_url(cfg: XunfeiConfig, date: str | None = None) -> str:
    """生成带鉴权参数的 wss 地址。date 可注入，方便单测。"""
    date = date or formatdate(usegmt=True)
    signature_origin = f"host: {HOST}\ndate: {date}\nGET {PATH} HTTP/1.1"
    digest = hmac.new(
        cfg.api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(digest).decode("ascii")
    authorization_origin = (
        f'api_key="{cfg.api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("ascii")
    query = urlencode({"authorization": authorization, "date": date, "host": HOST})
    return f"wss://{HOST}{PATH}?{query}"


def build_payload(cfg: XunfeiConfig, text: str) -> dict:
    return {
        "common": {"app_id": cfg.app_id},
        "business": {
            "aue": "lame",  # mp3，浏览器直接能放
            "sfl": 1,  # 开启流式
            "vcn": cfg.vcn,
            "tte": "UTF8",
            "speed": cfg.speed,
            "volume": 50,
            "pitch": 50,
        },
        "data": {
            "status": 2,
            "text": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        },
    }


async def synthesize(cfg: XunfeiConfig, text: str, timeout: float = 25.0) -> bytes:
    if not cfg.ready:
        raise XunfeiError("讯飞 TTS 配置不完整（app_id / api_key / api_secret / vcn）")
    if not text.strip():
        raise XunfeiError("空文本")

    url = build_auth_url(cfg)
    payload = build_payload(cfg, text)
    chunks: list[bytes] = []

    try:
        async with websockets.connect(url, close_timeout=5, max_size=8 * 1024 * 1024) as ws:
            await ws.send(json.dumps(payload, ensure_ascii=False))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                message = json.loads(raw)
                code = int(message.get("code") or 0)
                if code != 0:
                    raise XunfeiError(f"讯飞返回 {code}: {message.get('message')}")
                data = message.get("data") or {}
                audio = data.get("audio")
                if audio:
                    chunks.append(base64.b64decode(audio))
                if int(data.get("status") or 0) == 2:
                    break
    except XunfeiError:
        raise
    except Exception as exc:  # noqa: BLE001 - 网络/协议异常统一收敛
        raise XunfeiError(f"讯飞合成失败: {type(exc).__name__}: {exc}") from exc

    if not chunks:
        raise XunfeiError("讯飞没有返回音频")
    return b"".join(chunks)
