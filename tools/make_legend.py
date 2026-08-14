#!/usr/bin/env python3
"""Render the width legend from the default style.

The Portolan browser derives a legend only from a `fill` layer whose
`fill-color` is a `match` or `step` expression. This collection is lines, so it
derives nothing, and the legend has to ship as an image.

Colours and breaks are read out of `styles/default.json` rather than repeated
here, so the legend cannot drift from the style it describes. Change the style
and re-run this.

    python3 tools/make_legend.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STYLE = ROOT / "catalog" / "road-detections" / "styles" / "default.json"
OUTPUT = ROOT / "catalog" / "road-detections" / "legends" / "width.png"

TITLE = "Road width (metres)"
SCALE = 2  # Rendered at 2x and downsampled, so the text is not aliased.

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def read_step_expression() -> list[tuple[str, str]]:
    """(label, colour) per class, from the step expression on line-color."""
    style = json.loads(STYLE.read_text())
    layer = next(layer for layer in style["layers"] if layer["type"] == "line")
    expression = layer["paint"]["line-color"]
    if not (isinstance(expression, list) and expression[0] == "step"):
        raise SystemExit("line-color is not a step expression; nothing to legend")

    default_colour = expression[2]
    pairs = expression[3:]
    breaks = [pairs[i] for i in range(0, len(pairs), 2)]
    colours = [pairs[i] for i in range(1, len(pairs), 2)]

    entries = [(f"< {breaks[0]:g}", default_colour)]
    for i, colour in enumerate(colours):
        low = breaks[i]
        if i + 1 < len(breaks):
            entries.append((f"{low:g} to {breaks[i + 1]:g}", colour))
        else:
            entries.append((f"{low:g} and above", colour))
    return entries


def render(entries: list[tuple[str, str]]) -> Image.Image:
    font = load_font(13 * SCALE)
    title_font = load_font(14 * SCALE)

    pad = 12 * SCALE
    swatch_w, swatch_h = 26 * SCALE, 6 * SCALE
    gap = 8 * SCALE
    row_h = 22 * SCALE

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    label_w = max(
        int(measure.textbbox((0, 0), label, font=font)[2]) for label, _ in entries
    )
    title_w = int(measure.textbbox((0, 0), TITLE, font=title_font)[2])

    width = max(pad * 2 + swatch_w + gap + label_w, pad * 2 + title_w)
    height = pad * 2 + int(row_h * 1.4) + row_h * len(entries)

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.text((pad, pad), TITLE, font=title_font, fill="#111111")

    y = pad + int(row_h * 1.4)
    for label, colour in entries:
        cy = y + (row_h - swatch_h) // 2
        draw.rounded_rectangle(
            [pad, cy, pad + swatch_w, cy + swatch_h],
            radius=swatch_h // 2,
            fill=colour,
        )
        draw.text(
            (pad + swatch_w + gap, y + (row_h - 15 * SCALE) // 2),
            label,
            font=font,
            fill="#333333",
        )
        y += row_h

    draw.rectangle([0, 0, width - 1, height - 1], outline="#d8d8d8")
    return image.resize((width // SCALE, height // SCALE), Image.LANCZOS)


def main() -> int:
    entries = read_step_expression()
    image = render(entries)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, "PNG", optimize=True)
    print(f"wrote {OUTPUT.relative_to(ROOT)}  {image.width}x{image.height}px"
          f"  {OUTPUT.stat().st_size} bytes")
    for label, colour in entries:
        print(f"  {colour}  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
