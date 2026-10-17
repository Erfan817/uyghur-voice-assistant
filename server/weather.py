"""天气：给"打开问候"提供一句真实的天气摘要。

用 Open-Meteo（免费、无需 key）。注意：这里走 http 而不是 https——
某些网络环境下 TLS 会被中间设备重置，http 更稳；数据不敏感。
失败后回落到 wttr.in，再失败就返回 None，由上层省略天气句。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from .config import DATA_DIR

_GEOCODE = "http://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "http://api.open-meteo.com/v1/forecast"
_WTTR = "http://wttr.in/{city}?format=j1"

# wttr.in 用拉丁名更稳
_CITY_EN = {
    "乌鲁木齐": "Urumqi",
    "喀什": "Kashgar",
    "和田": "Hotan",
    "阿克苏": "Aksu",
    "库尔勒": "Korla",
    "伊宁": "Yining",
    "吐鲁番": "Turpan",
    "石河子": "Shihezi",
    "克拉玛依": "Karamay",
    "哈密": "Hami",
    "阿图什": "Artux",
    "博乐": "Bole",
    "塔城": "Tacheng",
    "阿勒泰": "Altay",
    "昌吉": "Changji",
    "北京": "Beijing",
    "上海": "Shanghai",
}

_STALE_FILE = DATA_DIR / "weather-cache.json"
_STALE_TTL = 12 * 3600

# WMO weather code -> (维语, 中文)
_CODES: dict[int, tuple[str, str]] = {
    0: ("قۇياشلىق", "晴"),
    1: ("ئاساسەن قۇياشلىق", "晴间多云"),
    2: ("ئازراق بۇلۇتلۇق", "多云"),
    3: ("بۇلۇتلۇق", "阴"),
    45: ("تۇمانلىق", "雾"),
    48: ("تۇمانلىق", "雾凇"),
    51: ("ئازراق يامغۇر", "小毛毛雨"),
    53: ("يامغۇر", "毛毛雨"),
    55: ("كۈچلۈك يامغۇر", "强毛毛雨"),
    56: ("توڭلىغان يامغۇر", "冻毛毛雨"),
    57: ("توڭلىغان يامغۇر", "冻毛毛雨"),
    61: ("ئازراق يامغۇر", "小雨"),
    63: ("يامغۇر", "中雨"),
    65: ("كۈچلۈك يامغۇر", "大雨"),
    66: ("توڭلىغان يامغۇر", "冻雨"),
    67: ("توڭلىغان يامغۇر", "冻雨"),
    71: ("ئازراق قار", "小雪"),
    73: ("قار", "中雪"),
    75: ("كۈچلۈك قار", "大雪"),
    77: ("قار", "雪粒"),
    80: ("ئازراق يامغۇر", "阵雨"),
    81: ("يامغۇر", "强阵雨"),
    82: ("كۈچلۈك يامغۇر", "暴雨"),
    85: ("قار", "阵雪"),
    86: ("كۈچلۈك قار", "强阵雪"),
    95: ("چاقماقلىق يامغۇر", "雷阵雨"),
    96: ("چاقماقلىق يامغۇر", "雷阵雨伴冰雹"),
    99: ("چاقماقلىق يامغۇر", "强雷暴冰雹"),
}

_TTL = 30 * 60
_TTL_MISS = 2 * 60
_cache: dict[str, tuple[float, dict | None]] = {}

# 常用城市直接给坐标，省掉一次地理编码（也避开中文城市名匹配不到的问题）。
CITY_COORDS: dict[str, tuple[float, float]] = {
    "乌鲁木齐": (43.83, 87.62),
    "喀什": (39.47, 75.99),
    "和田": (37.11, 79.92),
    "阿克苏": (41.17, 80.26),
    "库尔勒": (41.73, 86.15),
    "伊宁": (43.92, 81.32),
    "吐鲁番": (42.95, 89.19),
    "石河子": (44.31, 86.08),
    "克拉玛依": (45.58, 84.89),
    "哈密": (42.83, 93.51),
    "阿图什": (39.71, 76.17),
    "博乐": (44.90, 82.07),
    "塔城": (46.75, 82.99),
    "阿勒泰": (47.84, 88.14),
    "昌吉": (44.01, 87.30),
    "北京": (39.90, 116.40),
    "上海": (31.23, 121.47),
}


def _coords(city: str) -> tuple[float, float] | None:
    key = city.strip()
    for suffix in ("市", "地区", "自治州", "县", "区"):
        if key.endswith(suffix) and len(key) > len(suffix):
            key = key[: -len(suffix)]
    return CITY_COORDS.get(key)



def describe(code: int) -> tuple[str, str]:
    return _CODES.get(int(code), ("بۇلۇتلۇق", "多云"))


async def current(city: str) -> dict | None:
    city = (city or "").strip()
    if not city:
        return None
    now = time.time()
    cached = _cache.get(city)
    if cached:
        ttl = _TTL if cached[1] is not None else _TTL_MISS
        if now - cached[0] < ttl:
            return cached[1]

    result: dict | None = None
    # wttr 走 http，比 open-meteo 在这类网络下稳；open-meteo 作为备选
    for fetcher in (_wttr, _open_meteo):
        for attempt in range(2):
            try:
                result = await fetcher(city)
            except Exception:
                result = None
            if result is not None:
                break
            await asyncio.sleep(0.3)
        if result is not None:
            break

    if result is None:
        result = _load_stale(city)
    elif result.get("temp") is not None:
        _save_stale(city, result)

    _cache[city] = (now, result)
    return result


async def _open_meteo(city: str) -> dict | None:
    async with httpx.AsyncClient(timeout=3.5) as client:
        coords = _coords(city)
        name = city
        if coords is None:
            geo = await client.get(
                _GEOCODE,
                params={"name": city, "count": 1, "language": "zh", "format": "json"},
            )
            geo.raise_for_status()
            results = (geo.json() or {}).get("results") or []
            if not results:
                return None
            place = results[0]
            coords = (place["latitude"], place["longitude"])
            name = place.get("name") or city
        forecast = await client.get(
            _FORECAST,
            params={
                "latitude": coords[0],
                "longitude": coords[1],
                "current": "temperature_2m,weather_code",
                "timezone": "Asia/Shanghai",
            },
        )
        forecast.raise_for_status()
        data = forecast.json().get("current") or {}
        temp = data.get("temperature_2m")
        code = data.get("weather_code", 3)
        desc_ug, desc_zh = describe(code)
        return {
            "city": name,
            "temp": round(float(temp)) if temp is not None else None,
            "code": int(code),
            "desc_ug": desc_ug,
            "desc_zh": desc_zh,
            "source": "open-meteo",
        }


async def _wttr(city: str) -> dict | None:
    name = _CITY_EN.get(city, city)
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(_WTTR.format(city=name))
        resp.raise_for_status()
        data = resp.json()
        cur = (data.get("current_condition") or [{}])[0]
        temp = cur.get("temp_C")
        code = _wttr_code(cur)
        desc_ug, desc_zh = describe(code)
        return {
            "city": city,
            "temp": int(float(temp)) if temp is not None else None,
            "code": code,
            "desc_ug": desc_ug,
            "desc_zh": desc_zh,
            "source": "wttr.in",
        }


def _load_stale(city: str) -> dict | None:
    try:
        if not _STALE_FILE.exists():
            return None
        data = json.loads(_STALE_FILE.read_text(encoding="utf-8"))
        item = data.get(city)
        if not item or time.time() - item.get("ts", 0) > _STALE_TTL:
            return None
        payload = dict(item.get("data") or {})
        payload["stale"] = True
        return payload or None
    except Exception:
        return None


def _save_stale(city: str, data: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {}
        if _STALE_FILE.exists():
            payload = json.loads(_STALE_FILE.read_text(encoding="utf-8"))
        payload[city] = {"ts": time.time(), "data": data}
        _STALE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _wttr_code(cur: dict[str, Any]) -> int:
    text = " ".join(
        str(item.get("value", "")) for item in (cur.get("weatherDesc") or [])
    ).lower()
    if "snow" in text or "blizzard" in text:
        return 73
    if "rain" in text or "drizzle" in text or "shower" in text:
        return 63
    if "thunder" in text:
        return 95
    if "fog" in text or "mist" in text:
        return 45
    if "cloud" in text or "overcast" in text:
        return 3
    if "sun" in text or "clear" in text:
        return 0
    return 3
