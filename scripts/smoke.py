"""冒烟测试：真实打一遍服务端，检查链路是否通。

用法：
    .venv\\Scripts\\python.exe scripts\\smoke.py
产物写到 data/smoke.json，便于人工核对维语文本。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
OUT = Path("data") / "smoke.json"

QUESTIONS = [
    "بۈگۈن ھاۋا قانداق؟",
    "باشىم ئاغرىۋاتىدۇ، نېمە قىلسام بولىدۇ؟",
    "سىز كىم؟",
    "بالىلىرىم يوقلاپ كەلمىدى.",
    "دوختۇرخانىغا قانداق بارىمەن؟",
    "بىر ھېكايە ئوقۇپ بېرىڭ.",
]


def main() -> int:
    results: dict = {"base": BASE}
    with httpx.Client(base_url=BASE, timeout=90) as client:
        health = client.get("/api/health").json()
        results["health"] = health
        print("health:", json.dumps(health, ensure_ascii=False))

        greeting = client.post("/api/greeting").json()
        results["greeting"] = greeting
        print("greeting:", greeting.get("text_ug", "")[:80])

        turns = []
        for question in QUESTIONS:
            response = client.post(
                "/api/turn", data={"text": question, "session_id": "smoke"}
            )
            if response.status_code != 200:
                print("turn failed:", response.status_code, response.text[:200])
                return 1
            data = response.json()
            speech = client.post(
                "/api/tts",
                json={"text_ug": data["reply_ug"], "text_zh": data.get("reply_zh") or ""},
            )
            data["tts_status"] = speech.status_code
            data["tts_bytes"] = len(speech.content)
            turns.append(data)
            print(
                f"- {data['category']:<9} {data['latency_ms'].get('total', 0):>5}ms "
                f"tts={speech.status_code}/{len(speech.content)}B "
                f"{(data.get('reply_ug') or '')[:40]}"
            )
        results["turns"] = turns

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
