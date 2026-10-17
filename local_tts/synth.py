"""命令行合成一个样本，用来快速试听/测 RTF。

  .venv-tts\\Scripts\\python.exe local_tts\\synth.py ^
    --ref-audio local_tts\\ref\\voice.wav ^
    --ref-text-file local_tts\\ref\\voice.txt ^
    --text-file local_tts\\target_ug.txt ^
    --out data\\sample.wav
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import soundfile as sf

from .engine import SAMPLE_RATE, SledEngine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-audio", required=True)
    parser.add_argument("--ref-text")
    parser.add_argument("--ref-text-file")
    parser.add_argument("--text")
    parser.add_argument("--text-file")
    parser.add_argument("--out", default="local_tts/out.wav")
    parser.add_argument("--cfg", type=float, default=1.5)
    parser.add_argument("--max-seconds", type=float, default=8.0)
    args = parser.parse_args()

    ref_text = args.ref_text or ""
    if args.ref_text_file:
        ref_text = Path(args.ref_text_file).read_text(encoding="utf-8")
    text = args.text or ""
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    if not ref_text.strip() or not text.strip():
        parser.error("需要参考音转写和目标文本")

    started = time.perf_counter()
    engine = SledEngine()
    print(f"device={engine.device} loaded in {time.perf_counter() - started:.1f}s", flush=True)

    gen_started = time.perf_counter()
    audio = engine.synthesize(
        text, args.ref_audio, ref_text, cfg=args.cfg, max_seconds=args.max_seconds
    )
    elapsed = time.perf_counter() - gen_started
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, audio, SAMPLE_RATE)
    duration = len(audio) / SAMPLE_RATE
    print(
        f"gen {elapsed:.1f}s · audio {duration:.2f}s · RTF {elapsed / max(duration, 0.01):.2f}",
        flush=True,
    )
    print(f"saved: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
