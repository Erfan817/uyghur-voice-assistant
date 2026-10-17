"""临时诊断：直接打阿里云 ASR，打印原始 JSON。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.config import load_settings  # noqa: E402
from server.providers.asr import AliyunASR  # noqa: E402


async def main() -> None:
    settings = load_settings()
    asr = AliyunASR(
        settings.asr_appkey,
        settings.asr_access_key_id,
        settings.asr_access_key_secret,
        settings.asr_region,
    )
    token = await asr._get_token()
    print("token ok:", bool(token))

    for name in sys.argv[1:]:
        data = Path(name).read_bytes()
        params = {
            "appkey": asr.appkey,
            "format": "wav",
            "sample_rate": "16000",
            "enable_punctuation_prediction": "true",
            "enable_inverse_text_normalization": "true",
        }
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(
                asr.gateway,
                params=params,
                content=data,
                headers={"X-NLS-Token": token, "Content-Type": "application/octet-stream"},
            )
        print("==", name, resp.status_code)
        try:
            print(json.dumps(resp.json(), ensure_ascii=False))
        except Exception:
            print(resp.text[:500])


if __name__ == "__main__":
    asyncio.run(main())
