"""Spectra 6 (Inky Impression 7.3" 2025 / E673) palette quantization.

Palette values are taken verbatim from Pimoroni's `inky` library
(inky/inky_e673.py, MIT License, Copyright (c) 2018 Pimoroni Ltd.):

- DESATURATED_PALETTE: the pure colours the panel is driven with.
- SATURATED_PALETTE: Pimoroni's approximation of how the inks actually look.

inky's own `set_image()` dithers against a blend of the two (default
saturation=0.5). We do the dithering ourselves (so we can pre-process the
artwork and draw crisp text afterwards) and hand inky a "P" image with exactly
six pure colours, which makes inky skip its own dithering.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from PIL import Image, ImageEnhance

# Sequential order used by inky's quantizer (index -> colour name).
NAMES = ("black", "white", "yellow", "red", "blue", "green")
BLACK, WHITE, YELLOW, RED, BLUE, GREEN = range(6)

DESATURATED_PALETTE = [
    (0, 0, 0),
    (255, 255, 255),
    (255, 255, 0),
    (255, 0, 0),
    (0, 0, 255),
    (0, 255, 0),
]
SATURATED_PALETTE = [
    (0, 0, 0),
    (161, 164, 165),
    (208, 190, 71),
    (156, 72, 75),
    (61, 59, 94),
    (58, 91, 70),
]

DitherMethod = Literal["fs", "vivid", "none"]


def blend_palette(saturation: float) -> list[tuple[int, int, int]]:
    """Same blend as inky's Inky._palette_blend()."""
    s = float(saturation)
    out = []
    for sat, des in zip(SATURATED_PALETTE, DESATURATED_PALETTE):
        out.append(tuple(int(a * s + b * (1.0 - s)) for a, b in zip(sat, des)))
    return out


def preview_palette() -> list[tuple[int, int, int]]:
    """Colours for on-screen simulation PNGs.

    Pimoroni's measured SATURATED_PALETTE, scaled per channel so that the
    panel's white maps to 255 (a monitor shows the paper as white; relative
    ink colours are kept). This is an approximation, not a colorimetric proof.
    """
    w = SATURATED_PALETTE[WHITE]
    return [
        tuple(min(255, round(c * 255 / wc)) for c, wc in zip(col, w))
        for col in SATURATED_PALETTE
    ]


def _palette_image(colors: list[tuple[int, int, int]]) -> Image.Image:
    pal = Image.new("P", (1, 1))
    flat = [v for c in colors for v in c]
    pal.putpalette(flat + flat[:3] * (256 - len(colors)))  # pad with black
    return pal


def paper_white_balance(img: Image.Image, paper_pct: float = 92.0, black_pct: float = 0.5) -> Image.Image:
    """Map aged paper tone to white and stretch levels per channel.

    Antique prints have beige/grey paper; without this the dither sprinkles
    yellow/green dots over the whole background.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    lum = a.mean(axis=2)
    bright = a[lum >= np.percentile(lum, paper_pct)]
    paper = np.median(bright, axis=0) if bright.size else np.array([255, 255, 255], np.float32)
    lo = np.percentile(a.reshape(-1, 3), black_pct, axis=0)
    scale = 255.0 / np.maximum(paper - lo, 1.0)
    out = np.clip((a - lo) * scale, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def prepare(img: Image.Image, method: DitherMethod, *, color_boost: float = 1.5,
            contrast: float = 1.1, gamma: float = 1.3) -> Image.Image:
    img = img.convert("RGB")
    if method == "vivid":
        img = paper_white_balance(img)
        if gamma != 1.0:  # darken mid-tones: panel white is dull, pale pigments vanish
            lut = [round(255 * (i / 255) ** gamma) for i in range(256)] * 3
            img = img.point(lut)
        img = ImageEnhance.Color(img).enhance(color_boost)
        img = ImageEnhance.Contrast(img).enhance(contrast)
    return img


def quantize(img: Image.Image, *, method: DitherMethod = "vivid", saturation: float = 0.5,
             color_boost: float = 1.5, contrast: float = 1.1, gamma: float = 1.3) -> Image.Image:
    """Return an "L" image of palette indices 0..5 (same size as input).

    - fs:    Floyd–Steinberg against inky's blended palette (== inky default).
    - vivid: paper white-balance + gamma + saturation/contrast boost, then FS.
    - none:  nearest colour, no dithering (for flat graphics / text).
    """
    src = prepare(img, method, color_boost=color_boost, contrast=contrast, gamma=gamma)
    dither = Image.Dither.NONE if method == "none" else Image.Dither.FLOYDSTEINBERG
    q = src.quantize(palette=_palette_image(blend_palette(saturation)), dither=dither)
    idx = np.asarray(q, dtype=np.uint8).copy()
    idx[idx > 5] = BLACK  # padding entries are black
    return Image.fromarray(idx, "L")


def to_device_image(indices: Image.Image) -> Image.Image:
    """Indices -> "P" image with exactly six pure colours (inky skips dithering)."""
    p = Image.fromarray(np.asarray(indices, dtype=np.uint8), "P")
    p.putpalette([v for c in DESATURATED_PALETTE for v in c])
    return p


def to_preview(indices: Image.Image) -> Image.Image:
    lut = np.array(preview_palette(), dtype=np.uint8)
    return Image.fromarray(lut[np.asarray(indices, dtype=np.uint8)], "RGB")

