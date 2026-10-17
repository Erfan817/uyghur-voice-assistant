"""安全兜底：意图分类 + 输出后检。

原则：宁可说"我不太会"，不可说错。
分类器刻意做成高精度关键词表——维语关键词误判会让长辈莫名其妙被拒绝，
所以宁可漏判（交给 LLM 处理），也不要错判。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import has_chinese, normalize_for_match, uyghur_ratio

CATEGORIES = ("emergency", "medical", "religion", "policy")

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "emergency": (
        # 中文
        "胸痛", "胸口疼", "心口疼", "喘不上", "呼吸困难", "晕倒", "昏迷",
        "摔倒", "跌倒", "出血", "流血", "中风", "抽搐", "救护车", "急救",
        "中毒", "烫伤", "烧伤", "叫医生",
        # 维语
        "كۆكرەك", "نەپەس", "ھۇشىدىن", "يىقىلىپ", "قان چىق", "قان ئېق",
        "زەھەرلەن", "كۆيۈپ",
    ),
    "religion": (
        "礼拜", "斋月", "清真", "教法", "阿訇", "古兰经", "圣训",
        "哈拉尔", "猪肉", "犯忌", "祈祷", "罪过", "能不能吃",
        "ناماز", "روزا", "ھالال", "ھارام", "ئىمام", "قۇرئان", "پەتۋا", "گۇناھ",
    ),
    "medical": (
        "药", "吃药", "剂量", "副作用", "血压", "血糖", "发烧", "感冒",
        "头疼", "肚子疼", "不舒服", "看病", "医生", "打针", "输液", "手术",
        "生病", "疼",
        "دورا", "دوختۇر", "ئاغرى", "ئىسسىق", "زۇكام", "قان بېسىمى",
        "قان شېكىرى", "كېسەل",
    ),
    "policy": (
        "社保", "医保", "户口", "身份证", "补贴", "退休金", "养老金",
        "低保", "报销", "办证", "残疾证", "政策", "办事", "疫苗", "证明",
        "سۇغۇرتا", "كىملىك", "ياردەم پۇلى", "سىياسەت",
    ),
}

# 高精度排除：命中这些词时不算某类（避免"血压"和"出血"之类的误伤）
_NEGATIVE: dict[str, tuple[str, ...]] = {
    "emergency": ("قان بېسىمى", "血压"),
}

_ORDER = ("emergency", "religion", "medical", "policy")


@dataclass
class Verdict:
    category: str = "normal"  # normal | emergency | medical | religion | policy
    matched: list[str] = field(default_factory=list)
    blocked: bool = False  # True 表示不交给 LLM 自由发挥

    @property
    def is_normal(self) -> bool:
        return self.category == "normal"


def _hits(text: str, words: tuple[str, ...]) -> list[str]:
    found = []
    for word in words:
        if word in text:
            found.append(word)
    return found


def analyze(text: str) -> Verdict:
    raw = text or ""
    norm = normalize_for_match(raw)
    for category in _ORDER:
        words = _KEYWORDS[category]
        hits = _hits(raw, words) or _hits(norm, words)
        if not hits:
            continue
        negatives = _NEGATIVE.get(category, ())
        if negatives and all(word in raw or word in norm for word in negatives):
            continue
        blocked = category in {"emergency", "religion"}
        return Verdict(category=category, matched=hits, blocked=blocked)
    return Verdict()


_BAD_PATTERNS = (
    re.compile(r"\d+\s*(mg|毫克|克|ml|毫升|تال|دانە|قېتىم|رەت)", re.IGNORECASE),
    re.compile(r"(每天|一日|一次)\s*\d+\s*(片|粒|次)"),
    re.compile(r"(كۈنىگە|كۈندە)\s*\d+"),
)


def post_check(reply: str) -> tuple[bool, str]:
    """检查 LLM 输出能不能直接给长辈。

    返回 (是否可用, 理由)。不可用时上层改用模板。
    """
    if not reply or not reply.strip():
        return False, "empty"
    if has_chinese(reply) and uyghur_ratio(reply) < 0.5:
        return False, "not_uyghur"
    for pattern in _BAD_PATTERNS:
        if pattern.search(reply):
            return False, "dosage"
    if len(reply) > 800:
        return False, "too_long"
    return True, "ok"
