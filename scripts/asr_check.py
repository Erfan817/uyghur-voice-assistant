"""验证 ASR 配置：读一个 WAV，打印转写、耗时和（可选）WER。

用法：
    .venv\\Scripts\\python.exe scripts\\asr_check.py --audio data\\local_tts_reply.wav
    .venv\\Scripts\\python.exe scripts\\asr_check.py --audio x.wav --ref-file ref.txt

没有配置 key 时会走 mock，并提示需要哪些变量。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.config import load_settings  # noqa: E402
from server.normalize import cer, normalize_ug, wer  # noqa: E402
from server.providers.asr import ASRError, build_asr  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--ref")
    parser.add_argument("--ref-file")
    args = parser.parse_args()

    settings = load_settings()
    kind = settings.resolved_asr()
    print(f"provider: {kind}")
    if kind == "mock":
        print(
            "未配置真实 ASR，会在演示脚本里轮播。需要：\n"
            "  AYNUR_ASR_APPKEY / AYNUR_ASR_ACCESS_KEY_ID / AYNUR_ASR_ACCESS_KEY_SECRET",
            file=sys.stderr,
        )

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"找不到音频：{audio_path}", file=sys.stderr)
        return 2

    reference = args.ref or ""
    if args.ref_file:
        reference = Path(args.ref_file).read_text(encoding="utf-8").strip()

    asr = build_asr(settings)
    started = time.perf_counter()
    try:
        result = asyncio.run(asr.transcribe(audio_path.read_bytes(), audio_path.name))
    except ASRError as exc:
        print(f"ASR 失败：{exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    print(f"耗时: {elapsed * 1000:.0f} ms")
    print(f"转写: {result.text}")
    if reference:
        print(f"参考: {normalize_ug(reference)}")
        print(f"WER: {wer(reference, result.text):.3f}  CER: {cer(reference, result.text):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
