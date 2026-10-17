"""测试环境：把数据目录指到临时目录，避免污染本地 data/。"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="aynur-test-")
os.environ.setdefault("AYNUR_DATA_DIR", _TMP)
os.environ["AYNUR_MODE"] = "demo"
os.environ["AYNUR_ARM"] = "A'"
os.environ.pop("AYNUR_LLM_API_KEY", None)
