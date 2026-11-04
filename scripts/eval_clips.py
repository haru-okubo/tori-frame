#!/usr/bin/env python3
"""Evaluate one or more Perch v2 TFLite variants on samples/MANIFEST.txt clips.

Clip prediction = garden species with the highest *summed* full-softmax
probability over all 5 s windows (hop 5 s). Same rule for every model, so the
numbers are directly comparable. Audio clips are local-only (XC licenses).

  python scripts/eval_clips.py --models data/models/perch_v2_fp16.tflite \
      data/models/perch_v2_dynint8.tflite --out docs/eval_int8_vs_fp16.txt
"""
from __future__ import annotations

import argparse
import resource
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from birdframe.audio import iter_windows, load_mono
from birdframe.classify import default_mask
from birdframe.model import PerchV2TFLite

ROOT = Path(__file__).resolve().parents[1]


def load_manifest(path: Path) -> list[tuple[Path, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f, _sci, wamei, _xc = line.split("\t")
        rows.append((ROOT / f, wamei))
    return rows


def run(model_path: Path, clips, threads: int):
    t_load = time.perf_counter()
    model = PerchV2TFLite(model_path, num_threads=threads)
    load_s = time.perf_counter() - t_load
    mask = default_mask()
    preds, times, top_probs = [], [], []
    for path, _exp in clips:
        wav = load_mono(path)
        acc: dict[str, float] = defaultdict(float)
        best_p = 0.0
        for _t, w in iter_windows(wav):
            t0 = time.perf_counter()
            logits = model.embed_logits(w)
            times.append((time.perf_counter() - t0) * 1000)
            for sp, _lg, p in mask.topk(logits, k=len(mask.species)):
                acc[sp.wamei] += p
            best_p = max(best_p, mask.topk(logits, k=1)[0][2])
        pred = max(acc, key=acc.get)
        preds.append(pred)
        top_probs.append(best_p)
    return {
        "preds": preds,
        "ms": np.array(times[1:] or times),  # drop first (warm-up)
        "load_s": load_s,
        "top_probs": top_probs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=ROOT / "samples" / "MANIFEST.txt")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    clips = [c for c in load_manifest(args.manifest) if c[0].is_file()]
    lines = [f"clips: {len(clips)}  threads: {args.threads}  rule: argmax sum(full_softmax) over windows, garden mask"]
    results = {}
    for m in args.models:
        r = run(m, clips, args.threads)
        results[m.name] = r
        correct = sum(p == e for p, (_, e) in zip(r["preds"], clips))
        lines.append(
            f"{m.name}: top1 {correct}/{len(clips)}  "
            f"latency ms/window mean {r['ms'].mean():.0f} p50 {np.median(r['ms']):.0f} "
            f"p95 {np.percentile(r['ms'], 95):.0f}  load {r['load_s']:.1f}s  "
            f"maxRSS so far {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB"
        )
    names = list(results)
    lines.append("")
    lines.append("file\texpected\t" + "\t".join(names))
    for i, (path, exp) in enumerate(clips):
        cells = [f"{results[n]['preds'][i]}({results[n]['top_probs'][i]:.2f})" for n in names]
        lines.append(f"{path.name.split('_')[0]}\t{exp}\t" + "\t".join(cells))
    if len(names) == 2:
        a, b = (results[n]["preds"] for n in names)
        agree = sum(x == y for x, y in zip(a, b))
        lines.insert(len(names) + 1, f"prediction agreement {names[0]} vs {names[1]}: {agree}/{len(clips)}")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
