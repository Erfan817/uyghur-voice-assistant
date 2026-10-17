# 语料

`questions.csv` 是 M0 的 20 题模板：15 道纯维语（天气/健康/家常/办事/朗读各 3）+ 5 道混说。

**这些不是"例句"，是占位。** 真正要用的是家里人自己的问法——把 `text_ug` 换成长辈的原话，
`speaker`、`dialect`、`expected_facts` 按实际填写。

## 录音

- 真机、客厅（电视开着）、长辈自然语速，每题说两遍
- 手机自带录音机录 m4a 即可，回来用 ffmpeg 转 16k 单声道 WAV
- 命名：`q01_weather_01.m4a`，与 `id` 对齐

## 转写

录音当天就转写，别拖。`transcript` 写进同目录的 `transcripts.csv`（或直接补一列），
转写者用维语正字，术语保留原样。

## 音频不入库

`.gitignore` 已排除 `*.wav` / `*.m4a` / `recordings/`。只提交 CSV 和转写文本。
