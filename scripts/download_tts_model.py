"""下载 SLED-TTS 维语模型和 Encodec 编解码器。

HF 在这个网络下不稳定，huggingface_hub 自带重试和断点续传，放后台跑。
用法：.venv\\Scripts\\python.exe scripts\\download_tts_model.py
"""

from __future__ import annotations

import time

from huggingface_hub import snapshot_download

TARGETS = [
    ("ElgekAI/SLED-TTS-Uyghur-UAS-0.2B", "D:/Aynur/models/sled-uyghur"),
    ("facebook/encodec_24khz", "D:/Aynur/models/encodec_24khz"),
]


def main() -> None:
    for repo, local in TARGETS:
        for attempt in range(5):
            try:
                print(f"[{repo}] attempt {attempt + 1} -> {local}", flush=True)
                path = snapshot_download(
                    repo_id=repo,
                    local_dir=local,
                    resume_download=True,
                    max_workers=2,
                )
                print(f"[{repo}] done: {path}", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[{repo}] failed: {type(exc).__name__}: {exc}", flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            print(f"[{repo}] gave up", flush=True)


if __name__ == "__main__":
    main()
