"""FastAPI 入口。

一个进程同时提供：API + PWA 静态文件 + 缓存的语音文件。
部署就一条命令，不需要 nginx。
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, config
from .config import DATA_DIR, STATIC_DIR, get_settings, update_settings
from .memory import Store
from .pipeline import Pipeline
from .providers.tts import TTSError

MAX_AUDIO_BYTES = 10 * 1024 * 1024


class AppState:
    def __init__(self) -> None:
        self.store = Store()
        self.settings = get_settings()
        self.pipeline = Pipeline(self.settings, self.store)

    def reload(self) -> None:
        self.settings = get_settings()
        self.pipeline = Pipeline(self.settings, self.store)


state = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Aynur", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def access_guard(request: Request, call_next):
    # 可选的访问口令：公开到公网时防止别人刷你的额度
    required = _access_token()
    if required and request.url.path.startswith("/api/"):
        if request.url.path == "/api/health":
            return await call_next(request)
        provided = request.headers.get("x-aynur-token", "")
        if provided != required:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


def _access_token() -> str:
    import os

    return (os.environ.get("AYNUR_ACCESS_TOKEN") or "").strip()


# ---------- 页面 ----------


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json"
    )


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


# ---------- API ----------


@app.get("/api/health")
async def health():
    settings = state.settings
    return {
        "ok": True,
        "version": __version__,
        "mode": settings.resolved_mode(),
        "arm": settings.arm,
        "asr": settings.resolved_asr(),
        "tts": settings.resolved_tts(),
        "ug_tts": settings.ug_tts(),
        "has_llm": bool(settings.llm_api_key),
        "has_ug_voice": settings.has_ug_voice(),
        "weather": settings.weather_enabled,
        "stats": state.store.stats(),
    }


@app.post("/api/turn")
async def turn(
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    session_id: str = Form("default"),
):
    session = _clean_session(session_id)
    payload = b""
    if audio is not None:
        payload = await audio.read()
        if not payload:
            raise HTTPException(status_code=400, detail="empty audio")
        if len(payload) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="audio too large")

    if not payload and not (text and text.strip()):
        raise HTTPException(status_code=400, detail="need audio or text")

    result = await state.pipeline.turn(
        audio=payload or None,
        text=(text or "").strip() or None,
        session_id=session,
    )
    return result.as_dict()


@app.post("/api/greeting")
async def greeting():
    return await state.pipeline.greeting()


@app.post("/api/tts")
async def tts(body: dict):
    """文字先出，语音后到。合成失败就返回 204，前端静默降级。"""
    text_ug = str(body.get("text_ug") or "")[:400]
    text_zh = str(body.get("text_zh") or "")[:400]
    if not text_ug and not text_zh:
        raise HTTPException(status_code=400, detail="empty text")
    try:
        result = await state.pipeline.synthesize(text_ug, text_zh)
    except TTSError:
        return Response(status_code=204)
    media = "audio/wav" if result.path.suffix == ".wav" else "audio/mpeg"
    return FileResponse(
        result.path,
        media_type=media,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/audio/{name}")
async def audio(name: str):
    safe = Path(name).name
    if safe != name or not safe:
        raise HTTPException(status_code=400, detail="bad name")
    path = DATA_DIR / "tts" / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    media = "audio/wav" if path.suffix == ".wav" else "audio/mpeg"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/feedback")
async def feedback(body: dict):
    session = _clean_session(str(body.get("session_id") or "default"))
    reason = str(body.get("reason") or "unsure")[:40]
    text = str(body.get("text") or "")[:500]
    state.store.log_failure(session, text, reason)
    state.store.add_message(session, "user", f"[feedback]{reason} {text}".strip())
    return {"ok": True}


@app.get("/api/settings")
async def read_settings():
    return state.settings.public()


@app.post("/api/settings")
async def write_settings(body: dict):
    allowed = {
        key
        for key in body
        if key
        in {
            "arm",
            "mode",
            "city",
            "user_title",
            "daily_limit",
            "weather_enabled",
            "llm_base_url",
            "llm_model",
            "llm_api_key",
            "mt_base_url",
            "mt_model",
            "mt_api_key",
            "tts_provider",
            "tts_voice_zh",
            "tts_voice_ug",
            "tts_url",
            "tts_api_key",
            "asr_provider",
        }
    }
    patch = {key: body[key] for key in allowed}
    state.settings = update_settings(patch)
    state.reload()
    return state.settings.public()


@app.get("/api/profile")
async def read_profile():
    return state.store.get_profile()


@app.post("/api/profile")
async def write_profile(body: dict):
    profile = state.store.set_profile(body)
    if body.get("city"):
        state.settings = update_settings({"city": body["city"]})
    return profile


@app.post("/api/profile/reset")
async def reset_profile():
    return state.store.clear_profile()


@app.get("/api/failures")
async def failures(limit: int = 50):
    return {"items": state.store.list_failures(limit)}


@app.get("/api/export")
async def export():
    payload = {
        "version": __version__,
        "settings": state.settings.public(),
        "profile": state.store.get_profile(),
        "failures": state.store.list_failures(200),
        "stats": state.store.stats(),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="aynur-export.json"'},
    )


def _clean_session(value: str) -> str:
    value = (value or "default").strip()
    safe = "".join(ch for ch in value if ch.isalnum() or ch in "-_")[:64]
    return safe or "default"


# 静态文件放最后，别遮住 /api
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=False)
