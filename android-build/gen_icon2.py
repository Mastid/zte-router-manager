# -*- coding: utf-8 -*-
"""生成应用图标（多密度 PNG + Android 自适应图标前景）。

设计：超椭圆 squircle 底（蓝→深蓝对角渐变）+ 左上柔光 + 内描边，
      居中白色 Z（带柔和投影），整体与 App 内蓝色圆角 logo 一致。
不依赖第三方库，3x 超采样后降采样得到抗锯齿边缘。
"""
import os
import struct
import zlib

SS = 3                      # 超采样倍数
SHAPE_R = 0.235             # squircle 圆角比例（相对边长）
N = 4.2                     # 超椭圆指数，越大越方

C_TOP = (61, 155, 245)      # #3D9BF5 左上
C_BOT = (10, 58, 134)       # #0A3A86 右下
C_LINE = (255, 255, 255, 40)  # 内描边

# Z 字形（相对 0~1 的归一化坐标）
Z_BARS = [
    (0.275, 0.295, 0.725, 0.355),   # 上横
    (0.275, 0.645, 0.725, 0.705),   # 下横
]
Z_DIAG = [(0.725, 0.345), (0.725, 0.415), (0.325, 0.655), (0.275, 0.655),
          (0.275, 0.585), (0.675, 0.345)]


def in_squircle(x, y):
    """以中心为原点的超椭圆判定，x/y 取值 -1~1。"""
    return abs(x) ** N + abs(y) ** N <= 1.0


def in_poly(px, py, pts):
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / float(yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def lerp(a, b, t):
    return a + (b - a) * t


def shade(u, v, round_icon):
    """u,v ∈ [0,1] 归一化坐标，返回 (r,g,b,a)。"""
    x = (u - 0.5) * 2
    y = (v - 0.5) * 2
    if round_icon:
        if x * x + y * y > 1.0:
            return (0, 0, 0, 0)
    else:
        if not in_squircle(x, y):
            return (0, 0, 0, 0)

    # 对角渐变：左上亮 → 右下深
    t = max(0.0, min(1.0, (u * 0.55 + v * 0.75)))
    r = lerp(C_TOP[0], C_BOT[0], t)
    g = lerp(C_TOP[1], C_BOT[1], t)
    b = lerp(C_TOP[2], C_BOT[2], t)

    # 左上柔光（径向，白 0.16 递减）
    d = ((u - 0.18) ** 2 + (v - 0.10) ** 2) ** 0.5
    gloss = max(0.0, 1.0 - d / 0.85) ** 2 * 0.30
    r = lerp(r, 255, gloss)
    g = lerp(g, 255, gloss)
    b = lerp(b, 255, gloss)

    # 右下轻微反光，避免整块死沉
    d2 = ((u - 0.88) ** 2 + (v - 0.96) ** 2) ** 0.5
    glow = max(0.0, 1.0 - d2 / 0.55) ** 2 * 0.12
    r = lerp(r, 255, glow)
    g = lerp(g, 255, glow)
    b = lerp(b, 255, glow)

    # 内描边（1.6% 边长）
    edge = min(u, v, 1 - u, 1 - v)
    if not round_icon:
        # squircle 边缘距离用近似：超椭圆值越接近 1 越靠边
        e = abs((u - 0.5) * 2) ** N + abs((v - 0.5) * 2) ** N
        if e > 0.985:
            r = lerp(r, 255, 0.22)
            g = lerp(g, 255, 0.22)
            b = lerp(b, 255, 0.22)
    else:
        rad = (x * x + y * y) ** 0.5
        if rad > 0.985:
            r = lerp(r, 255, 0.22)
            g = lerp(g, 255, 0.22)
            b = lerp(b, 255, 0.22)

    # Z 投影
    sx, sy = u, v - 0.016
    shadow = False
    for x0, y0, x1, y1 in Z_BARS:
        if x0 <= sx <= x1 and y0 <= sy <= y1:
            shadow = True
            break
    if not shadow and in_poly(sx, sy, Z_DIAG):
        shadow = True

    # Z 主体
    solid = False
    for x0, y0, x1, y1 in Z_BARS:
        if x0 <= u <= x1 and y0 <= v <= y1:
            solid = True
            break
    if not solid and in_poly(u, v, Z_DIAG):
        solid = True

    if solid:
        return (255, 255, 255, 255)
    if shadow:
        r = lerp(r, 4, 0.16)
        g = lerp(g, 14, 0.16)
        b = lerp(b, 30, 0.16)
    return (int(r), int(g), int(b), 255)


def render(size, round_icon=False):
    """返回 RGBA bytes（size*size*4），超采样后平均。"""
    big = size * SS
    acc = [[[0, 0, 0, 0] for _ in range(size)] for _ in range(size)]
    for Y in range(big):
        v = (Y + 0.5) / big
        row = Y // SS
        for X in range(big):
            u = (X + 0.5) / big
            r, g, b, a = shade(u, v, round_icon)
            cell = acc[row][X // SS]
            cell[0] += r * a
            cell[1] += g * a
            cell[2] += b * a
            cell[3] += a
    out = bytearray()
    n = SS * SS
    for y in range(size):
        for x in range(size):
            sr, sg, sb, sa = acc[y][x]
            if sa == 0:
                out += bytes((0, 0, 0, 0))
            else:
                out += bytes((sr // sa, sg // sa, sb // sa, sa // n))
    return bytes(out)


def write_png(path, size, round_icon=False):
    rgba = render(size, round_icon)
    rows = []
    stride = size * 4
    for y in range(size):
        rows.append(b"\x00" + rgba[y * stride:(y + 1) * stride])
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


DENS = [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)]

if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "res")
    for dens, size in DENS:
        p1 = os.path.join(base, "mipmap-" + dens, "ic_launcher.png")
        p2 = os.path.join(base, "mipmap-" + dens, "ic_launcher_round.png")
        n1 = write_png(p1, size, False)
        n2 = write_png(p2, size, True)
        print("%-8s %3dpx  %6dB / %6dB" % (dens, size, n1, n2))
