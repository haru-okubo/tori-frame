#!/usr/bin/env python3
"""Download Perch v2 artifacts used by birdframe.

Default runtime model: ernensbjorn/perch-v2-int8-tflite perch_v2_dynint8.tflite
  - Apache-2.0 TFLite conversion of Google's official SavedModel (dynamic-range int8)
  - ~105 MB; ~0.6 GB peak RSS on the box vs ~1.75 GB for fp16 -> fits Pi 4 2GB
  - same predictions as fp16 on the 31-clip local eval (docs/eval_int8_vs_fp16.txt)

Also fetches official Google labels + eBird code side-car from the public
Chirp GCS bucket (same assets shipped with the Kaggle model).

Optional: attempt Kaggle perch_v2_cpu SavedModel via kagglehub (may require
credentials). Conversion notes for Pi are printed at the end.
"""

from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "data" / "models"
RAW = ROOT / "data" / "raw"

GCS_LABELS = "https://storage.googleapis.com/chirp-public-bucket/models/perch_v2/assets/labels.csv"
GCS_EBIRD = (
    "https://storage.googleapis.com/chirp-public-bucket/models/perch_v2/assets/perch_v2_ebird_classes.csv"
)
HF_REPO = "ernensbjorn/perch-v2-int8-tflite"


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"  -> {dest} ({dest.stat().st_size} bytes)")


def download_tflite(variant: str = "perch_v2_dynint8.tflite") -> Path:
    from huggingface_hub import hf_hub_download

    MODELS.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(repo_id=HF_REPO, filename=variant, local_dir=str(MODELS))
    # Also save a short provenance note
    note = MODELS / "MODEL_SOURCE.txt"
    note.write_text(
        f"file: {variant}\n"
        f"repo: https://huggingface.co/{HF_REPO}\n"
        f"license: Apache-2.0 (conversion of Google Perch v2 SavedModel)\n"
        f"upstream: https://www.kaggle.com/models/google/bird-vocalization-classifier\n"
        f"official labels: {GCS_LABELS}\n",
        encoding="utf-8",
    )
    print(f"TFLite: {path}")
    return Path(path)


def try_kaggle_cpu() -> Path | None:
    try:
        import kagglehub
    except ImportError:
        print("kagglehub not installed; skip official SavedModel download")
        return None
    try:
        root = kagglehub.model_download(
            "google/bird-vocalization-classifier/tensorFlow2/perch_v2_cpu"
        )
        print(f"Kaggle perch_v2_cpu at: {root}")
        dest = MODELS / "perch_v2_cpu_savedmodel"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(root, dest)
        return dest
    except Exception as e:
        print(f"Kaggle download failed (auth may be required): {e}")
        return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--variant",
        default="perch_v2_dynint8.tflite",
        choices=[
            "perch_v2_fp16.tflite",
            "perch_v2_original.tflite",
            "perch_v2_dynint8.tflite",
        ],
    )
    p.add_argument("--try-kaggle", action="store_true")
    args = p.parse_args()

    fetch(GCS_LABELS, RAW / "perch_v2_labels.csv")
    fetch(GCS_EBIRD, RAW / "perch_v2_ebird_classes.csv")
    download_tflite(args.variant)
    # Ensure TFLite-aligned labels.txt (strip GCS leading taxonomy tag if needed)
    labels_txt = MODELS / "labels.txt"
    if not labels_txt.is_file():
        raw = (RAW / "perch_v2_labels.csv").read_text(encoding="utf-8").splitlines()
        if raw and raw[0].strip() == "inat2024_fsd50k":
            raw = raw[1:]
        labels_txt.write_text("\n".join(raw) + "\n", encoding="utf-8")
        print(f"wrote {labels_txt} ({len(raw)} classes)")
    if args.try_kaggle:
        try_kaggle_cpu()

    print(
        """
Runtime notes (Raspberry Pi 4/5, 64-bit Raspberry Pi OS)
-------------------------------------------------------
Default: perch_v2_dynint8.tflite via ai-edge-litert (aarch64 wheels, cp310-cp314).
No conversion step needed. fp16 (--variant perch_v2_fp16.tflite) needs ~1.75 GB RAM.

If you prefer the official Kaggle TF SavedModel (perch_v2_cpu):
  pip install kagglehub tensorflow
  python -c "import kagglehub; print(kagglehub.model_download(
      'google/bird-vocalization-classifier/tensorFlow2/perch_v2_cpu'))"

To convert SavedModel -> TFLite yourself (on an x86 machine with TF):
  converter = tf.lite.TFLiteConverter.from_saved_model(path)
  converter.optimizations = []  # or [tf.lite.Optimize.DEFAULT] for dynint8
  # for fp16:
  converter.optimizations = [tf.lite.Optimize.DEFAULT]
  converter.target_spec.supported_types = [tf.float16]
  open('perch_v2_fp16.tflite','wb').write(converter.convert())

ONNX alternative (community, Apache-2.0): justinchuby/Perch-onnx on Hugging Face
  + onnxruntime on Pi (aarch64 wheels available).
"""
    )


if __name__ == "__main__":
    main()
