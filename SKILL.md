---
name: life-as-stock
description: 把一个人物的一生画成一只股票的 K 线图，输出竖屏 MP4 短视频。当用户要求"把某人的一生画成股票/做成K线视频""用股票走势讲某人生平""做一个名人生平的信息图视频"，或提到李清照/李白那类"人生轨迹股票化"的形式时使用。输入一个人名，自动完成资料查证、剧情编排、逐帧渲染与配乐合成。
agent_created: true
---

# 人生股票化视频

把一个人的生平翻译成一条 K 线：出生是挂牌，贬谪是跌停，平反是 V 型反转，去世是退市。输出 720×1280 竖屏 MP4，暖米色纸感信息图风格，无旁白、纯文字 + 图表 + 配乐。

## 何时使用

- "把 XX 的一生画成一只股票"
- "用 K 线图讲 XX 的生平"
- 需要一条 90 秒左右、可直接发抖音/视频号的文史类竖屏视频

## 工作流

### 第 1 步：查证生平

先用 WebSearch 核实人物关键节点，拿到**准确的年份 + 事件 + 年龄（虚岁）+ 一句可引用的原文**。至少覆盖：出生、成名、第一次重大挫折、人生最高点、最惨的低谷、转折/平反、去世。宁可少写一章，也不要写错年份。

同时收集 1-2 句当事人自己的诗文做章节脚注（`cite` 字段），这是成片"高级感"的主要来源。

### 第 2 步：写剧本 JSON

按 `references/writing-guide.md` 的规则编排章节，按 `references/story-schema.md` 的字段写 JSON。先用 `references/story-schema.md` 里的骨架起步，再逐章填。

产出统一放在当前工作目录下的 `life-stock/<姓名>/`：`story.json` + 渲染出的 `mp4`。

写完务必自检：

- 每章 `price` 的第一个值 == 上一章最后一个值（保持走势连续）
- 章节数 14–18，每章 `dur` 4–7 秒，总时长 85–100 秒
- 每行标题 ≤ 12 个汉字，每章 ≤ 2 行（最多 3 行）
- 每章最多 1 个红字关键词

### 第 3 步：先出静帧再出片

**不要直接渲染整片。** 先挑 3–4 个关键时间点出静帧，肉眼检查排版：

```bash
python scripts/render.py story.json --still 8.5 44.6 62.0
```

重点看：标题有没有超宽被裁、标注有没有压在 K 线上、数字和右侧信息有没有错位。发现问题改 JSON 重出静帧，直到满意。

### 第 4 步：渲染成片

```bash
python scripts/render.py story.json -o out.mp4
```

约 45ms/帧，90 秒 ≈ 3.5 分钟。过程会：生成配乐（按每章 `tone` 控制情绪）→ 逐帧绘制 → 管道直送 ffmpeg → 统一响度到 -14 LUFS。

渲染完用 `ffmpeg -ss <t> -i out.mp4 -frames:v 1 chk.png` 抽查 2–3 帧，确认无误再交付。

## 依赖与解释器

需要 `Pillow` / `numpy` / `scipy` / `ffmpeg`，以及一款中文宋体（Windows 用 `simsun.ttc`，macOS 找 Songti，脚本会自动探测）。

**优先使用 WorkBuddy 托管 Python**，系统 `python` 往往缺依赖：

```bash
# Windows
PY="$HOME/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
# macOS / Linux
PY="$HOME/.workbuddy/binaries/python/envs/default/bin/python"

"$PY" scripts/render.py story.json -o out.mp4
```

托管 Python 缺包时：`"$PY" -m pip install pillow numpy scipy`。跑之前先 `"$PY" -c "import PIL,numpy,scipy"` 确认一次，报错再装。

## 调参

- **换风格**：`scripts/render.py` 顶部常量区（`PAPER` 纸色、`INK` 墨色、`RED`/`GREEN` 涨跌色）。注意保持**红涨绿跌**的中国习惯。
- **换节奏**：`SEC_PER_CANDLE`（默认 1.5 秒一根）控制 K 线密度。
- **换配乐**：替换 `scripts/music.py` 的 `CHORDS` 和弦进行；或在 JSON 同目录放一个同名 `.wav` 后加 `--no-music` 自行混音。

## 示例

`examples/李白.json`（91 秒，17 章）与 `examples/苏轼.json`（88 秒，17 章）是两套完整可跑的剧本，可直接改文案复用。
