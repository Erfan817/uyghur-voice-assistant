"""揭盲并汇总：每条链路的三项均分 + 正确率 + 分类别表现。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def _num(value: str) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("blind", help="填好分数的 blind.csv")
    parser.add_argument("key", help="blind-key.json")
    args = parser.parse_args()

    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    rows = list(csv.DictReader(Path(args.blind).open(encoding="utf-8")))

    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    per_category: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, int] = defaultdict(int)
    missing = 0

    for row in rows:
        meta = key.get(row["code"])
        if not meta:
            missing += 1
            continue
        arm = meta["arm"]
        counts[arm] += 1
        for field in ("score_understand", "score_natural", "score_persona", "correct"):
            value = _num(row.get(field, ""))
            if value is None:
                continue
            buckets[arm][field].append(value)
            if field == "score_understand":
                per_category[arm][meta["category"]].append(value)

    def mean(values: list[float]) -> str:
        return f"{sum(values) / len(values):.2f}" if values else "—"

    print(f"{'链路':<5}{'条数':>5}{'可懂':>8}{'自然':>8}{'人设':>8}{'正确率':>8}")
    for arm in sorted(buckets):
        data = buckets[arm]
        print(
            f"{arm:<5}{counts[arm]:>5}"
            f"{mean(data['score_understand']):>8}"
            f"{mean(data['score_natural']):>8}"
            f"{mean(data['score_persona']):>8}"
            f"{mean(data['correct']):>8}"
        )

    print("\n分类别可懂性：")
    for arm in sorted(per_category):
        parts = [f"{cat}={mean(vals)}" for cat, vals in sorted(per_category[arm].items())]
        print(f"  {arm}: " + "  ".join(parts))

    if missing:
        print(f"\n⚠️ {missing} 行在对照表里找不到编号，已跳过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
