#!/usr/bin/env python3
"""Download curated Xeno-canto clips for local testing only (NOT committed).

Species identity is verified via HTTP Content-Disposition on /<id>/download.
Many XC licenses are CC BY-NC-*; local evaluation only — do not redistribute.
IDs live in samples/xc_ids.tsv.
"""

from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples" / "xc"
IDS = ROOT / "samples" / "xc_ids.tsv"
UA = "Mozilla/5.0 (compatible; birdframe-local-eval/0.1)"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for line in IDS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        rows.append((parts[0], parts[1], parts[2]))

    manifest = [
        "# Local-only Xeno-canto test clips (do NOT commit audio).",
        "# Species verified via HTTP Content-Disposition on /<id>/download.",
        "# Many XC licenses are CC BY-NC-*; local evaluation only — do not redistribute.",
        "# file\texpected_sci\texpected_wamei\txc_id",
    ]
    for xc_id, sci, wamei in rows:
        req = urllib.request.Request(
            f"https://xeno-canto.org/{xc_id}/download",
            method="HEAD",
            headers={"User-Agent": UA},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            cd = r.headers.get("Content-Disposition", "")
        ext = ".wav" if ".wav" in cd.lower() else ".mp3"
        raw = OUT / f"XC{xc_id}_{sci.replace(' ', '_')}{ext}"
        wav = OUT / f"XC{xc_id}_{sci.replace(' ', '_')}_15s.wav"
        if not raw.exists() or raw.stat().st_size < 1000:
            print(f"DL XC{xc_id}")
            req2 = urllib.request.Request(
                f"https://xeno-canto.org/{xc_id}/download",
                headers={"User-Agent": UA},
            )
            with urllib.request.urlopen(req2, timeout=120) as r, open(raw, "wb") as f:
                f.write(r.read())
        if not wav.exists() or wav.stat().st_size < 1000:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(raw), "-t", "15", "-ac", "1", "-ar", "32000", str(wav)],
                check=True,
                capture_output=True,
            )
        manifest.append(f"{wav.relative_to(ROOT)}\t{sci}\t{wamei}\tXC{xc_id}")
        print(f"  {wav.name}")
    man = ROOT / "samples" / "MANIFEST.txt"
    man.write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"wrote {man} ({len(rows)} clips)")


if __name__ == "__main__":
    main()
