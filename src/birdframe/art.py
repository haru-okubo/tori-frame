"""Artwork catalog: species -> public-domain paintings, crop windows, image cache."""

from __future__ import annotations

import csv
import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from PIL import Image, ImageOps

from birdframe.species import PACKAGE_ROOT

Image.MAX_IMAGE_PIXELS = None  # some museum scans are > 89 MP

DEFAULT_CATALOG = PACKAGE_ROOT / "data" / "artworks" / "artworks.csv"
DEFAULT_CROPS = PACKAGE_ROOT / "data" / "artworks" / "crops.yaml"
DEFAULT_ORIGINALS = PACKAGE_ROOT / "assets" / "originals"
DEFAULT_CACHE = PACKAGE_ROOT / "assets" / "cache"

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
_IMG_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")


@dataclass(frozen=True)
class Artwork:
    artwork_id: str
    wamei: str
    scientific_name: str
    title: str
    artist: str
    date: str
    source_museum: str
    license: str
    confidence: str
    box: tuple[float, float, float, float] | None  # bird region, normalized
    # Optional usable area (normalized): the display window never leaves it. Used for
    # scans whose margins carry colour charts, rulers or the facing page.
    clip: tuple[float, float, float, float] | None = None
    solo: bool = True  # False: bird pose unsuited to a full-screen single picture (e.g. diving)
    style: str = "kachoga"  # see ART_STYLES


# Art styles (artworks.csv `style` column):
#   kachoga         - Japanese bird-and-flower prints/paintings and Edo bird albums
#   natural_history - scientific colour plates (Fauna Japonica, Gould, Naumann, ...)
ART_STYLES = ("kachoga", "natural_history")
STYLE_MODES = ("rotate", "prefer")


class ArtCatalog:
    def __init__(
        self,
        catalog: Path = DEFAULT_CATALOG,
        crops: Path = DEFAULT_CROPS,
        originals: Path = DEFAULT_ORIGINALS,
        cache_dir: Path = DEFAULT_CACHE,
        min_confidence: str = "medium",
        cache_max_side: int = 1600,
        styles: Sequence[str] | None = None,
        style_mode: str = "rotate",
    ):
        """`styles`: which art styles to show (None = all). `style_mode`:
        "rotate" mixes all allowed styles day by day; "prefer" uses the first style in
        `styles` that has art for the species and falls back to the next one."""
        if style_mode not in STYLE_MODES:
            raise ValueError(f"style_mode must be one of {STYLE_MODES}, got {style_mode!r}")
        unknown = set(styles or ()) - set(ART_STYLES)
        if unknown:
            raise ValueError(f"unknown art style(s) {sorted(unknown)}; known: {ART_STYLES}")
        self.styles = tuple(styles) if styles else None
        self.style_mode = style_mode
        self.originals = Path(originals)
        self.cache_dir = Path(cache_dir)
        self.cache_max_side = cache_max_side
        boxes = yaml.safe_load(Path(crops).read_text(encoding="utf-8")) if Path(crops).exists() else {}
        boxes = boxes or {}
        floor = CONFIDENCE_RANK[min_confidence]
        self.by_sci: dict[str, list[Artwork]] = {}
        self.by_wamei: dict[str, list[Artwork]] = {}
        with Path(catalog).open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if CONFIDENCE_RANK.get(r["species_confidence"], 0) < floor:
                    continue
                style = (r.get("style") or "kachoga").strip()
                if self.styles is not None and style not in self.styles:
                    continue
                b = boxes.get(r["artwork_id"])
                art = Artwork(
                    artwork_id=r["artwork_id"],
                    wamei=r["wamei"],
                    scientific_name=r["scientific_name"],
                    title=r["title"],
                    artist=r["artist"],
                    date=r["date"],
                    source_museum=r["source_museum"],
                    license=r["license"],
                    confidence=r["species_confidence"],
                    box=(b["x0"], b["y0"], b["x1"], b["y1"]) if b else None,
                    clip=tuple(b["clip"]) if b and b.get("clip") else None,
                    style=style,
                    solo=bool(b.get("solo", True)) if b else True,
                )
                if self.original_path(art) is None:
                    continue  # not downloaded yet
                self.by_sci.setdefault(art.scientific_name, []).append(art)
                self.by_wamei.setdefault(art.wamei, []).append(art)
        for lst in list(self.by_sci.values()) + list(self.by_wamei.values()):
            lst.sort(key=lambda a: -CONFIDENCE_RANK[a.confidence])

    def candidates(self, scientific_name: str = "", wamei: str = "") -> list[Artwork]:
        return self.by_sci.get(scientific_name) or self.by_wamei.get(wamei) or []

    def pick_ordered(self, scientific_name: str = "", wamei: str = "",
                     day: dt.date | None = None) -> list[Artwork]:
        """All best-confidence artworks for the species, rotated so the one `pick` would
        choose for `day` comes first (lets a renderer prefer one that fits its layout)."""
        cands = self.candidates(scientific_name, wamei)
        if not cands:
            return []
        if self.style_mode == "prefer" and self.styles:
            for st in self.styles:
                same = [a for a in cands if a.style == st]
                if same:
                    cands = same
                    break
        top = CONFIDENCE_RANK[cands[0].confidence]
        best = [a for a in cands if CONFIDENCE_RANK[a.confidence] == top]
        day = day or dt.date.today()
        k = day.toordinal() % len(best)
        return best[k:] + best[:k]

    def pick(self, scientific_name: str = "", wamei: str = "", day: dt.date | None = None) -> Artwork | None:
        """Best-confidence artworks, rotated by day so the frame varies over time."""
        ordered = self.pick_ordered(scientific_name, wamei, day)
        return ordered[0] if ordered else None

    def original_path(self, art: Artwork) -> Path | None:
        for ext in _IMG_EXT:
            p = self.originals / f"{art.artwork_id}{ext}"
            if p.exists():
                return p
        return None

    def load(self, art: Artwork) -> Image.Image:
        """Downscaled RGB copy (cached on disk; keeps Pi 4 RAM use low)."""
        return _load_cached(str(self.original_path(art)), str(self.cache_dir), self.cache_max_side)


