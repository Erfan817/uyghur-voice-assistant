# 本地维语 TTS

在本机跑 `SLED-TTS-Uyghur-UAS-0.2B`（MIT，208M 参数），给 Aynur 当 `http` provider。

## 实测

| | |
|---|---|
| 显卡 | RTX 4060 Laptop 8 GB |
| 精度 | fp16 |
| RTF | **1.1–1.8**（3.5 秒音频约 3.9 秒合成；短句因为固定开销更高） |
| 显存 | 模型约 390 MB（fp16） |
| CPU | 也能跑，但会慢 5–10 倍，只建议离线批量 |

## 它需要一段参考音

这是 zero-shot 克隆模型：合成时必须给一段 **3–9 秒的参考录音 + 逐字转写**，
输出会沿用这段录音的音色。

正式用之前，请家人录一段并明确同意（模型卡要求：不得未经授权克隆他人声音）。

参考音要求：
- 安静房间、手机贴近、正常语速，8–10 秒
- 内容随意，最好包含日常用词（问好、天气、身体、家里）
- 逐字转写要和录音**完全一致**，转写错会明显影响音质

放好：
```
local_tts/ref/voice.wav    # 16k/24k/44.1k 都行，会自动重采样
local_tts/ref/voice.txt    # 与录音逐字对应的维吾尔文
```

## 启动

```powershell
# 1. 依赖（独立 venv，不动 Aynur 主服务）
uv venv .venv-tts --python 3.12
uv pip install --python .venv-tts\Scripts\python.exe torch --index-url https://download.pytorch.org/whl/cu126
uv pip install --python .venv-tts\Scripts\python.exe "transformers==4.47.0" librosa soundfile fastapi "uvicorn[standard]"

# 2. 模型（约 870 MB）
.venv\Scripts\python.exe scripts\download_tts_model.py

# 3. SLED 代码（模型卡要求把 training/sled.py 覆盖进 sled 包）
git clone https://github.com/ictnlp/SLED-TTS third_party/SLED-TTS
copy models\sled-uyghur\training\sled.py third_party\SLED-TTS\sled\sled.py

# 4. 起服务
.venv-tts\Scripts\python.exe -m uvicorn local_tts.server:app --host 127.0.0.1 --port 8100
```

然后在项目 `.env` 里：

```dotenv
AYNUR_TTS_PROVIDER=http
AYNUR_TTS_URL=http://127.0.0.1:8100/tts
AYNUR_TTS_VOICE_UG=local
```

## 注意

- 单次训练上限 20 秒；长回复要按句切分后再合成
- 参考音有噪声会被学进去
- 音色、韵律不保证；需要母语者试听把关
- Windows 上 `transformers` 必须是 4.47.0（模型代码按这个版本写的），所以单独建了 `.venv-tts`
