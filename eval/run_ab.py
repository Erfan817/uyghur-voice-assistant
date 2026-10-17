"""跑 A / A' / B1 / B2 四条链路，产出可盲评的文本结果。

这是 M0 的 T0 阶段（纯文本）：不录音、不合成语音，只比"生成出来的维语好不好"。
文本都过不了关的链路，不要浪费时间去合成音频。

用法：
    .venv\\Scripts\\python.exe eval\\run_ab.py --arms "A,A',B1,B2" --limit 20
    .venv\\Scripts\\python.exe eval\\blind.py data\\eval\\run-xxxx.jsonl
    .venv\\Scripts\\python.exe eval\\summarize.py data\\eval\\blind.csv data\\eval\\blind-key.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.config import DATA_DIR, load_settings  # noqa: E402
from server.memory import Store  # noqa: E402
from server.pipeline import Pipeline  # noqa: E402


def read_questions(path: Path, limit: int | None) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit] if limit else rows


async def run(arms: list[str], limit: int | None) -> Path:
    settings = load_settings()
    settings.daily_limit = 10**6  # 评测不受每日上限限制
    store = Store(DATA_DIR / "eval.db")
    pipeline = Pipeline(settings, store)

    questions = read_questions(ROOT / "corpus" / "questions.csv", limit)
    out_dir = DATA_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"run-{stamp}.jsonl"

    with out_path.open("w", encoding="utf-8") as handle:
        for arm in arms:
            settings.arm = arm
            for item in questions:
                session = f"eval-{arm}-{item['id']}-{stamp}"
                result = await pipeline.turn(
                    audio=None, text=item["text_ug"], session_id=session
                )
                record = {
                    "item_id": item["id"],
                    "category": item["category"],
                    "arm": arm,
                    "question": item["text_ug"],
                    "reply": result.reply_ug,
                    "reply_zh": result.reply_zh,
                    "latency_ms": result.latency_ms.get("total"),
                    "fallback": result.fallback,
                    "safety_category": result.category,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"{arm:<3} {item['id']} {record['latency_ms']:>5}ms  {result.reply_ug[:40]}")
    print(f"\n结果：{out_path}")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", default="A,A',B1,B2")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    asyncio.run(run(arms, args.limit or None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
