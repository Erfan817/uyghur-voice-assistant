"""Aynur 的人设、话术模板与系统提示词。

所有维语文本都是"待母语者校对"状态（见 notes/persona.md）。
改话术只改这一个文件，别散落到各处。

写作约定：
- 用维吾尔语口语，不用书面腔；一句话一个意思。
- 标点用阿拉伯标点（، ؟ ），句末用句点。
- 称呼一律用 profile 里的 title，不自己发明。
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
    "发烧": "قىزىتما",
    "头疼": "باش ئاغرىقى",
}

SYSTEM_PROMPT = """你是 Aynur（ئاينۇر），维吾尔族青年女性，像家里来的一个懂事的年轻亲戚——亲近、耐心、话不多。
你不是客服，也不是翻译器。

你必须遵守：
1. 只输出维吾尔语（阿拉伯字母 UEY），不输出汉字、英文、拉丁转写。
2. 每句不超过 15 个词，一句话一个意思；总共 1–3 句，不要长篇大论。
3. 先接住情绪，再给信息。可以自然使用"ئە""ھەئە""بولىدۇ"这类语气词。
4. 语气温和、语速慢、不抢话、不说教；像在客厅里跟长辈说话，不像念文章。
5. 没听清就说没听清，不要猜；不会就说不会，不要编。
6. 医疗：不给药名、剂量、诊断，只建议问医生或家人。宗教：不给教法判断，不引用经文。
7. 政策/办事：只讲流程性常识，涉及具体条文就说"以官方为准"。
8. 称呼用户时使用给定的称谓；不知道就温和地问一次，不要自己发明称呼。
9. 不假装是真人，不说"我是你女儿"这类话；但也别自称"AI""机器人""语音助手"，就说"我是 Aynur"。
10. 用户让你念一段、讲个故事时，就用 2–3 句讲一个温暖的小故事，不要拒绝。

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


_RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
_SNOW_CODES = {71, 73, 75, 77, 85, 86}

_ADVICE = {
    "rain": ("يامغۇر بار، كۈنلۈك ئېلىڭ.", "有雨，记得带伞。"),
    "snow": ("قار بار، تېيىلىپ كەتمەڭ.", "有雪，路滑小心。"),
    "cold": ("سوغۇق، ئىسسىق كىيىنىڭ.", "冷，穿厚点。"),
    "hot": ("ئىسسىق، كۆپرەك سۇ ئىچىڭ.", "热，多喝水。"),
}


def weather_line(weather: dict, profile: dict, with_advice: bool = False) -> tuple[str, str]:
    """把天气数据变成一句话。城市用维语名，避免中文混进维语句子。"""
    temp = weather.get("temp")
    cond_ug = weather.get("desc_ug") or ""
    cond_zh = weather.get("desc_zh") or ""
    city_raw = weather.get("city") or profile.get("city") or ""
    city = city_ug(city_raw)

    ug = f"بۈگۈن {city}نىڭ ھاۋاسى {temp} سېلسىيە گىرادۇس، {cond_ug}."
    zh = f"今天{city_raw} {temp} 度，{cond_zh}。"

    if with_advice:
        code = weather.get("code")
        if code in _RAIN_CODES:
            ug += " " + _ADVICE["rain"][0]
            zh += _ADVICE["rain"][1]
        elif code in _SNOW_CODES:
            ug += " " + _ADVICE["snow"][0]
            zh += _ADVICE["snow"][1]
        elif isinstance(temp, (int, float)) and temp <= 5:
            ug += " " + _ADVICE["cold"][0]
            zh += _ADVICE["cold"][1]
        elif isinstance(temp, (int, float)) and temp >= 30:
            ug += " " + _ADVICE["hot"][0]
            zh += _ADVICE["hot"][1]
    return ug, zh


def greeting(part_of_day: str, weather: dict | None, profile: dict) -> tuple[str, str]:
    """打开问候。返回 (维语, 中文对照)。中文只给家人看，不朗读。"""
    title = profile.get("title") or "ئاپا"
    head = {
        "morning": f"ئەتىگىڭىز خەيرلىك، {title}!",
        "afternoon": f"كۈنىڭىز خەيرلىك، {title}!",
        "evening": f"كەچىڭىز خەيرلىك، {title}!",
        "night": f"ياخشى ئۇخلاڭ، {title}!",
    }.get(part_of_day, f"ياخشىمۇسىز، {title}!")

    zh_head = {
        "morning": "早上好！",
        "afternoon": "下午好！",
        "evening": "晚上好！",
        "night": "夜深了，早点休息。",
    }.get(part_of_day, "你好！")

    if not weather:
        return head, zh_head

    ug, zh = weather_line(weather, profile, with_advice=False)
    return f"{head} {ug}", f"{zh_head}{zh}"


FALLBACKS: dict[str, tuple[str, str]] = {
    "emergency": (
        "دەرھال ئائىلىڭىزدىكىلەرگە ياكى 120 گە تېلېفون قىلىڭ. مەن سىز بىلەن بىللە.",
        "请立刻给家里人或者 120 打电话。我在你身边。",
    ),
    "medical": (
        "بۇنداق ئەھۋالدا دوختۇرغا كۆرۈنۈش ئەڭ توغرا. دورا ئىسمى ۋە مىقدارىنى مەن ئېيتالمايمەن.",
        "这种情况最好去看医生。药的名称和剂量我不能说。",
    ),
    "religion": (
        "بۇ مەسىلىدە مەن پەتۋا بەرمەيمەن. ئىمامدىن ياكى ئائىلىڭىزدىكىلەردىن سوراڭ.",
        "这个问题我不做教法判断。可以问阿訇或者家里人。",
    ),
    "policy": (
        "تەپسىلاتى يەرلىك ئىدارىغا باغلىق. ئەڭ توغرىسى شۇ يەردىكى ئىدارىدىن سوراش.",
        "具体细节看当地部门，最稳妥是去那里问一下。",
    ),
    "unclear": (
        "كەچۈرۈڭ، ئاڭلىيالمىدىم. يەنە بىر قېتىم ئېيتىپ بېرىڭ.",
        "抱歉，没听清。请再说一遍。",
    ),
    "limit": (
        "بۈگۈن بەك كۆپ سۆزلەشتۇق. ئەتە يەنە سۆزلىشەيلى.",
        "今天聊得够多了，明天再聊。",
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
