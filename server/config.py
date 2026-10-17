"""运行配置。

优先级：默认值 < 环境变量 < data/settings.json（家人设置页写入）。

这里不解析 .env 文件，部署时用系统环境变量或启动脚本注入即可。
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AYNUR_DATA_DIR") or (ROOT / "data"))
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _s(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def _b(name: str, default: bool = True) -> bool:
    raw = _s(name, "")
    if not raw:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


@dataclass
class Settings:
    # 模式与链路
    mode: str = _s("AYNUR_MODE", "auto")  # auto | demo | live
    arm: str = _s("AYNUR_ARM", "A'")  # A | A' | B1 | B2

    # 对话 LLM（OpenAI 兼容）
    llm_base_url: str = _s("AYNUR_LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_api_key: str = _s("AYNUR_LLM_API_KEY")
    llm_model: str = _s("AYNUR_LLM_MODEL", "deepseek-chat")
    llm_temperature: float = float(_s("AYNUR_LLM_TEMPERATURE", "0.5"))

    # B1 臂专用翻译模型
    mt_base_url: str = _s("AYNUR_MT_BASE_URL", "https://api.siliconflow.cn/v1")
    mt_api_key: str = _s("AYNUR_MT_API_KEY")
    mt_model: str = _s("AYNUR_MT_MODEL", "tencent/Hunyuan-MT-7B")

    # ASR
    asr_provider: str = _s("AYNUR_ASR_PROVIDER", "auto")  # auto | mock | aliyun | http
    asr_appkey: str = _s("AYNUR_ASR_APPKEY")
    asr_access_key_id: str = _s("AYNUR_ASR_ACCESS_KEY_ID")
    asr_access_key_secret: str = _s("AYNUR_ASR_ACCESS_KEY_SECRET")
    asr_region: str = _s("AYNUR_ASR_REGION", "cn-shanghai")
    asr_url: str = _s("AYNUR_ASR_URL")
    asr_api_key: str = _s("AYNUR_ASR_API_KEY")

    # TTS
    tts_provider: str = _s("AYNUR_TTS_PROVIDER", "auto")  # auto | edge | sapi | http | mock
    tts_voice_zh: str = _s("AYNUR_TTS_VOICE_ZH", "zh-CN-XiaoxiaoNeural")
    tts_voice_ug: str = _s("AYNUR_TTS_VOICE_UG")
    tts_url: str = _s("AYNUR_TTS_URL")
    tts_api_key: str = _s("AYNUR_TTS_API_KEY")

    # 产品参数
    city: str = _s("AYNUR_CITY", "乌鲁木齐")
    user_title: str = _s("AYNUR_USER_TITLE", "ئاپا")
    user_name: str = _s("AYNUR_USER_NAME")
    daily_limit: int = int(_s("AYNUR_DAILY_LIMIT", "60"))
    weather_enabled: bool = _b("AYNUR_WEATHER", True)

    # ---- 派生判断 ----
    def resolved_mode(self) -> str:
        if self.mode in {"demo", "live"}:
            return self.mode
        return "live" if self.llm_api_key else "demo"

    @property
    def is_live(self) -> bool:
        return self.resolved_mode() == "live"

    def resolved_asr(self) -> str:
        if self.asr_provider != "auto":
            return self.asr_provider
        if self.asr_appkey and self.asr_access_key_id and self.asr_access_key_secret:
            return "aliyun"
        if self.asr_url:
            return "http"
        return "mock"

    def resolved_tts(self) -> str:
        if self.tts_provider != "auto":
            return self.tts_provider
        if self.tts_voice_ug and self.tts_url:
            return "http"
        if self.tts_provider == "auto" and not self.is_live:
            return "edge" if _edge_available() else "sapi"
        # live 模式下没有维语 TTS：返回 text-only，由上层决定不出音频
        if self.tts_voice_ug:
            return "http"
        return "edge" if _edge_available() else "sapi"

    def has_ug_voice(self) -> bool:
        return bool(self.tts_voice_ug and self.tts_url)

    def public(self) -> dict:
        """给前端和家人设置页看的配置（不含密钥）。"""
        data = asdict(self)
        for key in (
            "llm_api_key",
            "mt_api_key",
            "asr_access_key_id",
            "asr_access_key_secret",
            "asr_api_key",
            "tts_api_key",
        ):
            value = data.get(key) or ""
            data[key] = ("*" * 6 + value[-4:]) if value else ""
        data["resolved_mode"] = self.resolved_mode()
        data["resolved_asr"] = self.resolved_asr()
        data["resolved_tts"] = self.resolved_tts()
        data["has_llm"] = bool(self.llm_api_key)
        data["has_ug_voice"] = self.has_ug_voice()
        return data


def _edge_available() -> bool:
    try:
        import edge_tts  # noqa: F401

        return True
    except Exception:  # pragma: no cover - 环境问题
        return False


_SETTINGS_FILE = DATA_DIR / "settings.json"
_EDITABLE = {
    f.name
    for f in fields(Settings)
    if f.name not in {"llm_api_key", "mt_api_key", "asr_access_key_id", "asr_access_key_secret", "asr_api_key", "tts_api_key"}
}
_lock = threading.Lock()
_cache: Settings | None = None


def _apply_overrides(settings: Settings, data: dict) -> Settings:
    for key, value in data.items():
        if key not in _EDITABLE and key not in {
            "llm_api_key",
            "mt_api_key",
            "asr_access_key_id",
            "asr_access_key_secret",
            "asr_api_key",
            "tts_api_key",
        }:
            continue
        if not hasattr(settings, key):
            continue
        current = getattr(settings, key)
        try:
            if isinstance(current, bool):
                value = bool(value)
            elif isinstance(current, int) and not isinstance(value, bool):
                value = int(value)
            elif isinstance(current, float):
                value = float(value)
            elif isinstance(current, str):
                value = "" if value is None else str(value)
        except (TypeError, ValueError):
            continue
        setattr(settings, key, value)
    return settings


def load_settings() -> Settings:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        settings = Settings()
        if _SETTINGS_FILE.exists():
            try:
                data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                _apply_overrides(settings, data)
            except Exception:
                pass
        settings.arm = settings.arm if settings.arm in {"A", "A'", "B1", "B2"} else "A'"
        _cache = settings
        return settings


def get_settings() -> Settings:
    return load_settings()


def update_settings(patch: dict) -> Settings:
    global _cache
    settings = load_settings()
    _apply_overrides(settings, patch)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {f.name: getattr(settings, f.name) for f in fields(Settings)}
    _SETTINGS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache = settings
    return settings


def reset_cache() -> None:
    """给测试用：丢掉进程内缓存。"""
    global _cache
    with _lock:
        _cache = None
