# -*- coding: utf-8 -*-
"""根据时长与情绪分段合成配乐：Am7 - Fmaj7 - Cmaj7 - G6 循环，钢琴 + 垫子 + 极简节拍"""

import numpy as np
from scipy.signal import fftconvolve, butter, sosfilt
from scipy.io import wavfile

SR = 44100
BPM = 76.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT

CHORDS = [
    [45, 52, 57, 60, 64, 67],   # Am7
    [41, 48, 53, 57, 60, 64],   # Fmaj7
    [48, 55, 60, 64, 67, 71],   # Cmaj7
    [43, 50, 55, 59, 62, 64],   # G6
]
ROOTS = [33, 29, 36, 31]
ARP = [0, 3, 2, 4, 1, 3, 2, 5]

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


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def _piano(midi, dur, vel, rng):
    n = int(dur * SR)
    f = hz(midi)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, amp in ((1, 1.0), (2, 0.30), (3, 0.12), (4, 0.055), (6, 0.02)):
        if f * k > 12000:
            break
        out += amp * np.sin(2 * np.pi * f * k * t + rng.uniform(0, 6.28))
    out += 0.25 * np.sin(2 * np.pi * f * 1.0015 * t)
    out *= np.exp(-t * (2.0 + f / 700)) * (1 - np.exp(-t * 300))
    return out * vel


def _pad(midi, dur, vel, rng):
    n = int(dur * SR)
    f = hz(midi)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det in (-0.005, 0.0, 0.0055):
        out += np.sin(2 * np.pi * f * (1 + det) * t + rng.uniform(0, 6.28))
    out += 0.18 * np.sin(2 * np.pi * f * 2 * t)
    a = int(dur * 0.45 * SR)
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a) ** 1.5
    r = int(dur * 0.42 * SR)
    e[-r:] *= np.linspace(1, 0, r) ** 0.9
    return out * e * vel / 3.0


def _kick(vel):
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    f = 48 + 95 * np.exp(-t * 26)
    ph = 2 * np.pi * np.cumsum(f) / SR
    out = np.sin(ph) * np.exp(-t * 8.0)
    out += 0.12 * np.sin(2 * np.pi * 96 * t) * np.exp(-t * 40)
    return out * vel


_SOS_HAT = butter(2, [5200, 10500], "bandpass", fs=SR, output="sos")
_SOS_SN = butter(2, [900, 4200], "bandpass", fs=SR, output="sos")


def _hat(vel, rng):
    n = int(0.07 * SR)
    t = np.arange(n) / SR
    return sosfilt(_SOS_HAT, rng.normal(0, 1, n)) * np.exp(-t * 70) * vel


def _snare(vel, rng):
    n = int(0.26 * SR)
    t = np.arange(n) / SR
    x = sosfilt(_SOS_SN, rng.normal(0, 1, n))
    x /= (np.abs(x).max() + 1e-9)
    body = np.sin(2 * np.pi * 175 * t) * 0.5
    return (x * 0.75 + body) * np.exp(-t * 24) * vel


