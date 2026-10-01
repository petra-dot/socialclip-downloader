"""Generate the SocialClip Downloader app icon (flat, minimal, no gradients).

Run:  python assets/make_icon.py

Produces assets/icon_512.png and a multi-size assets/icon.ico.
Deterministic and dependency-light (Pillow only); re-run to regenerate.
"""

import os

from PIL import Image, ImageDraw

# Flat palette: one background, one accent, one foreground. No gradients.
BACKGROUND = (24, 32, 40, 255)      # deep slate
ACCENT = (45, 212, 191, 255)        # teal (kept close to the previous brand)
FOREGROUND = (236, 244, 246, 255)   # near-white

CANVAS = 512


def _rounded_square(size, radius, fill):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=fill)
    return img


def _arrow(draw, size):
    """A chunky download arrow: thick stem, wide head, centered."""
    cx = size // 2
    stem_w = int(size * 0.16)
    stem_top = int(size * 0.24)
    stem_bottom = int(size * 0.52)
    head_w = int(size * 0.46)
    head_top = int(size * 0.48)
    head_bottom = int(size * 0.74)

    # stem
    draw.rectangle(
        (cx - stem_w // 2, stem_top, cx + stem_w // 2, stem_bottom),
        fill=ACCENT,
    )
    # head (triangle)
    draw.polygon(
        [
            (cx - head_w // 2, head_top),
            (cx + head_w // 2, head_top),
            (cx, head_bottom),
        ],
        fill=ACCENT,
    )


def _tray(draw, size):
    """A flat baseline the arrow lands in, reading as 'saved to disk'."""
    margin = int(size * 0.24)
    y = int(size * 0.82)
    thickness = int(size * 0.07)
    draw.rounded_rectangle(
        (margin, y, size - margin, y + thickness),
        radius=thickness // 2,
        fill=FOREGROUND,
    )


def build_icon(size=CANVAS):
    radius = int(size * 0.22)
    icon = _rounded_square(size, radius, BACKGROUND)
    draw = ImageDraw.Draw(icon)
    _arrow(draw, size)
    _tray(draw, size)
    return icon


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(here, "icon_512.png")
    ico_path = os.path.join(here, "icon.ico")

    master = build_icon(CANVAS)
    master.save(png_path)
    print("wrote", png_path)

    # Windows wants real sizes, not one downscaled bitmap.
    sizes = [16, 24, 32, 48, 64, 128, 256]
    master.save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print("wrote", ico_path, "sizes", sizes)


if __name__ == "__main__":
    main()
