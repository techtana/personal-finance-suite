"""Draw the app icon in every size the PWA manifest, iOS and browsers ask for.

    python scripts/make_icons.py

Writes static/icons/. The design: a rising net-worth line over a soft area on a dark
navy tile. "any" icons have rounded corners; maskable and Apple icons are full-bleed
with the mark inside the safe zone, because the platform applies its own mask.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static" / "icons"
NAVY_TOP, NAVY_BOTTOM = (30, 41, 59), (15, 23, 42)
LINE = (147, 197, 253)       # blue-300
AREA = (59, 130, 246, 95)    # blue-500, translucent
DOT = (167, 139, 250)        # violet-400, the "guidance" accent
GRID = (148, 163, 184, 45)
POINTS = [(0.10, 0.70), (0.36, 0.48), (0.55, 0.58), (0.90, 0.22)]
SCALE = 4                    # draw large, then downsample for smooth edges


def _gradient(size):
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(NAVY_TOP, NAVY_BOTTOM))
        draw.line([(0, y), (size, y)], fill=color + (255,))
    return img


def _mark(img, box):
    """Draw the chart mark inside box = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pts = [(x0 + px * w, y0 + py * h) for px, py in POINTS]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    base = y0 + 0.86 * h
    for frac in (0.30, 0.58):
        gy = y0 + frac * h
        draw.line([(x0, gy), (x1, gy)], fill=GRID, width=max(1, round(w * 0.012)))
    draw.polygon(pts + [(pts[-1][0], base), (pts[0][0], base)], fill=AREA)
    img.alpha_composite(layer)
    draw = ImageDraw.Draw(img)
    width = max(2, round(w * 0.075))
    draw.line(pts, fill=LINE, width=width, joint="curve")
    r = width / 2
    sx, sy = pts[0]
    draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=LINE)
    ex, ey = pts[-1]
    dr = w * 0.085
    draw.ellipse([ex - dr - width * 0.45, ey - dr - width * 0.45, ex + dr + width * 0.45, ey + dr + width * 0.45],
                 fill=NAVY_BOTTOM)
    draw.ellipse([ex - dr, ey - dr, ex + dr, ey + dr], fill=DOT)


def render(size, *, rounded, inset):
    big = size * SCALE
    img = _gradient(big)
    pad = big * inset
    _mark(img, (pad, pad, big - pad, big - pad))
    if rounded:
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1], radius=big * 0.22, fill=255)
        img.putalpha(mask)
    return img.resize((size, size), Image.LANCZOS)


def svg():
    """The same mark as a scalable favicon."""
    s, pad = 64, 64 * 0.16
    w = s - 2 * pad
    pts = [(pad + px * w, pad + py * w) for px, py in POINTS]
    base = pad + 0.86 * w
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = line + f" {pts[-1][0]:.1f},{base:.1f} {pts[0][0]:.1f},{base:.1f}"
    ex, ey = pts[-1]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1e293b"/><stop offset="1" stop-color="#0f172a"/></linearGradient></defs>
<rect width="64" height="64" rx="14" fill="url(#g)"/>
<polygon points="{area}" fill="#3b82f6" fill-opacity=".37"/>
<polyline points="{line}" fill="none" stroke="#93c5fd" stroke-width="{w * 0.075:.1f}" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{w * 0.085 + w * 0.034:.1f}" fill="#0f172a"/>
<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{w * 0.085:.1f}" fill="#a78bfa"/>
</svg>
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        render(size, rounded=True, inset=0.16).save(OUT / f"icon-{size}.png", optimize=True)
    for size in (96,):
        render(size, rounded=True, inset=0.14).save(OUT / f"icon-{size}.png", optimize=True)
    # Maskable: the platform crops to a circle or squircle; keep the mark in the middle 60%.
    render(512, rounded=False, inset=0.24).save(OUT / "maskable-512.png", optimize=True)
    render(192, rounded=False, inset=0.24).save(OUT / "maskable-192.png", optimize=True)
    # iOS rounds corners itself and shows transparency as black, so this one is opaque.
    render(180, rounded=False, inset=0.18).convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)
    render(32, rounded=True, inset=0.10).save(OUT / "favicon-32.png", optimize=True)
    (OUT / "favicon.svg").write_text(svg(), encoding="utf-8")
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
