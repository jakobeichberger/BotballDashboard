#!/usr/bin/env python3
"""Render the PWA PNG icons from the app logo (public/icons/app-icon.svg).

The logo is simple geometry, so it is redrawn here with Pillow instead of
pulling in an SVG rasterizer. Keep the shapes in sync with app-icon.svg.

    python3 frontend/scripts/generate-icons.py

Writes into frontend/public/:
  icons/icon-192.png, icons/icon-512.png  – "any" purpose, rounded tile
  icons/icon-maskable-512.png             – full-bleed, logo inside the 80 % safe zone
  apple-touch-icon.png (180×180)          – full-bleed, iOS rounds the corners itself
  favicon.ico (16/32/48)
"""

from pathlib import Path

from PIL import Image, ImageDraw

BLUE = (37, 99, 235, 255)  # #2563eb
WHITE = (255, 255, 255, 255)
SUPERSAMPLE = 4
PUBLIC = Path(__file__).resolve().parent.parent / "public"


def _robot(draw: ImageDraw.ImageDraw, scale: float, offset: float) -> None:
    """The robot face of app-icon.svg (512-unit viewBox), scaled and shifted."""

    def p(value: float) -> float:
        return offset + value * scale

    def box(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (p(x0), p(y0), p(x1), p(y1))

    # Antenna (drawn first so the head covers its base)
    draw.line([(p(256), p(148)), (p(256), p(92))], fill=WHITE, width=round(26 * scale))
    draw.ellipse(box(230, 46, 282, 98), fill=WHITE)
    # Head
    draw.rounded_rectangle(box(104, 148, 408, 388), radius=56 * scale, fill=WHITE)
    # Eyes
    draw.ellipse(box(166, 234, 226, 294), fill=BLUE)
    draw.ellipse(box(286, 234, 346, 294), fill=BLUE)
    # Mouth with round caps
    width = 28 * scale
    draw.line([(p(176), p(336)), (p(336), p(336))], fill=BLUE, width=round(width))
    for x in (176, 336):
        draw.ellipse(
            (p(x) - width / 2, p(336) - width / 2, p(x) + width / 2, p(336) + width / 2),
            fill=BLUE,
        )


def render(size: int, *, maskable: bool = False, rounded: bool = True) -> Image.Image:
    canvas = size * SUPERSAMPLE
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if rounded and not maskable:
        draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=canvas * 112 / 512, fill=BLUE)
    else:
        draw.rectangle((0, 0, canvas, canvas), fill=BLUE)
    # Maskable icons may be cropped to a circle of 80 % diameter: shrink the
    # logo so the antenna and head stay inside that safe zone.
    content = 0.72 if maskable else 1.0
    scale = canvas / 512 * content
    offset = canvas * (1 - content) / 2
    _robot(draw, scale, offset)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    icons = PUBLIC / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    render(192).save(icons / "icon-192.png", optimize=True)
    render(512).save(icons / "icon-512.png", optimize=True)
    render(512, maskable=True).save(icons / "icon-maskable-512.png", optimize=True)
    render(180, rounded=False).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    render(48).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"Icons written to {PUBLIC}")


if __name__ == "__main__":
    main()
