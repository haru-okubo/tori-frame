#!/usr/bin/env python3
"""Download artwork originals listed in data/artworks/artworks.csv.

Saves under assets/originals/{artwork_id}.{ext}
Skips files that already exist unless --force.
Dedupes identical image_url across multiple species rows (same bytes, one file
plus optional symlink aliases for secondary artwork_ids that share a URL).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "artworks" / "artworks.csv"
OUT_DIR = ROOT / "assets" / "originals"
MANIFEST = OUT_DIR / "download_manifest.csv"

UA = "bird-frame/0.1 (local prototype; educational; +https://github.com/)"


def ext_from_url_or_ctype(url: str, ctype: str | None) -> str:
    path = url.split("?")[0]
    if path.lower().endswith((".jpg", ".jpeg")):
        return ".jpg"
    if path.lower().endswith(".png"):
        return ".png"
    if path.lower().endswith((".tif", ".tiff")):
        return ".tif"
    if path.lower().endswith(".webp"):
        return ".webp"
    if ctype:
        ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or ""
        if ext == ".jpe":
            ext = ".jpg"
        if ext:
            return ext
    return ".jpg"


def download(url: str, dest: Path, timeout: int = 120) -> tuple[Path, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type")
        data = resp.read()
    if not dest.suffix:
        dest = dest.with_suffix(ext_from_url_or_ctype(url, ctype))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    return dest, digest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="Max unique URLs (0=all)")
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    # primary artwork_id per URL = first occurrence
    by_url: dict[str, list[dict]] = {}
    for row in rows:
        by_url.setdefault(row["image_url"], []).append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    n = 0
    for url, group in by_url.items():
        if args.limit and n >= args.limit:
            break
        primary = group[0]["artwork_id"]
        # prefer existing any extension
        existing = list(args.out.glob(f"{primary}.*"))
        existing = [p for p in existing if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}]
        if existing and not args.force:
            dest = existing[0]
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            print(f"skip {primary} ({dest.name})")
        else:
            tmp = args.out / primary
            try:
                dest, digest = download(url, tmp)
                print(f"got  {primary} -> {dest.name} ({dest.stat().st_size} bytes)")
                time.sleep(0.3)
            except Exception as e:
                print(f"FAIL {primary}: {e}", file=sys.stderr)
                for row in group:
                    manifest_rows.append(
                        {
                            "artwork_id": row["artwork_id"],
                            "wamei": row["wamei"],
                            "path": "",
                            "sha256": "",
                            "image_url": url,
                            "status": f"error:{e}",
                        }
                    )
                continue
        n += 1
        for i, row in enumerate(group):
            aid = row["artwork_id"]
            path = dest
            if i > 0:
                # alias file pointing at same bytes (copy symlink if possible)
                alias = dest.with_name(f"{aid}{dest.suffix}")
                if not alias.exists() or args.force:
                    if alias.exists():
                        alias.unlink()
                    try:
                        alias.symlink_to(dest.name)
                    except OSError:
                        alias.write_bytes(dest.read_bytes())
                path = alias
            manifest_rows.append(
                {
                    "artwork_id": aid,
                    "wamei": row["wamei"],
                    "path": str(path.relative_to(ROOT)),
                    "sha256": digest,
                    "image_url": url,
                    "status": "ok",
                }
            )

    fields = ["artwork_id", "wamei", "path", "sha256", "image_url", "status"]
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(manifest_rows)
    print(f"manifest -> {MANIFEST} ({len(manifest_rows)} rows, {n} unique downloads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
