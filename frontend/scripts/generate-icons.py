#!/usr/bin/env python3
"""Render the PWA PNG icons from the app logo (public/icons/app-icon.svg).

The logo is simple stroke geometry, so it is redrawn here with Pillow instead
of pulling in an SVG rasterizer. Keep the shapes in sync with app-icon.svg and
components/BrandMark.tsx (64-unit viewBox).

    python3 frontend/scripts/generate-icons.py

Writes into frontend/public/:
  icons/icon-192.png, icons/icon-512.png  – "any" purpose, rounded dark tile
  icons/icon-maskable-512.png             – full-bleed, logo inside the 80 % safe zone
  apple-touch-icon.png (180×180)          – full-bleed, iOS rounds the corners itself
  favicon.ico (16/32/48)                  – light tile, like the SVG favicon
"""

from pathlib import Path

from PIL import Image, ImageDraw

RED = (227, 24, 35, 255)  # #E31823 (--rot)
TIEF = (13, 15, 19, 255)  # #0D0F13 (--tief)
PAPIER = (242, 242, 242, 255)  # #F2F2F2 (--papier)
STROKE = 3.2
SUPERSAMPLE = 4
PUBLIC = Path(__file__).resolve().parent.parent / "public"

# Round-capped strokes of app-icon.svg: (x0, y0, x1, y1).
LINES = [
    (32, 17, 32, 11),  # antenna
    (8, 27, 8, 35),  # left ear
    (56, 27, 56, 35),  # right ear
    (26, 38, 38, 38),  # mouth
    (32, 45, 32, 50),  # neck
    (21, 52, 43, 52),  # base
]
# Filled dots: (cx, cy, r).
DOTS = [(32, 9, 3.4), (24.5, 29.5, 3.6), (39.5, 29.5, 3.6)]


def _mark(draw: ImageDraw.ImageDraw, scale: float, offset: float) -> None:
    """The robot mark (64-unit viewBox), scaled and shifted."""

    def p(value: float) -> float:
        return offset + value * scale

    width = STROKE * scale
    # Head outline (the SVG stroke is centred on the path: grow the box by half).
    half = width / 2
    draw.rounded_rectangle(
        (p(12) - half, p(17) - half, p(52) + half, p(45) + half),
        radius=8 * scale + half,
        outline=RED,
        width=round(width),
    )
    for x0, y0, x1, y1 in LINES:
        draw.line([(p(x0), p(y0)), (p(x1), p(y1))], fill=RED, width=round(width))
        for x, y in ((x0, y0), (x1, y1)):
            draw.ellipse((p(x) - half, p(y) - half, p(x) + half, p(y) + half), fill=RED)
    for cx, cy, r in DOTS:
        draw.ellipse((p(cx - r), p(cy - r), p(cx + r), p(cy + r)), fill=RED)


def render(
    size: int, *, maskable: bool = False, rounded: bool = True, tile: tuple = TIEF
) -> Image.Image:
    canvas = size * SUPERSAMPLE
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded and not maskable:
        draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=canvas * 14 / 64, fill=tile)
    else:
        draw.rectangle((0, 0, canvas, canvas), fill=tile)
    # Maskable icons may be cropped to a circle of 80 % diameter: shrink the
    # mark so the antenna and the ears stay inside that safe zone.
    content = 0.7 if maskable else 1.0
    scale = canvas / 64 * content
    offset = canvas * (1 - content) / 2
    _mark(draw, scale, offset)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    icons = PUBLIC / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    render(192).save(icons / "icon-192.png", optimize=True)
    render(512).save(icons / "icon-512.png", optimize=True)
    render(512, maskable=True).save(icons / "icon-maskable-512.png", optimize=True)
    render(180, rounded=False).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    render(48, tile=PAPIER).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"Icons written to {PUBLIC}")


if __name__ == "__main__":
    main()
