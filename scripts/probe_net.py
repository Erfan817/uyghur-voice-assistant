"""网络探针：部署前确认天气/语音相关端点通不通。"""

from __future__ import annotations

import httpx


def check(name: str, method: str, url: str, **kwargs) -> None:
    try:
        response = httpx.request(method, url, timeout=10.0, **kwargs)
        print(f"[ok]   {name}: {response.status_code} {response.text[:120]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[fail] {name}: {type(exc).__name__}: {exc}")


def main() -> None:
    check(
        "geocode-http",
        "GET",
        "http://geocoding-api.open-meteo.com/v1/search",
        params={"name": "Urumqi", "count": 1, "language": "zh", "format": "json"},
    )
    check(
        "geocode-https",
        "GET",
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": "Urumqi", "count": 1, "language": "zh", "format": "json"},
    )
    check(
        "forecast-http",
        "GET",
        "http://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 43.83,
            "longitude": 87.62,
            "current": "temperature_2m,weather_code",
        },
    )
    check("wttr", "GET", "https://wttr.in/Urumqi?format=j1")
    check("deepseek", "GET", "https://api.deepseek.com/v1/models")
    check("siliconflow", "GET", "https://api.siliconflow.cn/v1/models")


if __name__ == "__main__":
    main()
