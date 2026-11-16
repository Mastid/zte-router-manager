# -*- coding: utf-8 -*-
"""生成 iOS / PWA 用的方形图标（apple-touch-icon、manifest icons）。

iOS 会自己裁圆角，所以这里出「满幅方形」：底色用品牌深蓝，
中央叠 86% 大小的 squircle + 白色 Z（复用 gen_icon2 的绘制逻辑）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_icon2 as G

BG = G.C_BOT                   # #0A3A86
INSET = 0.86                   # squircle 占方形边长的比例（留出角度安全区）


def square(size, round_icon=False):
    inner = max(8, int(round(size * INSET)))
    rgba = G.render(inner, round_icon)
    off = (size - inner) // 2
    out = bytearray()
    for y in range(size):
        for x in range(size):
            sx, sy = x - off, y - off
            if 0 <= sx < inner and 0 <= sy < inner:
                i = (sy * inner + sx) * 4
                a = rgba[i + 3]
                if a == 255:
                    out += rgba[i:i + 4]
                    continue
                if a == 0:
                    out += bytes((BG[0], BG[1], BG[2], 255))
                    continue
                # 边缘半透明像素与底色混合，避免出现灰边
                t = a / 255.0
                out += bytes((int(rgba[i] * t + BG[0] * (1 - t)),
                              int(rgba[i + 1] * t + BG[1] * (1 - t)),
                              int(rgba[i + 2] * t + BG[2] * (1 - t)), 255))
            else:
                out += bytes((BG[0], BG[1], BG[2], 255))
    return bytes(out)


def write(path, size, round_icon=False):
    rgba = square(size, round_icon)
    import struct
    import zlib
    stride = size * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(size))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "zte-router-lab", "web")
    for name, size in [("icon-180.png", 180), ("icon-192.png", 192),
                       ("icon-512.png", 512)]:
        n = write(os.path.join(out, name), size, False)
        print("%-14s %3dpx  %6dB" % (name, size, n))
