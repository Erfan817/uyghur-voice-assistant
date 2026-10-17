"""用本地 TTS 合成一句话，存成 wav（给 ASR 做闭环测试）。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

text = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
out = Path(sys.argv[2])
resp = httpx.post(
    "http://127.0.0.1:8100/tts",
    json={"text": text, "max_seconds": 4},
    timeout=180,
)
resp.raise_for_status()
out.write_bytes(resp.content)
print(f"saved {out} ({len(resp.content)} bytes, rtf={resp.headers.get('x-rtf')})")
