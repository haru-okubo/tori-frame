#!/usr/bin/env python3
"""Build data/species/species_japan.csv from OSJ 8th-ed list × Perch labels.

Sources / licenses: see data/species/SOURCES.md
Does NOT use BirdNET or BirdNET-Geomodel region slices.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OSJ_XLSX = ROOT / "data" / "raw" / "jpbirdlist8ed_ver1.xlsx"
# Prefer HF/TFLite labels.txt (14,795 rows). Official GCS labels.csv has an
# extra leading taxonomy tag ("inat2024_fsd50k") that is NOT a model class;
# using it as index 0 shifts every perch_index by +1 vs the TFLite logits.
LABELS_TFLITE = ROOT / "data" / "models" / "labels.txt"
LABELS_GCS = ROOT / "data" / "raw" / "perch_v2_labels.csv"
EBIRD = ROOT / "data" / "raw" / "perch_v2_ebird_classes.csv"
OUT = ROOT / "data" / "species" / "species_japan.csv"
OUT_GARDEN = ROOT / "data" / "species" / "species_japan_garden.csv"

# OSJ scientific name -> Perch / iNaturalist label when taxonomies diverge.
# Only factual synonym redirects for matching; not a BirdNET geomodel list.
SYNONYMS: dict[str, str] = {
    "Anser cygnoid": "Anser cygnoides",
    "Charadrius dubius": "Thinornis dubius",
    "Charadrius alexandrinus": "Anarhynchus alexandrinus",
    "Charadrius mongolus": "Anarhynchus mongolus",
    "Charadrius leschenaultii": "Anarhynchus leschenaultii",
    "Charadrius veredus": "Anarhynchus veredus",
    "Ixobrychus sinensis": "Botaurus sinensis",
    "Ixobrychus eurhythmus": "Botaurus eurhythmus",
    "Ixobrychus cinnamomeus": "Botaurus cinnamomeus",
    "Ixobrychus flavicollis": "Botaurus flavicollis",
    "Accipiter gularis": "Tachyspiza gularis",
    "Accipiter soloensis": "Tachyspiza soloensis",
    "Accipiter gentilis": "Astur gentilis",
    "Hypotaenidia okinawae": "Gallirallus okinawae",
    "Bubulcus ibis": "Ardea ibis",
    "Corvus monedula": "Coloeus monedula",
    "Corvus dauuricus": "Coloeus dauuricus",
    "Locustella amnicola": "Helopsaltes amnicola",
    "Locustella pryeri": "Helopsaltes pryeri",
    "Locustella certhiola": "Helopsaltes certhiola",
    "Pardaliparus venustulus": "Periparus venustulus",
    "Columba livia": "Columba livia",
}

# Common English names for the residential / garden subset (curated).
GARDEN_EN: dict[str, str] = {
    "Passer montanus": "Eurasian Tree Sparrow",
    "Hypsipetes amaurotis": "Brown-eared Bulbul",
    "Zosterops japonicus": "Warbling White-eye",
    "Parus cinereus": "Cinereous Tit",
    "Horornis diphone": "Japanese Bush Warbler",
    "Corvus macrorhynchos": "Large-billed Crow",
    "Corvus corone": "Carrion Crow",
    "Spodiopsar cineraceus": "White-cheeked Starling",
    "Streptopelia orientalis": "Oriental Turtle-Dove",
    "Hirundo rustica": "Barn Swallow",
    "Motacilla cinerea": "Grey Wagtail",
    "Motacilla alba": "White Wagtail",
    "Phoenicurus auroreus": "Daurian Redstart",
    "Coccothraustes coccothraustes": "Hawfinch",
    "Chloris sinica": "Oriental Greenfinch",
    "Cyanopica cyanus": "Azure-winged Magpie",
    "Alcedo atthis": "Common Kingfisher",
    "Yungipicus kizuki": "Japanese Pygmy Woodpecker",
    "Emberiza personata": "Black-faced Bunting",
    "Turdus pallidus": "Pale Thrush",
    "Turdus eunomus": "Dusky Thrush",
    "Periparus ater": "Coal Tit",
    "Sittiparus varius": "Varied Tit",
    "Aegithalos caudatus": "Long-tailed Tit",
    "Dendrocopos major": "Great Spotted Woodpecker",
    "Phasianus versicolor": "Green Pheasant",
    "Columba livia": "Rock Dove",
    "Monticola solitarius": "Blue Rock Thrush",
    "Emberiza cioides": "Meadow Bunting",
    "Pyrrhula pyrrhula": "Eurasian Bullfinch",
}

GARDEN_WAMEI = set(GARDEN_EN)  # keyed by sci; also match wamei below
GARDEN_JP = {
    "スズメ",
    "ヒヨドリ",
    "メジロ",
    "シジュウカラ",
    "ウグイス",
    "ハシブトガラス",
    "ハシボソガラス",
    "ムクドリ",
    "キジバト",
    "ツバメ",
    "キセキレイ",
    "ハクセキレイ",
    "ジョウビタキ",
    "シメ",
    "カワラヒワ",
    "オナガ",
    "カワセミ",
    "コゲラ",
    "アオジ",
    "シロハラ",
    "ツグミ",
    "ヒガラ",
    "ヤマガラ",
    "エナガ",
    "アカゲラ",
    "キジ",
    "カワラバト（ドバト）",
    "イソヒヨドリ",
    "ホオジロ",
    "ウソ",
}


def _load_labels() -> list[str]:
    if LABELS_TFLITE.is_file():
        return [ln.strip() for ln in LABELS_TFLITE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Fallback: GCS CSV with leading taxonomy tag stripped
    raw = [ln.strip() for ln in LABELS_GCS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if raw and raw[0] in ("inat2024_fsd50k", "label", "labels"):
        raw = raw[1:]
    return raw


def main() -> None:
    labels = _load_labels()
    ebird_raw = [ln.strip() for ln in EBIRD.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Align eBird codes with TFLite labels: GCS ebird file also has a leading tag.
    if ebird_raw and ebird_raw[0] in ("ebird2021", "code"):
        ebird_raw = ebird_raw[1:]
    if len(ebird_raw) != len(labels):
        raise SystemExit(f"ebird/labels length mismatch: {len(ebird_raw)} vs {len(labels)}")
    label_to_idx = {n: i for i, n in enumerate(labels)}

    df = pd.read_excel(OSJ_XLSX, sheet_name="リスト")
    df.columns = ["order", "part", "category", "sp_num", "ssp_num", "sci", "author", "wamei"]
    species = df[df["category"] == "種"].copy()

    # Include feral pigeon row stored as 種 with wamei カワラバト（ドバト）
    rows_out: list[dict] = []
    unmatched: list[tuple[str, str]] = []

    for _, r in species.iterrows():
        sci = str(r["sci"]).strip()
        wamei = str(r["wamei"]).strip()
        perch_name = SYNONYMS.get(sci, sci)
        idx = label_to_idx.get(perch_name)
        if idx is None:
            unmatched.append((sci, wamei))
            continue
        code = ebird_raw[idx]
        if code in ("ebird2021", "no_ebird_code", "inat2024_fsd50k"):
            code = ""
        in_garden = (sci in GARDEN_EN) or (wamei in GARDEN_JP)
        english = GARDEN_EN.get(sci, "")
        rows_out.append(
            {
                "ebird_code": code,
                "perch_index": idx,
                "scientific_name": sci,
                "scientific_name_perch": perch_name,
                "wamei": wamei,
                "english_name": english,
                "in_garden": "1" if in_garden else "0",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ebird_code",
        "perch_index",
        "scientific_name",
        "scientific_name_perch",
        "wamei",
        "english_name",
        "in_garden",
    ]
    # Dedupe by Perch label (OSJ can list a name more than once in edge cases)
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in rows_out:
        key = r["scientific_name_perch"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    rows_out = deduped

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    garden_rows = [r for r in rows_out if r["in_garden"] == "1"]
    with OUT_GARDEN.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(garden_rows)

    print(f"wrote {OUT} ({len(rows_out)} species)")
    print(f"wrote {OUT_GARDEN} ({len(garden_rows)} garden species)")
    print(f"unmatched OSJ species (no Perch label): {len(unmatched)}")
    for sci, wamei in unmatched[:25]:
        print(f"  - {wamei} ({sci})")
    if len(unmatched) > 25:
        print(f"  ... and {len(unmatched) - 25} more")


if __name__ == "__main__":
    main()
