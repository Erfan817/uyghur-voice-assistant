"""下载 XLS-R 维语 ASR 模型（输出阿拉伯字母）。"""

from __future__ import annotations

import time

from huggingface_hub import snapshot_download

REPO = "mamatjan/xls-r-uyghur-cv18"
LOCAL = "D:/Aynur/models/xlsr-uyghur"

for attempt in range(5):
    try:
        print(f"[{REPO}] attempt {attempt + 1}", flush=True)
        path = snapshot_download(repo_id=REPO, local_dir=LOCAL, max_workers=2)
        print(f"done: {path}", flush=True)
        break
    except Exception as exc:  # noqa: BLE001
        print(f"failed: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(5 * (attempt + 1))
