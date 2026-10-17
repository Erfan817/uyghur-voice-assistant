"""汉维互译（B 臂用）。

不是要造一个翻译系统，只是把"翻译"这一步包成可替换的组件：
默认用同一个 LLM，配了专用翻译模型（如 Hunyuan-MT）就换成它。
"""

from __future__ import annotations

from ..config import Settings
from .llm import ChatResult, LLMError

_UG2ZH = (
    "把下面的维吾尔语翻译成简体中文。只输出译文，不要解释，不要加引号。\n"
    "如果原文本来就是中文，原样输出。\n\n{text}"
)

_ZH2UG = (
    "把下面的简体中文翻译成维吾尔语（阿拉伯字母 UEY）。只输出译文，不要解释。\n"
    "要求：口语化、短句、像家里长辈之间说话；不要书面腔。\n"
    "以下术语必须使用括号里的维语：{glossary}\n\n{text}"
)


class Translator:
    def __init__(self, client, glossary: dict[str, str] | None = None) -> None:
        self.client = client
        self.glossary = glossary or {}

    async def _ask(self, prompt: str) -> str:
        result: ChatResult = await self.client.chat(
            [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=300
        )
        return (result.text or "").strip().strip('"').strip()

    async def ug_to_zh(self, text: str) -> str:
        if not text.strip():
            return ""
        return await self._ask(_UG2ZH.format(text=text))

    async def zh_to_ug(self, text: str) -> str:
        if not text.strip():
            return ""
        glossary = "；".join(f"{zh}={ug}" for zh, ug in self.glossary.items())
        return await self._ask(_ZH2UG.format(text=text, glossary=glossary or "无"))


def build_translator(settings: Settings, glossary: dict[str, str] | None = None) -> Translator:
    from .llm import build_mt

    return Translator(build_mt(settings), glossary)


__all__ = ["Translator", "build_translator", "LLMError"]
