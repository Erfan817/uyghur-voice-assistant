"""用 XLS-R 维语模型转写 WAV（输出阿拉伯字母）。"""

from __future__ import annotations

import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

MODEL = "D:/Aynur/models/xlsr-uyghur"


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    processor = Wav2Vec2Processor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).to(device).eval()
    print(f"device={device}", flush=True)

    for path in sys.argv[1:]:
        audio, rate = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != 16000:
            audio = librosa.resample(audio, orig_sr=rate, target_sr=16000)
        inputs = processor(
            np.asarray(audio), sampling_rate=16000, return_tensors="pt"
        )
        started = __import__("time").perf_counter()
        with torch.inference_mode():
            logits = model(inputs.input_values.to(device)).logits
        elapsed = __import__("time").perf_counter() - started
        ids = torch.argmax(logits, dim=-1)
        text = processor.batch_decode(ids)[0]
        duration = len(audio) / 16000
        print(
            f"{path}\n  -> {text!r}\n  {elapsed:.2f}s for {duration:.2f}s "
            f"(rtf {elapsed / max(duration, 0.01):.2f})",
            flush=True,
        )


if __name__ == "__main__":
    main()
