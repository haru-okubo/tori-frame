"""Compose Spectra 6 frames: 1-3 bird panels or an idle screen.

Default layout is "full": the painting fills the whole screen (portrait 480x800 by
default, rotated onto the physically landscape 800x480 panel) with only a tiny
signature in a corner. The older "classic" layout (800x480, big caption) remains.

Artwork is dithered per panel (so dither noise never bleeds into the paper
margin); captions and hairlines are drawn afterwards directly in palette
indices, so text stays crisp black on the white "paper".
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from birdframe import palette as pal
from birdframe.art import ArtCatalog, Artwork, crop_window
from birdframe.species import PACKAGE_ROOT

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 800, 480
ARTISTS_CSV = PACKAGE_ROOT / "data" / "artworks" / "artists.csv"

# Noto Serif CJK JP (SIL OFL 1.1). Debian/Raspberry Pi OS: `apt install fonts-noto-cjk`.
DEFAULT_FONTS = {
    "regular": [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifJP-Regular.otf",
    ],
    "bold": [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifJP-Bold.otf",
    ],
    # small metadata text: sans survives 1-bit thresholding better at 13-14 px
    "sans": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf",
    ],
}
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
SEASON_JA = {"spring": "春", "summer": "夏", "autumn": "秋", "winter": "冬"}


@dataclass(frozen=True)
class PanelSpec:
    wamei: str
    scientific_name: str = ""


@dataclass(frozen=True)
class IdleInfo:
    """What to show when no bird is present."""

    species: PanelSpec
    reason: str  # "last_seen" | "seasonal"
    when: dt.datetime | None = None
    season: str = ""


@dataclass
class Frame:
    indices: Image.Image  # "L", values 0..5
    panels: list[PanelSpec] = field(default_factory=list)
    idle: IdleInfo | None = None
    artworks: list[str] = field(default_factory=list)
    rotation: int = 0  # degrees CCW applied to `indices` to get the 800x480 panel image

    def device_image(self) -> Image.Image:
        img = pal.to_device_image(self.indices)
        if self.rotation % 360:
            img = img.transpose({90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180,
                                 270: Image.Transpose.ROTATE_270}[self.rotation % 360])
        return img

    def preview(self) -> Image.Image:
        return pal.to_preview(self.indices)


class Fonts:
    def __init__(self, regular: list[str] | None = None, bold: list[str] | None = None,
                 sans: list[str] | None = None):
        self._reg = self._find(regular or DEFAULT_FONTS["regular"])
        self._bold = self._find(bold or DEFAULT_FONTS["bold"]) or self._reg
        self._sans = self._find(sans or DEFAULT_FONTS["sans"]) or self._reg
        if not self._reg:
            log.warning("No Japanese serif font found; install fonts-noto-cjk")
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    @staticmethod
    def _find(paths: list[str]) -> str | None:
        return next((p for p in paths if Path(p).exists()), None)

    def get(self, size: int, bold: bool = False, sans: bool = False) -> ImageFont.ImageFont:
        path = self._sans if sans else (self._bold if bold else self._reg)
        if not path:
            return ImageFont.load_default(size)
        key = (path, size)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(path, size, index=0)  # index 0 = JP
        return self._cache[key]


def _artist_ja() -> dict[str, str]:
    if not ARTISTS_CSV.exists():
        return {}
    with ARTISTS_CSV.open(encoding="utf-8") as f:
        return {r["artist"]: r["artist_ja"] for r in csv.DictReader(f)}


def _short_source(art: Artwork) -> str:
    s = art.source_museum
    if "Metropolitan" in s:
        s = "The Met"
    elif "National Diet Library" in s:
        s = "国立国会図書館"
    elif "Cleveland" in s:
        s = "Cleveland Museum of Art"
    elif "Rijksmuseum" in s:
        s = "Rijksmuseum"
    elif "Wikimedia" in s:
        s = "Wikimedia Commons"
    lic = "CC0" if "CC0" in art.license else "Public domain"
    return f"{s} · {lic}"


class FrameRenderer:
    def __init__(
        self,
        catalog: ArtCatalog,
        fonts: Fonts | None = None,
        *,
        method: pal.DitherMethod = "vivid",
        saturation: float = 0.5,
        color_boost: float = 1.5,
        contrast: float = 1.1,
        gamma: float = 1.3,
        max_aspect: float = 0.72,
        mount: bool = True,
        layout: str = "full",          # "full" (painting fills screen) | "classic"
        orientation: str = "portrait",  # "portrait" (480x800 logical) | "landscape" (800x480)
        rotation: int = 90,            # portrait only: 90 or 270 (degrees CCW logical -> panel)
        signature: bool = True,
        signature_size: int = 15,
        signature_corner: str = "br",  # tl|tr|bl|br
        art_context: float = 1.7,
    ):
        self.catalog = catalog
        self.fonts = fonts or Fonts()
        self.method = method
        self.saturation = saturation
        self.color_boost = color_boost
        self.contrast = contrast
        self.gamma = gamma
        self.max_aspect = max_aspect  # w/h: keep a hanging-scroll proportion
        self.mount = mount
        self.artist_ja = _artist_ja()
        if layout not in ("full", "classic"):
            raise ValueError(f"layout must be full|classic, got {layout!r}")
        if orientation not in ("portrait", "landscape"):
            raise ValueError(f"orientation must be portrait|landscape, got {orientation!r}")
        if rotation not in (90, 270):
            raise ValueError("rotation must be 90 or 270")
        self.layout = layout
        self.orientation = "landscape" if layout == "classic" else orientation
        self.rotation = rotation if self.orientation == "portrait" else 0
        self.width, self.height = (HEIGHT, WIDTH) if self.orientation == "portrait" else (WIDTH, HEIGHT)
        self.signature = signature
        self.signature_size = signature_size
        self.signature_corner = signature_corner
        self.art_context = art_context

    # ------------------------------------------------------------------ API
    def render(self, panels: list[PanelSpec], idle: IdleInfo | None = None,
               day: dt.date | None = None) -> Frame:
        W, H = self.width, self.height
        canvas = np.full((H, W), pal.WHITE, dtype=np.uint8)
        text = Image.new("L", (W, H), 0)  # 255 = black ink
        frame = Frame(indices=Image.new("L", (1, 1)), panels=list(panels), idle=idle,
                      rotation=self.rotation)
        if self.layout == "full":
            specs = [idle.species] if idle is not None else list(panels[:3])
            if not specs:
                raise ValueError("nothing to render")
            self._layout_full(canvas, text, specs, day, frame)
        elif idle is not None:
            self._layout_single(canvas, text, idle.species, day, frame, idle=idle)
        elif len(panels) == 1:
            self._layout_single(canvas, text, panels[0], day, frame)
        else:
            self._layout_multi(canvas, text, panels[:3], day, frame)
        ink = np.asarray(text) >= 96  # slightly bold threshold keeps thin serifs
        canvas[ink] = pal.BLACK
        frame.indices = Image.fromarray(canvas, "L")
        return frame

    # -------------------------------------------------------------- layouts
    def _layout_full(self, canvas, text, specs: list[PanelSpec], day, frame: Frame) -> None:
        """Painting fills the whole screen (1-3 birds stacked along the long side)."""
        W, H = self.width, self.height
        n = len(specs)
        # stack along the long axis; thin white gap between panels when n > 1
        gap = 6 if n > 1 else 0
        along = (max(W, H) - gap * (n - 1)) // n
        for i, spec in enumerate(specs):
            if self.orientation == "portrait":
                rect = (0, i * (along + gap), W, along)
            else:
                rect = (i * (along + gap), 0, along, H)
            art = self._place_art(canvas, text, spec, rect, day, bleed=True, solo=(n == 1))
            if art:
                frame.artworks.append(art.artwork_id)
            if self.signature:
                self._sign(canvas, text, spec, art, rect)

    def _sign(self, canvas, text, spec: PanelSpec, art: Artwork | None, rect) -> None:
        """Tiny caption (bird name + artist) on a small paper-white plate in a corner."""
        x, y, w, h = rect
        d = ImageDraw.Draw(text)
        f = self.fonts.get(self.signature_size)
        s = spec.wamei
        if art:
            artist = self.artist_ja.get(art.artist, art.artist).split("(")[0].strip()
            s += "　" + artist
        limit = int(w * 0.62)
        while len(s) > 2 and d.textlength(s, font=f) > limit:
            s = s[:-2] + "…"
        tw = int(d.textlength(s, font=f))
        th = self.signature_size + 4
        pad, margin = 5, 8
        pw, ph = tw + 2 * pad, th + 2 * pad - 2
        c = self.signature_corner
        px = x + margin if c[1] == "l" else x + w - margin - pw
        py = y + margin if c[0] == "t" else y + h - margin - ph
        canvas[py : py + ph, px : px + pw] = pal.WHITE
        d.text((px + pad, py + pad - 2), s, font=f, fill=255)

    def _layout_single(self, canvas, text, spec: PanelSpec, day, frame: Frame,
                       idle: IdleInfo | None = None) -> None:
        art_h = 420
        art_w = int(art_h * self.max_aspect)
        ax, ay = 104, (HEIGHT - art_h) // 2
        art = self._place_art(canvas, text, spec, (ax, ay, art_w, art_h), day)
        if art:
            frame.artworks.append(art.artwork_id)

        d = ImageDraw.Draw(text)
        x = ax + art_w + 64
        right = WIDTH - 48
        y = 120
        if idle is not None:
            if idle.reason == "last_seen" and idle.when:
                label = f"最後に見た鳥　{idle.when.month}月{idle.when.day}日 {idle.when:%H:%M}"
            else:
                label = f"{SEASON_JA.get(idle.season, '')}の鳥"
            d.text((x, y - 44), "いまは静かです", font=self.fonts.get(18), fill=255)
            d.text((x, y - 18), label, font=self.fonts.get(16), fill=255)
            y += 20
        f_name = self.fonts.get(46, bold=True)
        d.text((x, y), spec.wamei, font=f_name, fill=255)
        y += 64
        # small red seal next to the rule
        d.line([(x, y), (right, y)], fill=255, width=1)
        canvas[y - 7 : y + 7, right - 14 : right] = pal.RED
        y += 16
        if spec.scientific_name:
            d.text((x, y), spec.scientific_name, font=self.fonts.get(16), fill=255)
            y += 34
        if art:
            artist = self.artist_ja.get(art.artist, art.artist)
            d.text((x, y), artist, font=self.fonts.get(22), fill=255)
            y += 36
            for line in self._wrap(d, art.title, self.fonts.get(16), right - x, 3):
                d.text((x, y), line, font=self.fonts.get(16), fill=255)
                y += 24
            if art.date:
                d.text((x, y + 2), art.date, font=self.fonts.get(14, sans=True), fill=255)
            d.text((x, HEIGHT - ay - 18), _short_source(art), font=self.fonts.get(13, sans=True), fill=255)
        else:
            d.text((x, y), "（絵は準備中）", font=self.fonts.get(18), fill=255)

    def _layout_multi(self, canvas, text, specs: list[PanelSpec], day, frame: Frame) -> None:
        n = len(specs)
        outer, gutter = 28, 28
        slot_w = (WIDTH - 2 * outer - (n - 1) * gutter) // n
        top, cap_h, bottom = 22, 78, 10
        art_h = HEIGHT - top - cap_h - bottom
        art_w = min(slot_w, int(art_h * self.max_aspect))
        d = ImageDraw.Draw(text)
        for i, spec in enumerate(specs):
            sx = outer + i * (slot_w + gutter)
            ax = sx + (slot_w - art_w) // 2
            art = self._place_art(canvas, text, spec, (ax, top, art_w, art_h), day)
            if art:
                frame.artworks.append(art.artwork_id)
            cy = top + art_h + 12
            cx = sx + slot_w // 2
            self._center(d, cx, cy, spec.wamei, self.fonts.get(26, bold=True))
            if art:
                artist = self.artist_ja.get(art.artist, art.artist)
                self._center(d, cx, cy + 36, artist, self.fonts.get(15))
                f_small = self.fonts.get(13, sans=True)
                title = self._wrap(d, art.title, f_small, slot_w, 1)[0]
                self._center(d, cx, cy + 57, title, f_small)
            else:
                self._center(d, cx, cy + 36, "（絵は準備中）", self.fonts.get(15))

    # --------------------------------------------------------------- pieces
    def _place_art(self, canvas, text, spec: PanelSpec, rect, day, bleed: bool = False,
                   solo: bool = False) -> Artwork | None:
        x, y, w, h = rect
        ordered = self.catalog.pick_ordered(spec.scientific_name, spec.wamei, day=day)
        if solo:  # one bird on the whole screen: skip pictures flagged as unsuited (diving poses)
            ordered = [a for a in ordered if a.solo] or ordered
        art = ordered[0] if ordered else None
        if bleed and len(ordered) > 1:  # prefer a painting whose bird fits the tall crop uncut
            art = next((a for a in ordered if self._fits(a, w / h)), art)

        if art is None:
            self._placeholder(text, spec, rect)
            return None
        img = self.catalog.load(art)
        if bleed:
            tile = self._cover_tile(img, art, w / h).resize((w, h), Image.Resampling.LANCZOS)
        else:
            win = crop_window(img.size, art.box, aspect=w / h, clip=art.clip)
            tile = img.crop(win)
            tile.thumbnail((w, h), Image.Resampling.LANCZOS)
        idx = np.asarray(
            pal.quantize(tile, method=self.method, saturation=self.saturation,
                         color_boost=self.color_boost, contrast=self.contrast,
                         gamma=self.gamma)
        )
        ox, oy = x + (w - tile.width) // 2, y + (h - tile.height) // 2
        canvas[oy : oy + tile.height, ox : ox + tile.width] = idx
        if self.mount and not bleed:  # hairline "hyōsō" mount line around the painting
            ImageDraw.Draw(text).rectangle(
                [ox - 6, oy - 6, ox + tile.width + 5, oy + tile.height + 5], outline=255, width=1
            )
        return art

    def _fits(self, art: Artwork, aspect: float) -> bool:
        if art.box is None:
            return True
        img = self.catalog.load(art)
        W0, H0 = img.size
        win = crop_window(img.size, art.box, aspect=aspect, clip=art.clip, context=self.art_context)
        bx0, by0, bx1, by1 = art.box[0] * W0, art.box[1] * H0, art.box[2] * W0, art.box[3] * H0
        inside = (min(win[2], bx1) - max(win[0], bx0)) * (min(win[3], by1) - max(win[1], by0))
        return inside >= 0.985 * (bx1 - bx0) * (by1 - by0)

    def _cover_tile(self, img: Image.Image, art: Artwork, aspect: float) -> Image.Image:
        """Image tile of exactly `aspect` (w/h) that fills the rect and never cuts the bird.

        Normal case: a crop window around the bird (context shrinks step by step when the
        bird is large for the print). If even a tight window cannot hold the whole bird
        (wide bird in a landscape print, tall bird in a wide tile), take the strip of the
        print that contains the whole bird and extend it with flat paper tone on the
        short side (plain margins), softly blended at the seam.
        """
        W0, H0 = img.size
        self.last_plan = None
        if art.box is None:
            win = crop_window(img.size, None, aspect=aspect, clip=art.clip, context=self.art_context)
            self.last_plan = ("crop", win, 1.0)
            return img.crop(win)
        bx0, by0, bx1, by1 = art.box[0] * W0, art.box[1] * H0, art.box[2] * W0, art.box[3] * H0
        barea = (bx1 - bx0) * (by1 - by0)

        def covered(win) -> float:
            inside = (min(win[2], bx1) - max(win[0], bx0)) * (min(win[3], by1) - max(win[1], by0))
            return inside / barea

        ctx = self.art_context
        while ctx >= 1.06:
            win = crop_window(img.size, art.box, aspect=aspect, clip=art.clip, context=ctx)
            if covered(win) >= 0.985:
                self.last_plan = ("crop", win, 1.0)
                return img.crop(win)
            ctx = round(ctx - 0.15, 3) if ctx > 1.2 else round(ctx - 0.07, 3)
        cx0, cy0, cx1, cy1 = art.clip if art.clip else (0.0, 0.0, 1.0, 1.0)
        cl, ct, cr, cb = cx0 * W0, cy0 * H0, cx1 * W0, cy1 * H0
        bw, bh = bx1 - bx0, by1 - by0
        # strip of the print holding the whole bird (+12 %), then pad the short axis
        w2 = min(cr - cl, bw * 1.12)
        h2 = min(cb - ct, bh * 1.12)
        left = min(max((bx0 + bx1) / 2 - w2 / 2, cl), cr - w2)
        top = min(max((by0 + by1) / 2 - h2 / 2, ct), cb - h2)
        if w2 / aspect >= h2:   # too wide for the aspect -> use full-height strip, pad top/bottom
            h2 = cb - ct
            top = ct
            strip = img.crop((int(left), int(top), int(left + w2), int(top + h2)))
            need_h = int(round(strip.width / aspect))
            extra = max(need_h - strip.height, 0)
            bird_c = (by0 + by1) / 2 - top
            share = min(max(1 - bird_c / strip.height, 0.2), 0.8)
            pad = (0, 0, int(extra * share), extra - int(extra * share))   # l,r,t,b
        else:                   # too tall -> full-width strip, pad left/right
            w2 = cr - cl
            left = cl
            strip = img.crop((int(left), int(top), int(left + w2), int(top + h2)))
            need_w = int(round(strip.height * aspect))
            extra = max(need_w - strip.width, 0)
            bird_c = (bx0 + bx1) / 2 - left
            share = min(max(1 - bird_c / strip.width, 0.2), 0.8)
            pad = (int(extra * share), extra - int(extra * share), 0, 0)
        if sum(pad) == 0:  # no padding needed after all: centred window around the bird
            win = crop_window(img.size, art.box, aspect=aspect, clip=art.clip, context=1.0)
            self.last_plan = ("crop", win, covered(win))
            return img.crop(win)
        self.last_plan = ("pad", (int(left), int(top), int(left + strip.width), int(top + strip.height)), 1.0)
        arr = np.asarray(strip).astype(np.float32)
        pl, pr, pt, pb = pad
        # pad tone = median of the picture's outer 8 px on the padded sides, so the
        # extension continues the paper colour of the print
        edges = []
        if pt: edges.append(arr[:8].reshape(-1, 3))
        if pb: edges.append(arr[-8:].reshape(-1, 3))
        if pl: edges.append(arr[:, :8].reshape(-1, 3))
        if pr: edges.append(arr[:, -8:].reshape(-1, 3))
        paper = np.median(np.concatenate(edges), axis=0)
        out = np.empty((arr.shape[0] + pt + pb, arr.shape[1] + pl + pr, 3), dtype=np.float32)
        out[:] = paper
        out[pt : pt + arr.shape[0], pl : pl + arr.shape[1]] = arr
        seam = 24
        for i in range(seam):  # fade picture edge into paper
            t = (i + 1) / (seam + 1)
            if pt:
                out[pt + i, pl : pl + arr.shape[1]] = out[pt + i, pl : pl + arr.shape[1]] * t + paper * (1 - t)
            if pb:
                j = pt + arr.shape[0] - 1 - i
                out[j, pl : pl + arr.shape[1]] = out[j, pl : pl + arr.shape[1]] * t + paper * (1 - t)
            if pl:
                out[pt : pt + arr.shape[0], pl + i] = out[pt : pt + arr.shape[0], pl + i] * t + paper * (1 - t)
            if pr:
                j = pl + arr.shape[1] - 1 - i
                out[pt : pt + arr.shape[0], j] = out[pt : pt + arr.shape[0], j] * t + paper * (1 - t)
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    def _placeholder(self, text, spec: PanelSpec, rect) -> None:
        x, y, w, h = rect
        d = ImageDraw.Draw(text)
        d.rectangle([x, y, x + w - 1, y + h - 1], outline=255, width=1)
        f = self.fonts.get(max(24, min(48, w // 5)), bold=True)
        self._center(d, x + w // 2, y + h // 2 - 30, spec.wamei, f)

    @staticmethod
    def _center(d: ImageDraw.ImageDraw, cx: int, y: int, s: str, font) -> None:
        w = d.textlength(s, font=font)
        d.text((cx - w / 2, y), s, font=font, fill=255)

    @staticmethod
    def _wrap(d: ImageDraw.ImageDraw, s: str, font, width: int, max_lines: int) -> list[str]:
        words, lines, cur = s.split(), [], ""
        for wd in words:
            trial = f"{cur} {wd}".strip()
            if d.textlength(trial, font=font) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            while lines[-1] and d.textlength(lines[-1] + "…", font=font) > width:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
        # hard-truncate single over-long words
        out = []
        for ln in lines or [""]:
            while ln and d.textlength(ln, font=font) > width:
                ln = ln[:-2] + "…"
            out.append(ln)
        return out


def season_of(day: dt.date) -> str:
    return SEASONS[day.month]
