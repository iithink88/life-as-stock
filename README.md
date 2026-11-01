# 人生股票化视频 · life-as-stock

输入一个人名，输出一条"把 TA 的一生画成一只股票"的竖屏短视频。

出生是挂牌，贬谪是跌停，平反是 V 型反转，去世是退市。720×1280 / 30fps / 约 90 秒，暖米色纸感信息图，无旁白，纯文字 + K 线 + 程序合成配乐。

## 安装

1. 把整个 `life-as-stock` 文件夹放进 WorkBuddy 的技能目录：

   | 系统 | 路径 |
   |---|---|
   | Windows | `C:\Users\<你的用户名>\.workbuddy\skills\` |
   | macOS / Linux | `~/.workbuddy/skills/` |

   放完应该是 `.../skills/life-as-stock/SKILL.md` 这个层级。

2. 重启 WorkBuddy（或新开一个对话），技能会自动被识别。

3. 依赖：`Pillow`、`numpy`、`scipy`、`ffmpeg`，以及一款中文宋体。用托管 Python 装：

   ```bash
   "$HOME/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -m pip install pillow numpy scipy
   ```

   缺字体时打开 `scripts/render.py`，改顶部的 `FONT_CANDIDATES`（Windows 自带 `simsun.ttc`，macOS 找 Songti）。

4. 自检：`python scripts/render.py examples/李白.json --still 12.5` 能出一张 PNG 就说明环境齐了。

## 用法

```
用户：把杜甫的一生画成一只股票
```

WorkBuddy 会自动：查证生平 → 编排章节剧本 → 出静帧校验排版 → 渲染成片。

也可以直接在命令行跑：

```bash
python scripts/render.py story.json -o out.mp4          # 出片
python scripts/render.py story.json --still 12.5 44.6   # 只出静帧
python scripts/render.py story.json --no-music          # 不出配乐
```

## 剧本写法

一个 JSON 就够，`price` 控制股价曲线，`lines` 里的 `{红字}` 控制标红：

```json
{
  "person": "苏轼",
  "chapters": [
    {"dur": 6.0,
     "lines": ["21岁进京赶考，", "主考官说：{我要避路}。"],
     "right": ["1057年 · 21岁", "持仓 笔"],
     "cite": "欧阳修主考，误认曾巩之作，置第二",
     "price": [[0, 10.0], [0.45, 16.0], [1, 22.0]],
     "tone": "rise", "flash": "red",
     "ann": [["进士及第", "above", 0.45]]}
  ]
}
```

字段全表见 `references/story-schema.md`，写作方法论（事件→行情翻译表、曲线设计、标题句式）见 `references/writing-guide.md`。

## 目录

```
life-as-stock/
├── SKILL.md                       工作流与调参
├── scripts/render.py              渲染引擎（版式/K线/文字动画/故障转场/编码）
├── scripts/music.py               配乐合成（四和弦循环 + 钢琴 + 垫子 + 极简鼓）
├── references/story-schema.md     字段说明
├── references/writing-guide.md    写作指南
└── examples/                      两套可直接跑的完整剧本
    ├── 李白.json
    └── 苏轼.json
```

## 实现要点

几个踩过的坑，改代码前值得知道：

1. **纵轴自适应**（`Story._build_scale`）是观感关键：expand-only + EMA 平滑，始终包住历史最高最低，早期低价段也能撑满画面。改成固定坐标轴会显得很空。
2. **文字动画用绝对时间**（章节起点 + 0.1/0.3s 偏移），不用章节内百分比——章节长短不一时节奏会乱。
3. **PIL 的 ImageDraw 在 RGBA 图上不做 alpha 混合**，必须新建透明 RGBA 层再 `alpha_composite`，否则整屏被纯色盖掉。
4. **标注与印章会打架**：引擎给标注做了横向避让（被 K 线占位就平移并画斜引线），给印章做了四候选位碰撞检测。
5. **标注要等锚点蜡烛长出来**才显示，否则会指向不存在的 K 线；`validate()` 会提醒标注出现太晚。
6. **故障转场**：对最终帧做 R/B 通道 `np.roll` ±3px + 5 条随机横带位移，0.32 秒。
7. 音频统一 `loudnorm=I=-14:TP=-1.5`，抖音/视频号通用响度。

## 依赖

`Pillow`、`numpy`、`scipy`、`ffmpeg`，以及一款中文宋体（Windows 用 `simsun.ttc`，macOS 找 Songti）。缺字体时改 `render.py` 顶部的 `FONT_CANDIDATES`。

## 已知边界

- 单个视频 85–100 秒，章节 14–18 个；超出这个区间节奏会失衡
- 立绘、实拍素材一概没有，全靠排版和曲线，所以**文案质量决定成片质量**
- 配乐是程序合成的氛围乐，比流媒体上的商用 BGM 克制；要更"炸"的节奏，替换 `scripts/music.py` 的 `CHORDS` 或自行混音后用 `--no-music`

## 许可

MIT License，随便用、随便改、商用也行，保留版权声明即可。