def compose(duration, segments, out_path):
    """segments: [(起始秒, tone)]，按时间取最近一段的情绪，并在段间做 1.2s 过渡"""
    rng = np.random.default_rng(11)
    N = int(SR * duration)

    def mood(t):
        cur = TONE["calm"]
        for ts, tone in segments:
            if t >= ts:
                cur = TONE.get(tone, TONE["calm"])
        # 段边界 1.2s 内线性过渡
        for ts, tone in segments:
            if -0.1 < t - ts < 1.2:
                prev = TONE["calm"]
                for ts2, tone2 in segments:
                    if ts2 < ts:
                        prev = TONE.get(tone2, TONE["calm"])
                k = max(0.0, (t - ts) / 1.2)
                nxt = TONE.get(tone, TONE["calm"])
                cur = tuple(prev[i] + (nxt[i] - prev[i]) * k for i in range(3))
        return cur

    L = np.zeros(N)
    R = np.zeros(N)

    def add(sig, at, gain=1.0, pan=0.0):
        i = int(at * SR)
        if i >= N or i < 0:
            return
        m = min(len(sig), N - i)
        L[i:i + m] += sig[:m] * gain * (1 - max(0.0, pan) * 0.5)
        R[i:i + m] += sig[:m] * gain * (1 - max(0.0, -pan) * 0.5)

    for b in range(int(duration / BAR) + 2):
        t0 = b * BAR
        ci = b % 4
        ch = CHORDS[ci]
        rk, pk, kk = mood(min(t0, duration - 0.01))

        for j, m in enumerate(ch[:4]):
            add(_pad(m, BAR * 1.2, 0.20 * kk, rng), t0, pan=(j - 1.5) * 0.3)
        add(_pad(ROOTS[ci] + 12, BAR * 0.98, 0.30 * (0.5 + kk * 0.7), rng), t0)
        add(_pad(ROOTS[ci] + 24, BAR * 0.42, 0.16 * kk, rng), t0 + BAR * 0.55)

        for e in range(8):
            te = t0 + e * BEAT / 2
            if te >= duration:
                break
            m = ch[ARP[e] % len(ch)] + 12
            v = 0.26 * pk * (0.95 if e % 2 == 0 else 0.52) * (0.88 + 0.24 * rng.random())
            add(_piano(m, 1.6, v, rng), te, pan=0.4 if e % 2 else -0.4)

        if b % 2 == 0 and pk > 0.4:
            mel = ch[(b // 2) % 4] + 24
            add(_piano(mel, 2.6, 0.24 * pk, rng), t0 + BEAT * 0.5, pan=0.15)

        if rk > 0.08:
            add(_kick(0.62 * rk), t0)
            add(_kick(0.46 * rk), t0 + 2 * BEAT)
            if rk > 0.4:
                add(_kick(0.28 * rk), t0 + 3.5 * BEAT)
                add(_snare(0.20 * rk, rng), t0 + 2 * BEAT)
            for e in range(8):
                add(_hat(0.10 * rk * (1.0 if e % 2 == 0 else 0.55), rng),
                    t0 + e * BEAT / 2, pan=0.35)

    # 高光点的上行分解和弦
    for (ts, tone) in segments:
        if tone == "recover" and ts + 4 < duration:
            for i, m in enumerate([69, 72, 76, 79, 84]):
                add(_piano(m, 2.4, 0.26, rng), ts + 0.3 + i * 0.21, pan=0.12 * (i - 2))
        if tone == "peak" and ts + 3 < duration:
            for i, m in enumerate([72, 76, 79, 84]):
                add(_piano(m, 2.4, 0.24, rng), ts + 0.2 + i * 0.21, pan=0.12 * (i - 2))

    # 混响
    def make_ir(sec=1.7):
        n = int(sec * SR)
        t = np.arange(n) / SR
        ir = rng.normal(0, 1, n) * np.exp(-t * 3.4)
        ir = sosfilt(butter(2, 4200, "lowpass", fs=SR, output="sos"), ir)
        ir[: int(0.015 * SR)] = 0
        return ir / (np.abs(ir).max() + 1e-9)

    IR = make_ir()
    wetL = fftconvolve(L, IR, mode="full")[:N]
    wetR = fftconvolve(R, IR, mode="full")[:N]
    mixL = sosfilt(butter(2, 34, "highpass", fs=SR, output="sos"), L * 0.80 + wetL * 0.24)
    mixR = sosfilt(butter(2, 34, "highpass", fs=SR, output="sos"), R * 0.80 + wetR * 0.24)

    peak = max(np.abs(mixL).max(), np.abs(mixR).max(), 1e-9)
    mixL, mixR = mixL / peak, mixR / peak

    def soft(x, d=1.25):
        return np.tanh(x * d) / np.tanh(d)

    mixL, mixR = soft(mixL * 0.9) * 0.80, soft(mixR * 0.9) * 0.80
    f = int(min(1.5, duration * 0.1) * SR)
    mixL[:f] *= np.linspace(0, 1, f) ** 1.2
    mixR[:f] *= np.linspace(0, 1, f) ** 1.2
    tl = int(min(3.0, duration * 0.1) * SR)
    mixL[-tl:] *= np.linspace(1, 0, tl) ** 1.3
    mixR[-tl:] *= np.linspace(1, 0, tl) ** 1.3

    st = np.clip(np.stack([mixL, mixR], 1), -1, 1)
    wavfile.write(out_path, SR, (st * 32767).astype(np.int16))
    return out_path
