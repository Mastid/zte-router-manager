# -*- coding: utf-8 -*-
"""生成应用图标（192x192 PNG，圆角矩形 + 白色 Z），不依赖第三方库。"""
import os
import struct
import zlib

S = 192
R = 42          # 圆角半径
M = 46          # Z 的外边距

BG1 = (11, 99, 197)     # #0B63C5
BG2 = (10, 70, 150)


def in_round_rect(x, y):
    if x < 0 or y < 0 or x >= S or y >= S:
        return False
    cx = min(max(x, R), S - 1 - R)
    cy = min(max(y, R), S - 1 - R)
    return (x - cx) ** 2 + (y - cy) ** 2 <= R * R


def in_rect(x, y, x0, y0, x1, y1):
    return x0 <= x <= x1 and y0 <= y <= y1


def in_poly(x, y, pts):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / float(yj - yi) + xi):
            inside = not inside
        j = i
    return inside


Z_TOP = [(M, M), (S - M, M), (S - M, M + 22), (M, M + 22)]
Z_BOT = [(M, S - M - 22), (S - M, S - M - 22), (S - M, S - M), (M, S - M)]
Z_DIAG = [(S - M - 20, M + 22), (S - M, M), (M + 20, S - M), (M, S - M - 22)]


def pixel(x, y):
    if not in_round_rect(x, y):
        return (0, 0, 0, 0)
    if in_poly(x, y, Z_TOP) or in_poly(x, y, Z_BOT) or in_poly(x, y, Z_DIAG):
        return (255, 255, 255, 255)
    t = y / float(S - 1)
    r = int(BG1[0] + (BG2[0] - BG1[0]) * t)
    g = int(BG1[1] + (BG2[1] - BG1[1]) * t)
    b = int(BG1[2] + (BG2[2] - BG1[2]) * t)
    return (r, g, b, 255)


def write_png(path, size):
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            row += bytes(pixel(x, y))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "res")
    n = write_png(os.path.join(base, "mipmap-xxxhdpi", "ic_launcher.png"), S)
    print("icon written", n, "bytes")
