"""把 run_ab 的结果做成盲评表。

生成的 blind.csv 里没有链路名，只有随机编号；对应关系单独写进 blind-key.json，
评分人填完再揭盲（summarize.py）。
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import secrets
from pathlib import Path

BLIND_COLUMNS = [
    "code",
    "item_id",
    "question",
    "reply",
    "score_understand",
    "score_natural",
    "score_persona",
    "correct",
    "notes",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", help="run_ab.py 产出的 jsonl")
    parser.add_argument("--seed", type=int, default=20261017)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    run_path = Path(args.run)
    rows = [json.loads(line) for line in run_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rng = random.Random(args.seed)

    entries = []
    key = {}
    for row in rows:
        code = secrets.token_hex(3).upper()
        key[code] = {"arm": row["arm"], "item_id": row["item_id"], "category": row["category"]}
        entries.append(
            {
                "code": code,
                "item_id": row["item_id"],
                "question": row["question"],
                "reply": row["reply"],
                "score_understand": "",
                "score_natural": "",
                "score_persona": "",
                "correct": "",
                "notes": "",
            }
        )

    # 同一题的不同链路不要挨着出现，减少顺序效应
    rng.shuffle(entries)

    out_dir = run_path.parent
    blind_path = Path(args.out) if args.out else out_dir / "blind.csv"
    key_path = out_dir / "blind-key.json"

    with blind_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BLIND_COLUMNS)
        writer.writeheader()
        writer.writerows(entries)

    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"盲评表：{blind_path}（{len(entries)} 条）")
    print(f"对照表：{key_path}（别给评分人看）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