@lru_cache(maxsize=16)
def _load_cached(src: str, cache_dir: str, max_side: int) -> Image.Image:
    srcp = Path(src)
    cdir = Path(cache_dir)
    cached = cdir / f"{srcp.resolve().stem}_{max_side}.jpg"
    if cached.exists() and cached.stat().st_mtime >= srcp.resolve().stat().st_mtime:
        return Image.open(cached).convert("RGB")
    with Image.open(srcp) as im:
        im.draft("RGB", (max_side, max_side))  # fast JPEG downscale on decode
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    cdir.mkdir(parents=True, exist_ok=True)
    im.save(cached, quality=92)
    return im


def crop_window(
    size: tuple[int, int],
    box: tuple[float, float, float, float] | None,
    aspect: float,
    context: float = 1.7,
    clip: tuple[float, float, float, float] | None = None,
) -> tuple[int, int, int, int]:
    """Window of the given aspect (w/h) around the bird box, inside the image.

    The bird box is grown by `context` so the bird sits in its branch/flowers,
    as a hanging-scroll detail rather than a tight crop. If `clip` (normalized)
    is given, the window is kept inside that region instead of the whole image.
    """
    W0, H0 = size
    cx0, cy0, cx1, cy1 = clip if clip else (0.0, 0.0, 1.0, 1.0)
    ox, oy = cx0 * W0, cy0 * H0
    W, H = (cx1 - cx0) * W0, (cy1 - cy0) * H0
    if box is None:
        box = (cx0, cy0, cx1, cy1)
    x0, y0, x1, y1 = box[0] * W0 - ox, box[1] * H0 - oy, box[2] * W0 - ox, box[3] * H0 - oy
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw, bh = (x1 - x0) * context, (y1 - y0) * context
    h = max(bh, bw / aspect)
    w = h * aspect
    # fit inside image, keeping aspect
    if w > W:
        w, h = W, W / aspect
    if h > H:
        h, w = H, H * aspect
    left = min(max(cx - w / 2, 0), W - w) + ox
    top = min(max(cy - h / 2, 0), H - h) + oy
    return int(left), int(top), int(left + w), int(top + h)
