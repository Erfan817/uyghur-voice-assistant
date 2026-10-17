"""LLM：OpenAI 兼容接口（DeepSeek / DashScope / SiliconFlow / 自建都能用）。

没有 key 时用 MockLLM，让整条链路在 demo 模式下也能跑通。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import httpx

from ..config import Settings


class LLMError(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    gloss: str | None = None
    model: str = ""


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int = 400,
    ) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
        if resp.status_code >= 400:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"LLM 响应异常: {str(data)[:300]}")
        text = ((choices[0].get("message") or {}).get("content") or "").strip()
        return ChatResult(text=text, model=data.get("model") or self.model)


class MockLLM:
    """演示用。按关键词回脚本，保证没有 key 时也能看到完整交互。"""

    REPLIES: tuple[tuple[tuple[str, ...], str, str], ...] = (
        (
            ("ھاۋا", "天气"),
            "بۈگۈن ھاۋا ياخشى. سىرتقا چىققاندا ئىسسىق كىيىنىڭ.",
            "今天天气不错，出门穿暖和点。",
        ),
        (
            ("باش", "ئاغرى", "疼", "药", "دورا"),
            "باش ئاغرىقى بولسا، سەل ياتىپ دەم ئېلىڭ. ئۇزاققا سۆرەلسە دوختۇرغا كۆرۈنۈڭ. دورا ئىسمىنى مەن ئېيتالمايمەن.",
            "头疼先躺下歇一会儿。拖久了就去看医生，药名我不能说。",
        ),
        (
            ("بالا", "يوقلا", "孩子"),
            "بالىلىرىڭىز ئىش بىلەن ئالدىراش بولۇشى مۇمكىن. ئۇلارغا سېغىنىۋاتقانلىقىڭىزنى ئېيتىپ قويسىڭىز بولىدۇ.",
            "孩子们可能是忙。想他们了就跟他们说一声。",
        ),
        (
            ("دوختۇرخانا", "医院", "قانداق"),
            "ئالدى بىلەن ئائىلىڭىزدىكىلەرگە ئېيتىڭ، ئۇلار سىزنى ئاپارسۇن. يالغۇز ماڭماڭ.",
            "先跟家里人说，让他们带您去，别一个人去。",
        ),
        (
            ("كىم", "你是谁", "سىز"),
            "مەن ئاينۇر. سىزنى ئاڭلاپ، ياردەم قىلىش ئۈچۈن مۇشۇ يەردە.",
            "我是 Aynur，在这儿听您说话、给您帮忙。",
        ),
    )

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int = 400,
    ) -> ChatResult:
        user = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user = message.get("content") or ""
                break
        for keywords, ug, zh in self.REPLIES:
            if any(word in user for word in keywords):
                return ChatResult(text=ug, gloss=zh, model="mock")
        return ChatResult(
            text="ھەئە، ئاڭلىدىم. داۋاملىق سۆزلەڭ.",
            gloss="嗯，听到了，您接着说。",
            model="mock",
        )


def build_llm(settings: Settings):
    if settings.llm_api_key:
        return OpenAICompatLLM(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
        )
    return MockLLM()


def build_mt(settings: Settings):
    """B1 臂的专用翻译模型。没配就退回主 LLM。"""
    if settings.mt_api_key:
        return OpenAICompatLLM(
            base_url=settings.mt_base_url,
            api_key=settings.mt_api_key,
            model=settings.mt_model,
            temperature=0.0,
        )
    return build_llm(settings)
