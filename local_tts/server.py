"""本地维语 TTS 服务：POST /tts {text} -> audio/wav。

给 Aynur 服务端当 http provider 用：
    AYNUR_TTS_URL=http://127.0.0.1:8100/tts
    AYNUR_TTS_VOICE_UG=local

参考音和转写通过环境变量指定：
    AYNUR_TTS_REF_AUDIO=local_tts/ref/voice.wav
    AYNUR_TTS_REF_TEXT=...      （或 AYNUR_TTS_REF_TEXT_FILE=local_tts/ref/voice.txt）
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from .engine import ROOT, SAMPLE_RATE, SledEngine

REF_AUDIO = Path(os.environ.get("AYNUR_TTS_REF_AUDIO") or ROOT / "local_tts" / "ref" / "voice.wav")
REF_TEXT_FILE = Path(os.environ.get("AYNUR_TTS_REF_TEXT_FILE") or ROOT / "local_tts" / "ref" / "voice.txt")
REF_TEXT = os.environ.get("AYNUR_TTS_REF_TEXT", "").strip()

app = FastAPI(title="Aynur local TTS")
engine: SledEngine | None = None
ref_text = ""


@app.on_event("startup")
def _startup() -> None:
    global engine, ref_text
    engine = SledEngine()
    if REF_TEXT:
        ref_text = REF_TEXT
    elif REF_TEXT_FILE.exists():
        ref_text = REF_TEXT_FILE.read_text(encoding="utf-8").strip()
    print(f"TTS ready on {engine.device}, ref={REF_AUDIO} ({len(ref_text)} chars)", flush=True)


@app.get("/health")
def health() -> dict:
    return {
        "ok": engine is not None,
        "device": str(engine.device) if engine else None,
        "ref_audio": str(REF_AUDIO),
        "ref_ready": REF_AUDIO.exists() and bool(ref_text),
    }


@app.post("/tts")
def tts(body: dict) -> Response:
    if engine is None:
        raise HTTPException(status_code=503, detail="not ready")
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    if not REF_AUDIO.exists() or not ref_text:
        raise HTTPException(status_code=409, detail="reference audio/text not configured")

    started = time.perf_counter()
    audio = engine.synthesize(
        text,
        REF_AUDIO,
        ref_text,
        cfg=float(body.get("cfg") or 1.5),
        min_seconds=float(body.get("min_seconds") or 1.5),
        max_seconds=float(body.get("max_seconds") or max(3.0, len(text) / 12)),
    )
    buffer = io.BytesIO()
    sf.write(buffer, audio, SAMPLE_RATE, format="WAV")
    elapsed = time.perf_counter() - started
    duration = len(audio) / SAMPLE_RATE
    print(f"tts {elapsed:.2f}s for {duration:.2f}s audio (rtf {elapsed / max(duration, 0.01):.2f})", flush=True)
    return Response(
        content=buffer.getvalue(),
        media_type="audio/wav",
        headers={"X-RTF": f"{elapsed / max(duration, 0.01):.2f}"},
    )
