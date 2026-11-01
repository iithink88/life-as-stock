# -*- coding: utf-8 -*-
"""
把一个人的人生画成 K 线图 —— 渲染引擎
usage:
    python render.py story.json -o out.mp4
    python render.py story.json --still 12.5 44.0     # 只导出静帧预览
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 720, 1280, 30

# ---------------- 视觉常量（改这里换风格） ----------------
PAPER     = (211, 202, 181)
INK       = (44, 33, 24)
INK_SOFT  = (78, 68, 56)
INK_MUTE  = (132, 122, 106)
INK_FAINT = (166, 156, 138)
INK_LABEL = (104, 94, 80)
RED       = (169, 52, 46)
GREEN     = (40, 82, 66)
GRID      = (199, 191, 173)
PLAGUE_BG = (40, 34, 28)

TITLE_Y, LINE_H, TITLE_SIZE = 196, 60, 46
X0, X1 = 60.0, 566.0
SEC_PER_CANDLE = 1.5

FONT_CANDIDATES = [
    r"C:/Windows/Fonts/simsun.ttc",
    r"C:/Windows/Fonts/SourceHanSerifSC-Regular.otf",
    r"C:/Windows/Fonts/NotoSerifSC-Regular.otf",
    r"/System/Library/Fonts/Supplemental/Songti.ttc",
    r"/System/Library/Fonts/Songti.ttc",
    r"/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    r"/usr/share/fonts/truetype/arphic/uming.ttc",
    r"C:/Windows/Fonts/msyh.ttc",
]
_fc = {}

# ---------------- 音乐情绪表 ----------------
TONE = {
    "calm":    (0.34, 0.55, 0.62),
    "rise":    (0.66, 0.82, 0.68),
    "peak":    (1.00, 1.00, 0.80),
    "fall":    (0.60, 0.72, 0.76),
    "crash":   (0.82, 0.70, 0.86),
    "dark":    (0.16, 0.34, 0.90),
    "recover": (1.00, 1.05, 0.92),
    "end":     (0.30, 0.50, 0.62),
}


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("找不到中文字体，请在 FONT_CANDIDATES 里补充本机宋体路径")


FONT_PATH = find_font()


def F(size, bold=False):
    if size not in _fc:
        _fc[size] = ImageFont.truetype(FONT_PATH, size, index=0)
    return _fc[size]


# ---------------- 文案标记 ----------------
def parse_line(s):
    """'25岁，他{清仓出川}，' -> [('25岁，他',0),('清仓出川',1),('，',0)]"""
    out, buf, red = [], "", False
    for ch in s:
        if ch == "{":
            if buf:
                out.append((buf, 1 if red else 0))
            buf, red = "", True
        elif ch == "}":
            if buf:
                out.append((buf, 1 if red else 0))
            buf, red = "", False
        else:
            buf += ch
    if buf:
        out.append((buf, 1 if red else 0))
    return out


# ---------------- 背景 ----------------
def make_background():
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    for i, c in enumerate(PAPER):
        base[..., i] = c
    low = rng.normal(0, 1, (H // 20 + 2, W // 20 + 2)).astype(np.float32)
    low = low - low.min()
    low = low / (low.max() + 1e-6) * 255
    low = np.array(Image.fromarray(low.astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32)
    base += (low[..., None] - 128) * 0.022
    base += rng.normal(0, 2.2, (H, W, 1)).astype(np.float32)
    cx, cy = W * 0.42, H * 0.36
    d = np.sqrt(((xx - cx) / (W * 0.95)) ** 2 + ((yy - cy) / (H * 1.05)) ** 2)
    base *= (1.0 - 0.135 * np.clip(d, 0, 1.7) ** 2.0)[..., None]
    base *= (1 - 0.035 * np.clip((yy - H * 0.70) / (H * 0.30), 0, 1))[..., None]
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def make_grain_bank(n=10):
    rng = np.random.default_rng(99)
    return [np.repeat(rng.normal(0, 2.1, (H, W, 1)).astype(np.float32), 3, axis=2) for _ in range(n)]


# ---------------- 剧本 ----------------
class Story:
    def __init__(self, data):
        self.person = data.get("person", "")
        chs = data["chapters"]
        t = 0.0
        self.chapters = []
        for c in chs:
            dur = float(c.get("dur", 6.0))
            self.chapters.append(dict(
                t0=t, t1=t + dur,
                lines=[parse_line(s) for s in c["lines"]],
                raw_lines=c["lines"],
                right=[s for s in c.get("right", []) if s],
                cite=c.get("cite"),
                price=[(float(a), float(b)) for a, b in c["price"]],
                ann=[(a[0], a[2] if len(a) > 2 else 0.4, a[1] if len(a) > 1 else "below")
                     for a in c.get("ann", [])],
                flash=c.get("flash"),
                stamp=(c["stamp"][0], float(c["stamp"][1])) if c.get("stamp") else None,
                end=bool(c.get("end")),
                tone=c.get("tone", "calm"),
            ))
            t += dur
        self.total = t
        self._build_knots()
        self._build_candles()
        self._build_scale()

    # --- 股价关键帧 ---
    def _build_knots(self):
        k = []
        for ch in self.chapters:
            span = ch["t1"] - ch["t0"]
            for frac, price in ch["price"]:
                k.append((ch["t0"] + frac * span, price))
            # 保证章节末有落点
            if not any(abs(f - 1.0) < 1e-6 for f, _ in ch["price"]):
                k.append((ch["t1"] - 1e-4, ch["price"][-1][1]))
        # 去重并按时间排序
        k.sort(key=lambda x: x[0])
        ded = []
        for t, p in k:
            if ded and abs(t - ded[-1][0]) < 1e-6:
                ded[-1] = (t, p)
            else:
                ded.append((t, p))
        self.knots = ded

    def price_at(self, t):
        k = self.knots
        if t <= k[0][0]:
            return k[0][1]
        for i in range(len(k) - 1):
            t0, p0 = k[i]
            t1, p1 = k[i + 1]
            if t0 <= t <= t1:
                if t1 - t0 < 1e-9:
                    return p1
                x = (t - t0) / (t1 - t0)
                x = x * x * (3 - 2 * x)          # smoothstep
                return p0 + (p1 - p0) * x
        return k[-1][1]

    def _build_candles(self):
        rng = np.random.default_rng(2024)
        n = max(20, int(round(self.total / SEC_PER_CANDLE)))
        self.n_candle = n
        self.step_t = self.total / n
        candles, prev = [], self.price_at(0) * 0.99
        for i in range(n):
            t = i * self.step_t
            target = self.price_at(t)
            o = prev + (target - prev) * 0.45 + rng.normal(0, target * 0.006)
            c = target + rng.normal(0, target * 0.007)
            hi = max(o, c) + abs(rng.normal(0, target * 0.013)) + target * 0.003
            lo = min(o, c) - abs(rng.normal(0, target * 0.013)) - target * 0.003
            vol = 0.24 + abs(c - o) / max(target, 1e-6) * 2.1 + abs(rng.normal(0, 0.16))
            candles.append(dict(t=t, o=o, h=hi, l=lo, c=c, v=min(vol, 1.0)))
            prev = c
        vs = np.array([c["v"] for c in candles])
        vs = np.convolve(np.pad(vs, 1, mode="edge"), [0.25, 0.5, 0.25], mode="valid")
        for c, v in zip(candles, vs):
            c["v"] = float(np.clip(v, 0.14, 1.0))
        self.candles = candles

    def visible_count(self, t):
        return max(0, min(self.n_candle, int(t / self.step_t) + 1))

    def candle_index_at(self, t):
        return max(0, min(self.n_candle - 1, int(round(t / self.step_t))))

    def close_at(self, t):
        n = self.visible_count(t)
        return self.candles[0]["o"] if n <= 0 else self.candles[n - 1]["c"]

    # --- 纵轴自适应（expand-only）---
    def _build_scale(self):
        n = int(self.total * FPS) + 2
        los, his = np.zeros(n), np.zeros(n)
        lo = hi = self.candles[0]["c"]
        los_r = min(c["l"] for c in self.candles[:1]) - 1
        his_r = max(c["h"] for c in self.candles[:1]) + 1
        for i in range(n):
            v = self.visible_count(i / FPS)
            if v > 0:
                l = min(c["l"] for c in self.candles[:v])
                h = max(c["h"] for c in self.candles[:v])
                mid = (l + h) / 2
                span = max(h - l, mid * 0.30)
                los_r = min(los_r, mid - span * 0.62) if i > 4 else l
                his_r = max(his_r, mid + span * 0.62) if i > 4 else h
            lo += (los_r - lo) * 0.5
            hi += (his_r - hi) * 0.5
            los[i], his[i] = lo, hi
        self.los, self.his = los, his

    def chapter_index(self, t):
        for i, c in enumerate(self.chapters):
            if t < c["t1"]:
                return i
        return len(self.chapters) - 1

    def cx(self, i):
        pitch = (X1 - X0) / self.n_candle
        return X0 + i * pitch + pitch / 2


def nice_step(span):
    for s in (0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200):
        if span / s <= 4.6:
            return s
    return 500


# ---------------- 渲染 ----------------
class Renderer:
    def __init__(self, story):
        self.s = story
        self.bg = make_background()
        self.grain = make_grain_bank(10)

    def title_size(self, ch):
        size = TITLE_SIZE
        while size > 30:
            widest = 0
            for ln in ch["lines"]:
                widest = max(widest, sum(F(size).getlength(c) + 1.6
                                         for seg, _ in ln for c in seg))
            if widest <= 592:
                return size
            size -= 2
        return size

    def text_layer(self, ci, t):
        ch = self.s.chapters[ci]
        t0 = ch["t0"]
        layer = Image.new("RGBA", (W, 560), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        size = self.title_size(ch)
        f = F(size)
        lh = LINE_H if size >= 42 else 54
        is_cover = ci == 0

        for li, ln in enumerate(ch["lines"]):
            ta = t0 + (0.10 if not is_cover else -0.30) + li * 0.22
            p = (t - ta) / 0.42
            if p <= 0:
                continue
            p = min(1.0, p)
            ease = 1 - (1 - p) ** 3
            alpha = int(255 * ease)
            blur = (1 - ease) ** 1.3 * 8.5
            dy = int((1 - ease) * 15)
            tmp = Image.new("RGBA", (W, lh + 40), (0, 0, 0, 0))
            td = ImageDraw.Draw(tmp)
            x = 60
            for seg, red in ln:
                col = RED if red else INK
                for c in seg:
                    td.text((x, 20), c, font=f, fill=col + (alpha,),
                            stroke_width=1, stroke_fill=col + (alpha,))
                    x += f.getlength(c) + 1.6
            if blur > 0.3:
                tmp = tmp.filter(ImageFilter.GaussianBlur(blur))
            layer.alpha_composite(tmp, (0, TITLE_Y + li * lh + dy))

        if not self.s.person:
            return layer
        n = len(ch["lines"])
        ny = TITLE_Y + n * lh + 40
        p = (t - (t0 + (0.28 if not is_cover else -0.20))) / 0.38
        if p > 0:
            a = int(255 * min(1, p))
            d.text((60, ny), self.s.person, font=F(26), fill=INK + (a,),
                   stroke_width=1, stroke_fill=INK + (a,))
            price = str(int(round(self.s.close_at(t))))
            d.text((57, ny + 36), price, font=F(52), fill=INK + (a,),
                   stroke_width=1, stroke_fill=INK + (a,))
            d.text((57 + F(52).getlength(price) + 12, ny + 62),
                   "虚拟股价", font=F(13), fill=INK_MUTE + (a,))
            rx = W - 58
            for k, line in enumerate(ch["right"]):
                col = INK_SOFT if k == 0 else INK_MUTE
                d.text((rx, ny + 6 + k * 26), line, font=F(15), fill=col + (a,), anchor="ra")
        return layer

    def frame(self, t):
        s = self.s
        ci = s.chapter_index(t)
        ch = s.chapters[ci]
        img = self.bg.convert("RGBA")

        if ch["flash"]:
            k = max(0.0, min(1.0, (t - ch["t0"]) / 3.0))
            a = int(30 * (1 - k) ** 1.5)
            if a > 0:
                ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(ov).rectangle([0, 0, W, H],
                                             fill=(RED if ch["flash"] == "red" else GREEN) + (a,))
                img = Image.alpha_composite(img, ov)

        d = ImageDraw.Draw(img, "RGBA")
        n = len(ch["lines"])
        ny = TITLE_Y + n * LINE_H + 40
        plot_top = max(496, ny + 132)
        plot_bot, vol_top, vol_bot = 900, 924, 970

        i = max(0, min(len(s.los) - 1, int(round(t * FPS))))
        lo, hi = s.los[i], s.his[i]
        vv = s.visible_count(t)
        if vv > 0:
            hi = max(hi, max(c["h"] for c in s.candles[:vv]) * 1.01)
            lo = min(lo, min(c["l"] for c in s.candles[:vv]) * 0.99)

        def py(p):
            return plot_bot - (p - lo) / max(1e-6, hi - lo) * (plot_bot - plot_top)

        step = nice_step(hi - lo)
        v = math.ceil(lo / step) * step
        while v < hi:
            y = py(v)
            if plot_top + 4 < y < plot_bot - 4:
                d.line([(X0, y), (X1, y)], fill=GRID + (150,), width=1)
                lab = str(int(v)) if abs(v - round(v)) < 1e-6 else f"{v:.1f}"
                d.text((X0 - 10, y - 8), lab, font=F(13), fill=INK_FAINT, anchor="ra")
            v += step

        last_x = None
        self._boxes = []
        self._ann_boxes = []
        for k in range(vv):
            c = s.candles[k]
            x = s.cx(k)
            col = RED if c["c"] >= c["o"] else GREEN
            yh, yl, yo, yc = py(c["h"]), py(c["l"]), py(c["o"]), py(c["c"])
            grow = 1.0
            if k == vv - 1:
                grow = max(0.0, min(1.0, (t - c["t"]) / 0.42))
                if grow < 1.0:
                    mid = (yo + yc) / 2
                    yo = mid + (yo - mid) * grow
                    yc = mid + (yc - mid) * grow
                    yh = mid + (yh - mid) * grow
                    yl = mid + (yl - mid) * grow
            d.line([(x, yh), (x, yl)], fill=col + (235,), width=1)
            a0, a1 = min(yo, yc), max(yo, yc)
            if a1 - a0 < 1.7:
                a1 = a0 + 1.7
            d.rectangle([x - 2.7, a0, x + 2.7, a1], fill=col + (240,))
            vh = c["v"] * (vol_bot - vol_top) * grow
            d.rectangle([x - 2.1, vol_bot - vh, x + 2.1, vol_bot], fill=col + (74,))
            self._boxes.append((x - 4, x + 4, min(yh, yl) - 3, max(yh, yl) + 3))
            last_x = x

        if vv > 0:
            y = py(s.candles[vv - 1]["c"])
            xx = X0
            while xx < last_x + 2:
                d.line([(xx, y), (min(xx + 3.4, last_x + 2), y)], fill=(140, 131, 115, 175), width=1)
                xx += 7.6
            ax = last_x + 14
            d.line([(ax, y), (ax + 10, y)], fill=INK_SOFT + (195,), width=1)
            d.line([(ax, y), (ax + 4.5, y - 3.2)], fill=INK_SOFT + (195,), width=1)
            d.line([(ax, y), (ax + 4.5, y + 3.2)], fill=INK_SOFT + (195,), width=1)

        self._annotations(d, ch, t, vv, py)
        if ch["stamp"]:
            self._stamp(img, ch, t, last_x)

        img.alpha_composite(self.text_layer(ci, t), (0, 0))
        if ch["cite"]:
            cp = (t - (ch["t0"] + 0.9)) / 0.4
            if cp > 0:
                d.text((60, 992), ch["cite"], font=F(12),
                       fill=INK_FAINT + (int(255 * min(1, cp)),))

        d2 = ImageDraw.Draw(img)
        x = 60
        for cch in "世界切片":
            d2.text((x, 106), cch, font=F(19), fill=INK_LABEL)
            x += F(19).getlength(cch) + 6.5

        arr = np.asarray(img.convert("RGB"), np.float32)
        arr += self.grain[random.randrange(len(self.grain))]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        return self._glitch(img, t)

    def _annotations(self, d, ch, t, vv, py):
        f14 = F(14)
        for idx, (text, pos, where) in enumerate(ch["ann"]):
            k = self.s.candle_index_at(ch["t0"] + pos * (ch["t1"] - ch["t0"]))
            # 等锚点蜡烛真正长出来再显示，避免标注指向不存在的 K 线
            start = max(ch["t0"] + 0.75 + idx * 0.55, k * self.s.step_t)
            if t < start or k >= vv or k < 0:
                continue
            a = min(1, (t - start) / 0.35)
            c = self.s.candles[k]
            x = self.s.cx(k)
            tw = f14.getlength(text)
            if where == "above":
                y0 = py(c["h"]) - 4
                y1 = y0 - 34
                ty = y1 - 17
            else:
                y0 = py(c["l"]) + 4
                y1 = y0 + 34
                ty = y1 + 19
            # 标签横向避让：优先正上方，被 K 线占位则左右平移
            best_dx, best_sc = 0, 1e9
            for dx in (0, -36, 36, -70, 70):
                r = (x + dx - tw / 2 - 4, ty - 17, x + dx + tw / 2 + 4, ty + 17)
                sc = sum(3 for b in self._boxes
                         if not (r[2] < b[0] or r[0] > b[1] or r[3] < b[2] or r[1] > b[3]))
                sc += 0.012 * abs(dx)
                if sc < best_sc:
                    best_dx, best_sc = dx, sc
            lx = min(max(x + best_dx, 40 + tw / 2), W - 40 - tw / 2)
            d.line([(x, y0), (lx, y1)], fill=(112, 103, 90, int(165 * a)), width=1)
            d.rounded_rectangle([lx - tw / 2 - 4, ty - 17, lx + tw / 2 + 4, ty + 17],
                                radius=3, fill=PAPER + (255,))
            d.text((lx, ty), text, font=f14, fill=INK_SOFT + (int(235 * a),), anchor="mm")
            self._ann_boxes.append((lx - tw / 2 - 6, lx + tw / 2 + 6, ty - 19, ty + 19))

    def _stamp(self, img, ch, t, last_x):
        text, ts = ch["stamp"]
        tstar = ch["t0"] + ts * (ch["t1"] - ch["t0"])
        if t < tstar:
            return
        k = min(1.0, (t - tstar) / 0.26)
        ease = 1 - (1 - k) ** 2.2
        alpha = int(255 * ease)
        f = F(30)
        w, h = int(f.getlength(text) + 40), 56
        lay = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle([12, 12, 12 + w, 12 + h], radius=6, fill=PLAGUE_BG + (alpha,))
        ld.text((12 + w / 2, 12 + h / 2 - 3), text, font=f, fill=(243, 237, 226, alpha), anchor="mm")
        sc = 0.6 + 0.4 * ease
        if sc < 1:
            lay = lay.resize((max(1, int(lay.width * sc)), max(1, int(lay.height * sc))), Image.LANCZOS)
        lay = lay.rotate(-2.6, resample=Image.BICUBIC, expand=True)
        boxes = getattr(self, "_boxes", [])
        anns = getattr(self, "_ann_boxes", [])
        cands = [(96, 566), (96, 646), (420, 566), (420, 646)]
        if ch["end"]:
            cands = [(96, 566)] + cands
        best, best_score = cands[0], 1e9
        for px_, py_ in cands:
            r = (px_, py_, px_ + lay.width, py_ + lay.height)
            sc = 0.0
            for b in boxes:
                if not (r[2] < b[0] or r[0] > b[1] or r[3] < b[2] or r[1] > b[3]):
                    sc += 3
            for b in anns:
                if not (r[2] < b[0] or r[0] > b[1] or r[3] < b[2] or r[1] > b[3]):
                    sc += 8
            # 图还短的时候优先放右侧空白，图铺满后优先放左侧
            if last_x is not None and last_x < 360 and px_ < 250:
                sc += 3.0
            if last_x is not None and last_x > 430 and px_ > 250:
                sc += 3.0
            sc += 0.02 * abs(px_ - 250)
            if sc < best_score:
                best, best_score = (px_, py_), sc
        img.alpha_composite(lay, best)

    def _glitch(self, img, t):
        for ch in self.s.chapters[1:]:
            b = ch["t0"]
            if b - 0.10 <= t <= b + 0.22:
                k = (t - (b - 0.10)) / 0.32
                amp = (1 - abs(k - 0.5) * 2) ** 0.75
                arr = np.asarray(img, np.uint8).astype(np.int16)
                rng = np.random.default_rng(int(t * 1000) % 99991)
                sh = int(round(3.4 * amp))
                if sh > 0:
                    arr[..., 0] = np.roll(arr[..., 0], sh, axis=1)
                    arr[..., 2] = np.roll(arr[..., 2], -sh, axis=1)
                for _ in range(5):
                    y = int(rng.integers(0, H - 70))
                    hgt = int(rng.integers(6, 56))
                    dx = int(rng.integers(-28, 29) * amp)
                    if dx:
                        arr[y:y + hgt] = np.roll(arr[y:y + hgt], dx, axis=1)
                return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        return img


def validate(story):
    warns = []
    if len(story.chapters) < 6:
        warns.append("章节少于 6 个，故事会显得很赶")
    for c, raw in zip(story.chapters, story.chapters):
        if len(c["lines"]) > 3:
            warns.append(f"章节 {c['t0']:.1f}s 有 {len(c['lines'])} 行标题，最多 3 行")
        if c["t1"] - c["t0"] < 3.0:
            warns.append(f"章节 {c['t0']:.1f}s 只有 {c['t1']-c['t0']:.1f} 秒，太短")
    for a, b in zip(story.chapters, story.chapters[1:]):
        pa = a["price"][-1][1]
        pb = b["price"][0][1]
        if abs(pb - pa) / max(1e-6, abs(pa)) > 0.25:
            warns.append(f"{a['t1']:.1f}s 处股价从 {pa:.1f} 跳到 {pb:.1f}，会形成缺口（若非有意请对齐）")
    for c in story.chapters:
        for text, pos, where in c["ann"]:
            k = story.candle_index_at(c["t0"] + pos * (c["t1"] - c["t0"]))
            show = max(c["t0"] + 0.75, k * story.step_t)
            if c["t1"] - show < 1.4:
                warns.append(f"标注「{text}」到 {show:.1f}s 才出现，只剩 {c['t1']-show:.1f}s，"
                             f"把 ann 的进度从 {pos} 调到 0.25~0.45")
    for w in warns:
        print("[warn]", w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--still", nargs="*", type=float, default=None)
    ap.add_argument("--no-music", action="store_true")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    data = json.load(open(args.story, encoding="utf-8"))
    story = Story(data)
    validate(story)
    r = Renderer(story)

    out = args.out or os.path.splitext(args.story)[0] + ".mp4"
    if args.still is not None:
        for ts in args.still:
            p = os.path.splitext(out)[0] + f"_{ts:06.2f}.png"
            r.frame(ts).save(p)
            print("saved", p)
        return

    wav = os.path.splitext(out)[0] + ".wav"
    if not args.no_music:
        sys.path.insert(0, here)
        import music
        segs = [(c["t0"], c["tone"]) for c in story.chapters]
        music.compose(story.total, segs, wav)
        print("music ->", wav)

    total = int(story.total * FPS)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if not args.no_music and os.path.exists(wav):
        cmd += ["-i", wav, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for i in range(total):
        p.stdin.write(r.frame(i / FPS).tobytes())
        if i % 300 == 0:
            print(f"{i}/{total}  {time.time()-t0:.0f}s", flush=True)
    p.stdin.close()
    p.wait()
    print("done ->", out, round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
