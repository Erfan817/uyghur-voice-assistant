"""TTS：把回复变成可以播放的音频。

现状（2026-10，重要）：
- 没有任何一家主流平台提供维语 TTS。qwen3-tts-uyghur / SLED-TTS 是开源权重，要自己主机。
- Edge TTS 只有中文，所以演示模式下读的是中文对照，不是维语。
- 一旦你有了维语 TTS（自建或采购），把 AYNUR_TTS_URL + AYNUR_TTS_VOICE_UG 配上，
  就会自动切到 http provider，合成维语。

所有合成结果按 (provider, voice, text) 哈希缓存，重复话术不重复花钱。
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import DATA_DIR, Settings


class TTSError(RuntimeError):
    pass


@dataclass
class TTSResult:
    path: Path
    mime: str
    lang: str
    cached: bool = False


def _digest(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:32]


class TTSService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache_dir = DATA_DIR / "tts"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def speak(self, text: str, lang: str) -> TTSResult:
        text = (text or "").strip()
        if not text:
            raise TTSError("空文本")

        candidates: list[tuple[str, str, str, str]] = []
        if lang == "ug":
            kind = self.settings.ug_tts()
            if kind == "xunfei":
                candidates.append(("xunfei", self.settings.xf_vcn, "mp3", "audio/mpeg"))
            elif kind == "http":
                candidates.append(("http", self.settings.tts_voice_ug, "mp3", "audio/mpeg"))
            else:
                raise TTSError("no_ug_voice")
        else:
            kind = self.settings.resolved_tts()
            if kind == "http":
                candidates.append(("http", self.settings.tts_voice_zh, "mp3", "audio/mpeg"))
            elif kind == "sapi":
                candidates.append(("sapi", "", "wav", "audio/wav"))
            elif kind == "mock":
                candidates.append(("mock", "", "wav", "audio/wav"))
            else:
                candidates.append(("edge", self.settings.tts_voice_zh, "mp3", "audio/mpeg"))
                # 网络抖的时候 edge 经常连不上，退回离线 SAPI，至少还有声音
                candidates.append(("sapi", "", "wav", "audio/wav"))

        last_error: Exception | None = None
        for provider, voice, ext, mime in candidates:
            key = _digest(provider, voice, text)
            target = self.cache_dir / f"{key}.{ext}"
            if target.exists() and target.stat().st_size > 0:
                return TTSResult(path=target, mime=mime, lang=lang, cached=True)
            try:
                audio = await self._synthesize(provider, text, voice)
            except TTSError as exc:
                last_error = exc
                continue
            if not audio:
                last_error = TTSError(f"{provider} 合成失败")
                continue
            target.write_bytes(audio)
            self._maybe_cleanup()
            return TTSResult(path=target, mime=mime, lang=lang)
        raise TTSError(str(last_error or "合成失败"))

    async def _synthesize(self, provider: str, text: str, voice: str) -> bytes:
        if provider == "edge":
            return await self._edge(text, voice)
        if provider == "sapi":
            return await asyncio.to_thread(self._sapi, text)
        if provider == "http":
            return await self._http(text, voice)
        if provider == "xunfei":
            return await self._xunfei(text)
        return self._tone()

    async def _xunfei(self, text: str) -> bytes:
        from .xfyun import XunfeiConfig, synthesize

        config = XunfeiConfig(
            app_id=self.settings.xf_app_id,
            api_key=self.settings.xf_api_key,
            api_secret=self.settings.xf_api_secret,
            vcn=self.settings.xf_vcn,
            speed=self.settings.xf_speed,
        )
        return await synthesize(config, text)

    async def _edge(self, text: str, voice: str, attempts: int = 2) -> bytes:
        try:
            import edge_tts
        except Exception as exc:  # pragma: no cover
            raise TTSError("edge-tts 未安装") from exc

        last: Exception | None = None
        for attempt in range(attempts):
            try:
                async def _run() -> bytes:
                    communicate = edge_tts.Communicate(text, voice)
                    chunks: list[bytes] = []
                    async for chunk in communicate.stream():
                        if chunk.get("type") == "audio" and chunk.get("data"):
                            chunks.append(chunk["data"])
                    return b"".join(chunks)

                data = await asyncio.wait_for(_run(), timeout=6.0)
                if data:
                    return data
            except Exception as exc:  # 网络抖动很常见，重试
                last = exc
            await asyncio.sleep(0.4 * (attempt + 1))
        raise TTSError(f"edge-tts 失败: {last}")

    def _sapi(self, text: str) -> bytes:
        """离线兜底：Windows 自带语音。只保证有声音，不保证好听。"""
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            raise TTSError("没有 powershell，SAPI 不可用")
        with tempfile.TemporaryDirectory(prefix="aynur-tts-") as tmp:
            tmp_path = Path(tmp)
            txt = tmp_path / "text.txt"
            wav = tmp_path / "out.wav"
            ps1 = tmp_path / "sapi.ps1"
            txt.write_text(text, encoding="utf-8")
            script = f"""Add-Type -AssemblyName System.Speech
$text = Get-Content -Raw -Encoding UTF8 -LiteralPath '{txt}'
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{ $s.SelectVoice('Microsoft Huihui Desktop') }} catch {{ }}
$s.Rate = -1
$s.SetOutputToWaveFile('{wav}')
$s.Speak($text)
$s.Dispose()
"""
            ps1.write_text(script, encoding="utf-8-sig")
            proc = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ps1),
                ],
                capture_output=True,
                timeout=40,
            )
            if not wav.exists() or wav.stat().st_size == 0:
                raise TTSError(f"SAPI 失败: {proc.stderr.decode('utf-8', 'ignore')[:200]}")
            return wav.read_bytes()

    async def _http(self, text: str, voice: str) -> bytes:
        headers = {}
        if self.settings.tts_api_key:
            headers["Authorization"] = f"Bearer {self.settings.tts_api_key}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.settings.tts_url,
                json={"text": text, "voice": voice, "format": "mp3"},
                headers=headers,
            )
        if resp.status_code >= 400:
            raise TTSError(f"TTS HTTP {resp.status_code}: {resp.text[:200]}")
        if not resp.content:
            raise TTSError("TTS 返回空音频")
        return resp.content

    def _tone(self) -> bytes:
        """最后的兜底：一声轻响，至少让界面有反馈。"""
        path = self.cache_dir / "_tone.wav"
        if path.exists():
            return path.read_bytes()
        rate = 16000
        frames = int(rate * 0.28)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            for i in range(frames):
                env = math.exp(-4 * i / frames)
                sample = int(6000 * env * math.sin(2 * math.pi * 660 * i / rate))
                handle.writeframesraw(struct.pack("<h", sample))
        return path.read_bytes()

    def _maybe_cleanup(self, keep: int = 400) -> None:
        files = sorted(self.cache_dir.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        cutoff = time.time() - 45 * 24 * 3600
        for index, path in enumerate(files):
            if index > keep or path.stat().st_mtime < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass
