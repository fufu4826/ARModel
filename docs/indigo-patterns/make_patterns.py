"""Generate seamless, single-colour indigo-cloth tiles (no fade baked in) as SVG.

Each motif is drawn on a weaving grid (like ขิด / มัดหมี่ charts): one '#' = one cell.
The fill is white on transparent, so the file works both as a background-image on a
dark surface and as a CSS mask (only alpha matters there).
"""
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
CELL = 3


def grid(text):
    rows = [r for r in text.strip("\n").split("\n")]
    w = max(len(r) for r in rows)
    return [list(r.ljust(w, ".")) for r in rows]


def mirror_h(g):
    return [r + r[::-1] for r in g]


def mirror_v(g):
    return g + g[::-1]


def half_drop(g):
    """Place the tile twice side by side, the right copy dropped by half its height (brick repeat)."""
    h = len(g)
    shift = h // 2
    return [g[y] + g[(y - shift) % h] for y in range(h)]


def to_svg(name, g, title):
    h, w = len(g), len(g[0])
    rects = []
    for y, row in enumerate(g):
        x = 0
        while x < w:
            if row[x] == "#":
                start = x
                while x < w and row[x] == "#":
                    x += 1
                rects.append(f"M{start*CELL} {y*CELL}h{(x-start)*CELL}v{CELL}h-{(x-start)*CELL}z")
            else:
                x += 1
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*CELL}" height="{h*CELL}" '
           f'viewBox="0 0 {w*CELL} {h*CELL}" shape-rendering="crispEdges">'
           f"<title>{title}</title><path fill=\"#fff\" d=\"{''.join(rects)}\"/></svg>\n")
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
    return w * CELL, h * CELL


# 1. เขาภูพาน + ดอกมณีเทวา (elements of ผ้าลายนครธรรม): stepped mountain band over a row of small flowers.
mountain = grid("""
............#...........
...........###..........
..........##.##.........
.........##...##........
........##..#..##.......
.......##..###..##......
......##..##.##..##.....
.....##..##...##..##....
....##..##.....##..##...
...##..##.......##..##..
..##..##.........##..##.
.##..##...........##..##
##..##.............##..#
#..##...............##..
........................
.....#...........#......
....###.........###.....
...##.##.......##.##....
....###.........###.....
.....#...........#......
........................
""")

# 2. ลายขอ (hook / meander) — spiral hook mirrored into a four-way diamond.
hook = mirror_v(mirror_h(grid("""
##########..
#........#..
#.######.#..
#.#....#.#..
#.#.##.#.#..
#.#.#..#.#..
#.#.####.#..
#.#......#..
#.########..
#...........
############
............
""")))

# 3. ลายต้นสน (pine tree), brick repeat.
pine = half_drop(grid("""
.....##.....
....####....
.....##.....
...######...
....####....
..########..
...######...
.##########.
.....##.....
.....##.....
....####....
............
............
............
"""))


# 4. ลายมัดหมี่ (ikat diamond) — feathered outline from the tie-dye bleed, centre eye.
def ikat(size=22, r=8):
    c = size // 2
    g = [["."] * size for _ in range(size)]
    bleed = [0, 1, 0, 2, 1, 0, 1, 2, 0, 1, 1]
    for y in range(size):
        for x in range(size):
            d = abs(x - c) + abs(y - c)
            if d in (r, r - 1):
                g[y][x] = "#"
            if d <= 2 and d != 1:
                g[y][x] = "#"
    # Horizontal bleed on the outer edge (weft-ikat look), deterministic.
    for y in range(size):
        dy = abs(y - c)
        if dy >= r:
            continue
        ext = bleed[y % len(bleed)]
        for side in (-1, 1):
            x0 = c + side * (r - dy)
            for k in range(1, ext + 1):
                xx = x0 + side * k
                if 0 <= xx < size:
                    g[y][xx] = "#"
    # Corner joints so diamonds link into a lattice.
    for x, y in ((0, c), (size - 1, c), (c, 0), (c, size - 1)):
        g[y][x] = "#"
    return g


# 5. ลายตุ้มทอง / กระดุมทอง — button rings on a diamond lattice of dots.
def buttons(size=16):
    g = [["."] * size for _ in range(size)]
    ring = [".###.", "#...#", "#.#.#", "#...#", ".###."]
    for cx, cy in ((0, 0), (size // 2, size // 2)):
        for j, row in enumerate(ring):
            for i, ch in enumerate(row):
                if ch == "#":
                    g[(cy - 2 + j) % size][(cx - 2 + i) % size] = "#"
    for k in range(3, size // 2 - 2):
        for x, y in ((k, k), (size - k, k), (k, size - k), (size - k, size - k)):
            if (k % 2) == 1:
                g[y % size][x % size] = "#"
    return g


# 6. ลายข้าวพันก้อน — little rice-ball clusters between woven stripes.
rice = half_drop(grid("""
................
......##........
.....####.......
......##........
....##..##......
...####.####....
....##..##......
................
................
################
................
################
................
................
"""))

PATTERNS = [
    ("nakhontham-mountain", mountain, "เขาภูพานและดอกมณีเทวา (จากผ้าลายนครธรรม)"),
    ("kho-hook", hook, "ลายขอ"),
    ("ton-son-pine", pine, "ลายต้นสน"),
    ("mudmee-ikat", ikat(), "ลายมัดหมี่ (เพชรขอบซึม)"),
    ("tum-thong-button", buttons(), "ลายตุ้มทอง / กระดุมทอง"),
    ("khao-phan-kon-rice", rice, "ลายข้าวพันก้อน"),
]
for name, g, title in PATTERNS:
    print(name, to_svg(name, g, title))
