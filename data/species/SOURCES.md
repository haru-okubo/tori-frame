# Species list provenance

## `species_japan.csv` / `species_japan_garden.csv`

Built by `scripts/build_species_japan.py`.

### Japan checklist (species universe)

- **Source:** 日本鳥学会『日本鳥類目録改訂第8版』掲載鳥類リスト Excel  
  `https://ornithology.jp/materials/checklist/jpbirdlist8ed_ver1.xlsx`  
  Linked from https://ornithology.jp/checklist.html
- **Terms (from the workbook “注意” sheet, Japanese):**
  - Created by the checklist editorial committee in accordance with the 8th edition.
  - Use is the user’s responsibility.
  - **Secondary processing / derivative use by the user is allowed.**
  - Referring to the published 8th edition book is recommended.
- **This project** keeps the raw Excel under `data/raw/` (gitignored) and commits only the
  derived CSV (scientific name, 和名, mapping columns). Attribution: Ornithological Society of Japan.

### Perch class index / eBird codes

- Official Perch v2 `labels.csv` and `perch_v2_ebird_classes.csv` from Google’s Chirp public bucket  
  (`storage.googleapis.com/chirp-public-bucket/models/perch_v2/assets/…`), Apache-2.0 model assets.
- Species are matched by scientific name (with an explicit synonym table for known IOC/iNaturalist
  taxonomy renames). **No BirdNET model, BirdNET code, or BirdNET-Geomodel range list is used.**

### English names

- Garden subset: curated common English names in the build script.
- Full Japan list: English left blank when not in the garden curated set (eBird/Clements CSV download
  was blocked by Cloudflare from this environment). Optional future fill from eBird Taxonomy
  (Cornell Lab; follow their terms when downloading).

### Garden subset

~30 common species in Japanese residential / garden / park settings, selected manually for the
prototype (スズメ, ヒヨドリ, メジロ, …). Not a statistical occurrence model.

### Perch index alignment (critical)

Official GCS `labels.csv` begins with a taxonomy tag line `inat2024_fsd50k` that is
**not** one of the 14,795 TFLite logit classes. `perch_index` in these CSVs is the
0-based index into `data/models/labels.txt` (identical to GCS labels with that first
line removed). Using the unstripped GCS file as index 0 shifts every species by +1
and silently breaks classification.
