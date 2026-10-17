"""Aynur 的人设、话术模板与系统提示词。

所有维语文本都是"待母语者校对"状态（见 notes/persona.md）。
改话术只改这一个文件，别散落到各处。
"""

from __future__ import annotations

from typing import Iterable

TITLE_CHOICES = ["ئاپا", "ئانا", "ئاكا", "ئاچا", "بوۋا", "موم", "ھەدىيە"]

# 城市名的维语写法。中文名混进维语句子里会很难看，也影响 TTS。
CITY_UG: dict[str, str] = {
    "乌鲁木齐": "ئۈرۈمچى",
    "喀什": "قەشقەر",
    "和田": "خوتەن",
    "阿克苏": "ئاقسۇ",
    "库尔勒": "كورلا",
    "伊宁": "غۇلجا",
    "吐鲁番": "تۇرپان",
    "石河子": "شىخەنزە",
    "克拉玛依": "قاراماي",
    "哈密": "قۇمۇل",
    "阿图什": "ئاتۇش",
    "博乐": "بورتالا",
    "塔城": "تارباغاتاي",
    "阿勒泰": "ئالتاي",
    "昌吉": "سانجى",
    "北京": "بېيجىڭ",
    "上海": "شاڭخەي",
}


def city_ug(name: str) -> str:
    key = (name or "").strip()
    for suffix in ("市", "地区", "自治州", "县", "区"):
        if key.endswith(suffix) and len(key) > len(suffix):
            key = key[: -len(suffix)]
    return CITY_UG.get(key, name)


# 术语表：中文 -> 维语。进提示词，也用于译前替换。
GLOSSARY: dict[str, str] = {
    "血压": "قان بېسىمى",
    "血糖": "قان شېكىرى",
    "医院": "دوختۇرخانا",
    "医生": "دوختۇر",
    "药": "دورا",
    "天气": "ھاۋا",
    "社保": "ئىجتىمائىي سۇغۇرتا",
    "微信": "ۋېيشىن",
    "身份证": "كىملىك",
    "馕": "نان",
    "茶": "چاي",
    "感冒": "زۇكام",
    "发烧": "ئىسسىق",
    "头疼": "باش ئاغرىقى",
}

SYSTEM_PROMPT = """你是 Aynur（ئاينۇر），维吾尔族中年女性，是用户家里的"大姐/姑姑"式家人，不是客服，不是翻译器。

你必须遵守：
1. 只输出维吾尔语（阿拉伯字母 UEY），不输出汉字、英文、拉丁转写。
2. 每句不超过 15 个词，一句话一个意思；总共 1–3 句，不要长篇大论。
3. 先接住情绪，再给信息。可以自然使用"ئە""ھەئە""بولىدۇ"这类语气词。
4. 语气温和、语速感的短句、不抢话、不说教。
5. 没听清就说没听清，不要猜；不会就说不会，不要编。
6. 医疗：不给药名、剂量、诊断，只建议问医生或家人。宗教：不给教法判断，不引用经文。
7. 政策/办事：只讲流程性常识，涉及具体条文就说"以官方为准"。
8. 称呼用户时使用给定的称谓；不知道就温和地问一次，不要自己发明称呼。
9. 不假装是真人，不说"我是你女儿"这类话。

用户信息：
- 称呼：{title}
- 年龄：{age}
- 城市：{city}
- 健康注意：{health}
- 家里人：{family}

术语对照（必须优先使用）：
{glossary}

只输出回答正文，不要解释，不要加引号。"""


def build_system_prompt(profile: dict | None = None) -> str:
    profile = profile or {}
    glossary_lines = "\n".join(f"- {zh} = {ug}" for zh, ug in GLOSSARY.items())
    return SYSTEM_PROMPT.format(
        title=profile.get("title") or "ئاپا",
        age=profile.get("age") or "未填写",
        city=profile.get("city") or "乌鲁木齐",
        health=profile.get("health") or "无",
        family=profile.get("family") or "未填写",
        glossary=glossary_lines,
    )


def greeting(part_of_day: str, weather: dict | None, profile: dict) -> tuple[str, str]:
    """打开问候。返回 (维语, 中文对照)。中文只给家人看，不朗读。"""
    title = profile.get("title") or "ئاپا"
    head = {
        "morning": f"خەيرلىك سەھەر، {title}!",
        "afternoon": f"خەيرلىك كۈن، {title}!",
        "evening": f"خەيرلىك كەچ، {title}!",
        "night": f"خەيرلىك كېچە، {title}!",
    }.get(part_of_day, f"ياخشىمۇسىز، {title}!")

    zh_head = {
        "morning": "早上好！",
        "afternoon": "下午好！",
        "evening": "晚上好！",
        "night": "夜深了，早点休息。",
    }.get(part_of_day, "你好！")

    if not weather:
        return head, zh_head

    temp = weather.get("temp")
    cond_ug = weather.get("desc_ug") or ""
    cond_zh = weather.get("desc_zh") or ""
    city_raw = weather.get("city") or profile.get("city") or ""
    city = city_ug(city_raw)
    city_zh = city_raw

    sentence_ug = f"بۈگۈن {city} ھاۋاسى {temp} سېلسىيە گىرادۇس، {cond_ug}."
    sentence_zh = f"今天{city_zh} {temp} 度，{cond_zh}。"

    return f"{head} {sentence_ug}", f"{zh_head}{sentence_zh}"


FALLBACKS: dict[str, tuple[str, str]] = {
    "emergency": (
        "دەرھال ئائىلىڭىزدىكىلەرنى ياكى 120 نى تېلېفون قىلىڭ. مەن شۇ يەردە ساقلاپ تۇرىمەن.",
        "请立刻给家里人打电话，或者打 120。我在这里等你。",
    ),
    "medical": (
        "بۇنداق ئەھۋالدا دوختۇردىن سوراش ئەڭ توغرا. مەن دورا ئىسمى ياكى مىقدارىنى ئېيتالمايمەن.",
        "这种情况最好问医生。药的名称和剂量我不能说。",
    ),
    "religion": (
        "بۇ مەسىلىدە مەن پەتۋا بەرمەيمەن. ئىمام ياكى ئائىلىڭىزدىكىلەردىن سوراپ باقاي.",
        "这个我不做教法判断。可以问阿訇或家里人。",
    ),
    "policy": (
        "تەپسىلاتى يەرلىك ئىدارىغا باغلىق، ئەڭ توغرىسى ئىدارىدىن سوراش.",
        "具体细节看当地部门，最稳妥是去问一下。",
    ),
    "unclear": (
        "كەچۈرۈڭ، ئاڭلىيالمىدىم. يەنە بىر قېتىم ئېيتىڭ.",
        "抱歉，没听清，再说一遍。",
    ),
    "limit": (
        "بۈگۈن بەك كۆپ سۆزلەشتۇق. ئەتە يەنە سۆزلىشەيلى.",
        "今天聊得够多了，明天再来。",
    ),
    "error": (
        "ھازىرچە ئۇلانالمايۋاتىمەن. سەل تۇرۇپ يەنە سىناڭ.",
        "现在连不上，等会儿再试。",
    ),
}


def fallback(category: str) -> tuple[str, str]:
    return FALLBACKS.get(category, FALLBACKS["unclear"])


def policy_disclaimer() -> str:
    return "تەپسىلاتى رەسمىي ئورۇنغا باغلىق."


def join_reply(sentences: Iterable[str]) -> str:
    return " ".join(s.strip() for s in sentences if s and s.strip())
