"""Version 2 of tiles 1 and 6, redrawn from the component chart of ผ้าลายนครธรรม
(ดอกมณีเทวา, เขาภูพาน, ข้าวพันก้อน). Same output format as make_patterns.py:
white cells on transparent, no fade baked in."""
import sys
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent)
CELL = 3
N = 25          # motif box (odd so it has a centre cell)
C = N // 2
R = 11          # diamond outline radius


def blank(w, h):
    return [["."] * w for _ in range(h)]


def put(g, x, y):
    if 0 <= y < len(g) and 0 <= x < len(g[0]):
        g[y][x] = "#"


def clear(g, x, y):
    if 0 <= y < len(g) and 0 <= x < len(g[0]):
        g[y][x] = "."


def blob(g, cx, cy, r=2):
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if abs(dx) + abs(dy) <= r:
                put(g, cx + dx, cy + dy)


def outline(g):
    for y in range(N):
        for x in range(N):
            if abs(x - C) + abs(y - C) == R:
                put(g, x, y)


def flower():
    """ดอกมณีเทวา: diamond frame; inside a horizontal stem through a ring, buds above and below."""
    g = blank(N, N)
    outline(g)
    for x in range(N):
        if 3 <= abs(x - C) <= 8:
            put(g, x, C)
    for y in range(N):
        for x in range(N):
            if abs(x - C) + abs(y - C) == 2:
                put(g, x, y)
    for dy in (3, 4):
        put(g, C, C - dy); put(g, C, C + dy)
    blob(g, C, C - 6); blob(g, C, C + 6)
    return g


def mountain(h=13):
    """เขาภูพาน: nested stepped peaks, striped foothills inside, small cross at the foot."""
    g = blank(N, h)
    for y in range(h):
        for x in range(N):
            dx = abs(x - C)
            t = y - dx
            if dx >= C:
                continue
            if 0 <= t < 6 and t % 4 in (0, 1):
                put(g, x, y)
            if y >= 7 and t >= 6 and (x - C) % 2 == 0:
                put(g, x, y)
    for y in range(9, h):
        for x in range(C - 2, C + 3):
            clear(g, x, y)
    for x, y in ((C, 10), (C - 1, 11), (C, 11), (C + 1, 11), (C, 12)):
        put(g, x, y)
    return g


def rice():
    """ข้าวพันก้อน: diamond filled with a lattice of small squares, four rice balls, ring at the centre."""
    g = blank(N, N)
    outline(g)
    for y in range(N):
        for x in range(N):
            dx, dy = x - C, y - C
            if abs(dx) + abs(dy) < R - 1 and ((dx + dy) % 4 == 0 or (dx - dy) % 4 == 0):
                put(g, x, y)
    for cx, cy in ((C, C - 6), (C, C + 6), (C - 6, C), (C + 6, C)):
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                if abs(dx) + abs(dy) <= 3:
                    clear(g, cx + dx, cy + dy)
        blob(g, cx, cy)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            clear(g, C + dx, C + dy)
    for x, y in ((C, C - 1), (C, C + 1), (C - 1, C), (C + 1, C)):
        put(g, x, y)
    return g


def stack(*parts, gap=1):
    out = []
    for i, p in enumerate(parts):
        if i:
            out += [["."] * N for _ in range(gap)]
        out += p
    out += [["."] * N for _ in range(gap)]
    return out


def to_svg(name, g, title):
    h, w = len(g), len(g[0])
    d = []
    for y, row in enumerate(g):
        x = 0
        while x < w:
            if row[x] == "#":
                s = x
                while x < w and row[x] == "#":
                    x += 1
                d.append(f"M{s*CELL} {y*CELL}h{(x-s)*CELL}v{CELL}h-{(x-s)*CELL}z")
            else:
                x += 1
    (OUT / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*CELL}" height="{h*CELL}" viewBox="0 0 {w*CELL} {h*CELL}" '
        f'shape-rendering="crispEdges"><title>{title}</title><path fill="#fff" d="{"".join(d)}"/></svg>\n',
        encoding="utf-8")
    print(name, w * CELL, h * CELL)


to_svg("nakhontham-flower-mountain-v2", stack(flower(), mountain()), "ดอกมณีเทวาและเขาภูพาน (ตามแผ่นองค์ประกอบผ้าลายนครธรรม)")
to_svg("khao-phan-kon-rice-v2", stack(rice()), "ลายข้าวพันก้อน (ตามแผ่นองค์ประกอบผ้าลายนครธรรม)")
