"""一条对话的完整链路：ASR → 规范化 → 安全路由 → LLM → 后检 → TTS。

四种链路（M0 的评测维度，运行时可选）：
- A   直出维语（最小提示词）
- A'  直出维语 + 人设 + 术语表（默认）
- B1  维→汉 → 中文推理 → 汉→维（专用翻译模型）
- B2  同上，但翻译也用对话 LLM
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import persona, safety, weather
from .config import Settings
from .memory import Store
from .normalize import clamp_length, is_ug, normalize_ug, split_sentences
from .persona import GLOSSARY, build_system_prompt
from .providers.asr import ASRError, build_asr
from .providers.llm import LLMError, build_llm, build_mt
from .providers.mt import Translator
from .providers.tts import TTSError, TTSService

_WEATHER_WORDS = (
    "天气",
    "气温",
    "下雨",
    "冷不冷",
    "热不热",
    "ھاۋا",
    "سوغۇق",
    "ئىسسىق",
    "يامغۇر",
    "قار",
)
_HISTORY_LIMIT = 6
_MINIMAL_PROMPT = (
    "你是 Aynur。只用维吾尔语（阿拉伯字母 UEY）回答，句子短，1–3 句。"
    "不懂就说不会，不要编。"
)
_ZH_PROMPT = (
    "你是一个温和、耐心的中文助手，正在帮一位维吾尔族长辈回答问题。"
    "请用简体中文回答，口语化、短句、不超过 3 句。"
    "医疗问题不给药名和剂量，只建议问医生；宗教问题不做教法判断；政策问题提示以官方为准。"
)


@dataclass
class TurnResult:
    session_id: str
    transcript_ug: str
    transcript_zh: str | None
    reply_ug: str
    reply_zh: str | None
    audio_url: str | None
    audio_lang: str | None
    category: str
    arm: str
    mode: str
    latency_ms: dict[str, int] = field(default_factory=dict)
    audio_cached: bool = False
    fallback: str | None = None

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "transcript_ug": self.transcript_ug,
            "transcript_zh": self.transcript_zh,
            "reply_ug": self.reply_ug,
            "reply_zh": self.reply_zh,
            "audio_url": self.audio_url,
            "audio_lang": self.audio_lang,
            "category": self.category,
            "arm": self.arm,
            "mode": self.mode,
            "latency_ms": self.latency_ms,
            "audio_cached": self.audio_cached,
            "fallback": self.fallback,
        }


class Pipeline:
    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store
        self.tts = TTSService(settings)

    # ---- 对外入口 ----
    async def turn(
        self,
        *,
        audio: bytes | None,
        text: str | None,
        session_id: str,
    ) -> TurnResult:
        started = time.perf_counter()
        latency: dict[str, int] = {}
        profile = self.store.get_profile()

        transcript_ug = normalize_ug(text or "")
        transcript_zh: str | None = None
        fallback: str | None = None

        if audio:
            mark = time.perf_counter()
            try:
                asr = build_asr(self.settings)
                result = await asr.transcribe(audio)
                transcript_ug = normalize_ug(result.text)
                transcript_zh = result.gloss
            except (ASRError, Exception) as exc:  # noqa: BLE001 - 网络/鉴权都可能炸
                self.store.log_event("asr_error", {"error": str(exc)[:300]})
                latency["asr"] = _ms(mark)
                return await self._finalize(
                    session_id=session_id,
                    transcript_ug="",
                    transcript_zh=None,
                    reply_ug=None,
                    reply_zh=None,
                    category="error",
                    latency=latency,
                    started=started,
                    fallback="asr_error",
                )
            latency["asr"] = _ms(mark)

        if not transcript_ug:
            return await self._finalize(
                session_id=session_id,
                transcript_ug="",
                transcript_zh=None,
                reply_ug=None,
                reply_zh=None,
                category="unclear",
                latency=latency,
                started=started,
                fallback="empty_transcript",
            )

        if self.store.usage_today() >= self.settings.daily_limit:
            return await self._finalize(
                session_id=session_id,
                transcript_ug=transcript_ug,
                transcript_zh=transcript_zh,
                reply_ug=None,
                reply_zh=None,
                category="limit",
                latency=latency,
                started=started,
                fallback="quota",
            )

        if _is_weather_question(transcript_ug):
            mark = time.perf_counter()
            reply_ug, reply_zh = await self._weather_reply(profile)
            latency["weather"] = _ms(mark)
            category = "normal"
        else:
            verdict = safety.analyze(transcript_ug)
            category = verdict.category
            if verdict.category in {"emergency", "medical", "religion"}:
                reply_ug, reply_zh = persona.fallback(verdict.category)
                fallback = f"guardrail:{verdict.category}"
            else:
                mark = time.perf_counter()
                reply_ug, reply_zh = await self._generate(
                    transcript_ug, category=category, profile=profile, session_id=session_id
                )
                latency["llm"] = _ms(mark)

        return await self._finalize(
            session_id=session_id,
            transcript_ug=transcript_ug,
            transcript_zh=transcript_zh,
            reply_ug=reply_ug,
            reply_zh=reply_zh,
            category=category,
            latency=latency,
            started=started,
            fallback=fallback,
        )

    async def greeting(self) -> dict:
        profile = self.store.get_profile()
        data = await weather.current(profile.get("city") or self.settings.city)
        ug, zh = persona.greeting(_part_of_day(), data, profile)
        return {"text_ug": ug, "text_zh": zh, "weather": data}

    async def synthesize(self, text_ug: str, text_zh: str | None = None):
        """按当前配置挑一种能出声的方式；没有维语音色时，演示模式读中文对照。"""
        if self.settings.has_ug_voice():
            return await self.tts.speak(text_ug, "ug")
        if self.settings.resolved_mode() == "demo" and text_zh:
            return await self.tts.speak(text_zh, "zh")
        raise TTSError("no_voice")

    # ---- 生成 ----
    async def _generate(
        self,
        question: str,
        *,
        category: str,
        profile: dict,
        session_id: str,
    ) -> tuple[str, str | None]:
        arm = self.settings.arm
        llm = build_llm(self.settings)
        history = self.store.recent_messages(session_id, _HISTORY_LIMIT)

        try:
            if arm in {"B1", "B2"}:
                return await self._generate_pivot(question, profile, history, category)
            system = (
                _MINIMAL_PROMPT
                if arm == "A"
                else build_system_prompt(profile)
            )
            messages = [{"role": "system", "content": system}]
            for item in history:
                messages.append(
                    {
                        "role": "assistant" if item["role"] == "assistant" else "user",
                        "content": item["text"],
                    }
                )
            messages.append({"role": "user", "content": question})
            result = await llm.chat(messages)
            reply = normalize_ug(result.text)
            if category == "policy":
                reply = f"{reply} {persona.policy_disclaimer()}".strip()
            ok, reason = safety.post_check(reply)
            if not ok:
                self.store.log_failure(session_id, question, f"post_check:{reason}")
                ug, zh = persona.fallback("unclear")
                return ug, zh
            return reply, result.gloss
        except LLMError as exc:
            self.store.log_event("llm_error", {"error": str(exc)[:300]})
            ug, zh = persona.fallback("error")
            return ug, zh
        except Exception as exc:  # noqa: BLE001
            self.store.log_event("llm_error", {"error": str(exc)[:300]})
            ug, zh = persona.fallback("error")
            return ug, zh

    async def _generate_pivot(
        self,
        question: str,
        profile: dict,
        history: list[dict],
        category: str,
    ) -> tuple[str, str | None]:
        settings = self.settings
        translator = Translator(
            build_mt(settings) if settings.arm == "B1" else build_llm(settings),
            GLOSSARY,
        )
        zh_question = await translator.ug_to_zh(question)
        llm = build_llm(settings)
        messages = [{"role": "system", "content": _ZH_PROMPT}]
        for item in history[-4:]:
            messages.append(
                {
                    "role": "assistant" if item["role"] == "assistant" else "user",
                    "content": item["text"],
                }
            )
        messages.append({"role": "user", "content": zh_question})
        answer = await llm.chat(messages)
        answer_zh = (answer.text or "").strip()
        reply_ug = normalize_ug(await translator.zh_to_ug(answer_zh))
        if category == "policy":
            answer_zh = f"{answer_zh}（具体以官方为准）"
        ok, reason = safety.post_check(reply_ug)
        if not ok:
            self.store.log_failure(None, question, f"post_check:{reason}")
            ug, zh = persona.fallback("unclear")
            return ug, zh
        return reply_ug, answer_zh

    async def _weather_reply(self, profile: dict) -> tuple[str, str]:
        city = profile.get("city") or self.settings.city
        data = await weather.current(city)
        if not data:
            return (
                "ھازىرچە ھاۋا ئۇچۇرىنى تاپالمىدىم. كېيىنرەك يەنە سوراڭ.",
                "暂时查不到天气，等会儿再问一次。",
            )
        return persona.weather_line(data, profile, with_advice=True)

    # ---- 收尾 ----
    async def _finalize(
        self,
        *,
        session_id: str,
        transcript_ug: str,
        transcript_zh: str | None,
        reply_ug: str | None,
        reply_zh: str | None,
        category: str,
        latency: dict[str, int],
        started: float,
        fallback: str | None,
    ) -> TurnResult:
        if reply_ug is None:
            reply_ug, default_zh = persona.fallback(
                "limit" if fallback == "quota" else "error" if fallback in {"asr_error"} else "unclear"
            )
            reply_zh = reply_zh or default_zh

        sentences = split_sentences(reply_ug, limit=4)
        reply_ug = clamp_length(" ".join(sentences) if sentences else reply_ug, 260)
        if not is_ug(reply_ug):
            reply_ug, reply_zh = persona.fallback("unclear")

        # 语音不在这一跳同步合成：太慢会把整轮延迟拖到十几秒。
        # 前端拿到文字后单独请求 /api/tts，边显示边出声。
        latency["total"] = _ms(started)

        if transcript_ug:
            self.store.add_message(session_id, "user", transcript_ug)
            self.store.add_message(session_id, "assistant", reply_ug)
            self.store.bump_usage()

        return TurnResult(
            session_id=session_id,
            transcript_ug=transcript_ug,
            transcript_zh=transcript_zh,
            reply_ug=reply_ug,
            reply_zh=reply_zh,
            audio_url=None,
            audio_lang=None,
            category=category,
            arm=self.settings.arm,
            mode=self.settings.resolved_mode(),
            latency_ms=latency,
            audio_cached=False,
            fallback=fallback,
        )


def _is_weather_question(text: str) -> bool:
    return any(word in text for word in _WEATHER_WORDS)


def _part_of_day() -> str:
    hour = time.localtime().tm_hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 23:
        return "evening"
    return "night"


def _ms(mark: float) -> int:
    return int((time.perf_counter() - mark) * 1000)
