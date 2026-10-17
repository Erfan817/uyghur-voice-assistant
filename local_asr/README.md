# 本地维语 ASR

用 `mamatjan/xls-r-uyghur-cv18`（XLS-R 300M，Common Voice 18 微调）做维语听写，**输出阿拉伯字母**。

## 实测

| | |
|---|---|
| 显卡 | RTX 4060，fp32 |
| RTF | **0.13**（3.48 秒音频 0.45 秒识别） |
| 显存 | 约 1.2 GB |
| 模型 | 1.2 GB safetensors |

## 为什么不用阿里云

| | 本地 XLS-R | 阿里云 ISI |
|---|---|---|
| 输出 | 阿拉伯字母 | **拉丁转写**（`Bvgvn Hawa yahxi`） |
| 延迟 | 0.45 秒 | 2.8 秒 |
| 成本 | 0 | 按量计费 |
| 实时性 | 够用 | 更快，但脚本不对 |

阿里云的代码和密钥都留着，`.env` 里把 `AYNUR_ASR_PROVIDER` 改成 `aliyun` 就切回去。

## 启动

```powershell
.venv-tts\Scripts\python.exe -m uvicorn local_asr.server:app --host 127.0.0.1 --port 8200
```

## 接入 Aynur

```dotenv
AYNUR_ASR_PROVIDER=http
AYNUR_ASR_URL=http://127.0.0.1:8200/asr
```

服务端走现成的 `http` provider：multipart 上传 `audio`，读回 `{"text": ...}`。

## 已知问题

- 用合成音频测时，`ھاۋا` 会被认成 `ناۋۋا`——参考音是英文样本，口音重；真实人声还没测
- 输出没有标点，靠 LLM 和后处理补
- 模型基于朗读语料（Common Voice），方言和口语可能更差
