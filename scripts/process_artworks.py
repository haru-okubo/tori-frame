#!/usr/bin/env python3
"""Colour (Spectra 6) contact sheet of every catalogued artwork crop.

Uses the same crop window + dithering as the live renderer, so this is a
QA view of exactly what each painting will look like on the panel.

  python scripts/process_artworks.py [--dither vivid|fs] [--min-confidence low]
  -> out/contact_sheet.png

Only some items (e.g. a review sheet of newly catalogued art):

  python scripts/process_artworks.py --new-since HEAD --out out/contact_sheet_new.png
  python scripts/process_artworks.py --ids met_45024,ndl_baien_higara --out out/x.png
  python scripts/process_artworks.py --style natural_history --out out/contact_sheet_natural_history.png
"""
from __future__ import annotations

import argparse
import csv
import io
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from birdframe import palette as pal
from birdframe.art import ArtCatalog, crop_window
from birdframe.render import Fonts

ROOT = Path(__file__).resolve().parents[1]
CSV_REL = "data/artworks/artworks.csv"


def ids_added_since(rev: str) -> set[str]:
    """artwork_ids present in the working-tree catalog but not in git revision `rev`."""
    old_text = subprocess.run(["git", "show", f"{rev}:{CSV_REL}"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout
    old = {r["artwork_id"] for r in csv.DictReader(io.StringIO(old_text))}
    new = {r["artwork_id"] for r in csv.DictReader((ROOT / CSV_REL).open(encoding="utf-8"))}
    return new - old


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "contact_sheet.png")
    ap.add_argument("--dither", choices=["vivid", "fs", "none"], default="vivid")
    ap.add_argument("--min-confidence", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--ids", default="", help="Comma-separated artwork_ids to include (default: all)")
    ap.add_argument("--style", action="append", default=None,
                    help="Only this art style (repeatable): kachoga, natural_history")
    ap.add_argument("--new-since", metavar="REV", default="",
                    help="Only artworks added to artworks.csv since git revision REV")
    args = ap.parse_args()

    wanted: set[str] | None = None
    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
    if args.new_since:
        added = ids_added_since(args.new_since)
        wanted = added if wanted is None else wanted & added

    cat = ArtCatalog(min_confidence=args.min_confidence, styles=args.style)
    arts = sorted({a.artwork_id: a for lst in cat.by_wamei.values() for a in lst}.values(),
                  key=lambda a: (a.wamei, a.artwork_id))
    if wanted is not None:
        arts = [a for a in arts if a.artwork_id in wanted]
    if not arts:
        print("no artworks selected")
        return 1
    fonts = Fonts()
    tw, th, cap = 170, 236, 44
    rows = (len(arts) + args.cols - 1) // args.cols
    sheet = Image.new("RGB", (args.cols * (tw + 12) + 12, rows * (th + cap) + 12), "white")
    d = ImageDraw.Draw(sheet)
    for i, a in enumerate(arts):
        img = cat.load(a)
        tile = img.crop(crop_window(img.size, a.box, aspect=tw / th, clip=a.clip))
        tile.thumbnail((tw, th), Image.Resampling.LANCZOS)
        prev = pal.to_preview(pal.quantize(tile, method=args.dither))
        x = 12 + (i % args.cols) * (tw + 12)
        y = 12 + (i // args.cols) * (th + cap)
        sheet.paste(prev, (x + (tw - prev.width) // 2, y))
        d.text((x, y + th + 2), f"{a.wamei} [{a.confidence}]", font=fonts.get(14, bold=True), fill="black")
        d.text((x, y + th + 21), a.artwork_id[:28], font=fonts.get(11, sans=True), fill=(80, 80, 80))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, optimize=True)
    print(f"{args.out}: {len(arts)} artworks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
