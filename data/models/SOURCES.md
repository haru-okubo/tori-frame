# Model provenance

## Runtime weights (committed policy: download, do not vendor large binaries)

| Artifact | Origin | License | Notes |
|----------|--------|---------|-------|
| `perch_v2_fp16.tflite` | Hugging Face `ernensbjorn/perch-v2-int8-tflite` | Apache-2.0 | Faithful TFLite conversion of Google Perch v2 SavedModel; Pi 5 friendly |
| `labels.csv` | Google Chirp GCS / Kaggle assets | Apache-2.0 | Official class list (~14,795) |
| `perch_v2_ebird_classes.csv` | same | Apache-2.0 | Parallel eBird codes |

Upstream model card: https://www.kaggle.com/models/google/bird-vocalization-classifier  
Paper: Perch 2.0 (arXiv:2508.04665)

### Not used

- BirdNET weights or code (non-commercial / incompatible for this product path)
- `tphakala` regional Japan ONNX slices (derived with BirdNET Geomodel range filters)

### Optional official SavedModel

`kagglehub.model_download("google/bird-vocalization-classifier/tensorFlow2/perch_v2_cpu")`  
May require a Kaggle account. See `scripts/download_model.py --try-kaggle`.
