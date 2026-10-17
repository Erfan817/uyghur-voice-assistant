"""维吾尔语文本规范化。

ASR 的输出、人工转写、术语表、TTS 输入必须走同一套规则，否则 WER 和缓存全部不可比。
这里的规范化是"保守版"：只做确定等价的字形统一，不改写拼写。
"""

from __future__ import annotations

import re
import unicodedata

# 阿拉伯字母区（含补充区），用于判断"这是不是维语"
_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)

# 数字：阿拉伯-印度数字与波斯数字统一成 ASCII
_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩" "۰۱۲۳۴۵۶۷۸۹",
    "0123456789" "0123456789",
)

# 标点统一（只统一含义明确的几个）。展示用阿拉伯标点，比较时再全部剥掉。
_PUNCT = {
    "；": "؛",
    ";": "؛",
    "?": "؟",
    "۔": ".",
    "٫": ".",
    "٬": ",",
    ",": "،",
    "«": '"',
    "»": '"',
}

# 字母变体：把波斯/阿拉伯常见的"同形不同码"统一到一个码位。
# 维语 UEY 里 k 用 U+0643、h 用 U+06BE，但 OCR / 输入法常给出变体。
_LETTERS = {
    "\u06a9": "\u0643",  # ک -> ك
    "\u0647": "\u06be",  # ه -> ھ
}

# 要彻底删掉的不可见字符
_INVISIBLE = {
    "\u0640",  # tatweel
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\u200e",  # LRM
    "\u200f",  # RLM
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\ufeff",
}

_HARAKAT = re.compile("[\u064b-\u0652\u0670]")
_SPACES = re.compile(r"[ \t\u00a0]+")
_NEWLINES = re.compile(r"\s*\n\s*")
_STRIP_PUNCT = re.compile(
    r"[!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~،؛؟۔٬٫«»‹›…—–]"
)

def normalize_ug(text: str) -> str:
    """用于展示与缓存的规范化。"""
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = out.translate(_DIGITS)
    for src, dst in _PUNCT.items():
        out = out.replace(src, dst)
    for src, dst in _LETTERS.items():
        out = out.replace(src, dst)
    out = _HARAKAT.sub("", out)
    for ch in _INVISIBLE:
        out = out.replace(ch, "")
    out = _NEWLINES.sub("\n", out)
    out = _SPACES.sub(" ", out)
    out = "\n".join(line.strip() for line in out.split("\n"))
    return out.strip()


def normalize_for_match(text: str) -> str:
    """用于比较（WER、缓存键、术语表匹配）：去标点、压空格、统一大小写。"""
    out = normalize_ug(text).lower()
    out = _STRIP_PUNCT.sub(" ", out)
    out = _SPACES.sub(" ", out)
    return out.strip()


def is_ug(text: str) -> bool:
    """粗略判断文本是否含维吾尔文（阿拉伯字母）。"""
    if not text:
        return False
    hits = 0
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _ARABIC_RANGES):
            hits += 1
    return total > 0 and hits / total >= 0.4


def has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def uyghur_ratio(text: str) -> float:
    if not text:
        return 0.0
    hits = sum(
        1
        for ch in text
        if any(lo <= ord(ch) <= hi for lo, hi in _ARABIC_RANGES)
    )
    letters = sum(1 for ch in text if not ch.isspace())
    return hits / letters if letters else 0.0


def _levenshtein(ref: list[str], hyp: list[str]) -> int:
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)
    prev = list(range(len(hyp) + 1))
    for i, ref_token in enumerate(ref, start=1):
        cur = [i]
        for j, hyp_token in enumerate(hyp, start=1):
            cost = 0 if ref_token == hyp_token else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    """词错误率。参考文本为空时返回 0（该条不计分）。"""
    ref = normalize_for_match(reference).split()
    hyp = normalize_for_match(hypothesis).split()
    if not ref:
        return 0.0
    return _levenshtein(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    """字错误率，对维语这种连写多的语言比 WER 稳一点。"""
    ref = list(normalize_for_match(reference).replace(" ", ""))
    hyp = list(normalize_for_match(hypothesis).replace(" ", ""))
    if not ref:
        return 0.0
    return _levenshtein(ref, hyp) / len(ref)


def split_sentences(text: str, limit: int = 3) -> list[str]:
    """按句末标点切句，最多保留 limit 句。"""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", normalize_ug(text))
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []
    if len(parts) > limit:
        parts = parts[:limit]
    return parts


def clamp_length(text: str, max_chars: int = 220) -> str:
    """硬截断，防止模型跑飞后 TTS 合成一长段。尽量在句末切。"""
    text = normalize_ug(text)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for mark in (".", "?", "!", "\n"):
        pos = cut.rfind(mark)
        if pos > max_chars * 0.5:
            return cut[: pos + 1].strip()
    return cut.strip()
