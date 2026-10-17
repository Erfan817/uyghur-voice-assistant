# 规划文档索引

本目录存放 Aynur 项目规划期的设计讨论与决策记录（2026-10-17 起）。
代码已经跑到 v0.1，产品说明见仓库根目录的 [README](../README.md)。

| 文件 | 内容 |
|---|---|
| [decisions.md](decisions.md) | 已定决策（D1–D7）、选型核实记录、成本结构、待定项 |
| [persona.md](persona.md) | Aynur 人设卡（语气 / 记忆 / 兜底 / 问候模板） |
| [m0-protocol.md](m0-protocol.md) | M0 链路验证协议（T0 文本 → T1 音频，可直接执行） |
| [icon-prompt.md](icon-prompt.md) | 图标生图提示词与评审清单 |
| [img/](img/) | 界面截图 |

## 代码与文档的对应关系

| 文档里的东西 | 落在哪 |
|---|---|
| 文字规范化规则 | `server/normalize.py` |
| 人设提示词 / 话术 / 术语表 | `server/persona.py` |
| 安全兜底 | `server/safety.py` |
| 记忆与长期档案 | `server/memory.py` |
| 四条链路 | `server/pipeline.py` |
| Provider 适配 | `server/providers/` |
| 20 题语料模板 | `corpus/questions.csv` |
| 盲评工具 | `eval/run_ab.py` `eval/blind.py` `eval/summarize.py` |

## 待补

- 影视配音方向的独立规划（README 中提到，尚未成文）
- 正式术语表（当前只有第一批，在 `persona.py`）
- 真实语料录音与转写（M0 卡点）
- 讯飞维语 TTS 开通（已确认支持，见 `decisions.md` D7）
