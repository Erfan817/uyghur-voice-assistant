"""本地维语 ASR 服务：POST /asr (multipart audio) -> {"text": ...}。

给 Aynur 当 `http` provider 用：
    AYNUR_ASR_PROVIDER=http
    AYNUR_ASR_URL=http://127.0.0.1:8200/asr

模型：mamatjan/xls-r-uyghur-cv18（XLS-R 300M，输出阿拉伯字母）。
"""

from __future__ import annotations

import io
import os
import sys
import threading
import time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

# Windows 控制台默认 GBK，打印维语会抛 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MODEL_DIR = Path(
    os.environ.get("AYNUR_ASR_MODEL") or Path(__file__).resolve().parent.parent / "models" / "xlsr-uyghur"
)

app = FastAPI(title="Aynur local ASR")
processor: Wav2Vec2Processor | None = None
model: Wav2Vec2ForCTC | None = None
device: torch.device | None = None
lock = threading.Lock()


@app.on_event("startup")
def _startup() -> None:
    global processor, model, device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    processor = Wav2Vec2Processor.from_pretrained(str(MODEL_DIR))
    model = Wav2Vec2ForCTC.from_pretrained(str(MODEL_DIR)).to(device).eval()
    print(f"ASR ready on {device}", flush=True)


@app.get("/health")
def health() -> dict:
    return {
        "ok": model is not None,
        "device": str(device) if device else None,
        "model": str(MODEL_DIR),
    }


@app.post("/asr")
def transcribe(audio: UploadFile = File(...)) -> dict:
    if model is None or processor is None or device is None:
        raise HTTPException(status_code=503, detail="not ready")

    data = audio.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio")

    try:
        waveform, rate = sf.read(io.BytesIO(data), dtype="float32")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"无法解码音频: {exc}") from exc

    if waveform.ndim > 1:
        waveform = waveform.mean(axis=1)
    if rate != 16000:
        waveform = librosa.resample(waveform, orig_sr=rate, target_sr=16000)

    started = time.perf_counter()
    inputs = processor(np.asarray(waveform), sampling_rate=16000, return_tensors="pt")
    with lock, torch.inference_mode():
        logits = model(inputs.input_values.to(device)).logits
    ids = torch.argmax(logits, dim=-1)
    text = processor.batch_decode(ids)[0].replace("[UNK]", "").strip()
    elapsed = time.perf_counter() - started
    duration = len(waveform) / 16000
    print(
        f"asr {elapsed:.2f}s for {duration:.2f}s (rtf {elapsed / max(duration, 0.01):.2f}): {text[:60]}",
        flush=True,
    )
    return {"text": text, "provider": "xlsr", "rtf": round(elapsed / max(duration, 0.01), 2)}
