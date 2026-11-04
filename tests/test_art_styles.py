import csv
import datetime as dt

import pytest
from PIL import Image

from birdframe.art import ArtCatalog

COLS = ["artwork_id", "species_code", "wamei", "scientific_name", "title", "artist", "date",
        "source_museum", "object_url", "image_url", "license", "attribution",
        "species_confidence", "notes", "style"]


def _catalog(tmp_path, rows, **kw):
    csv_path = tmp_path / "artworks.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    orig = tmp_path / "originals"
    orig.mkdir()
    for r in rows:
        Image.new("RGB", (8, 8)).save(orig / f"{r['artwork_id']}.jpg")
    crops = tmp_path / "crops.yaml"
    crops.write_text("{}\n", encoding="utf-8")
    return ArtCatalog(catalog=csv_path, crops=crops, originals=orig,
                      cache_dir=tmp_path / "cache", **kw)


ROWS = [
    dict(artwork_id="k1", wamei="メジロ", scientific_name="Zosterops japonicus",
         species_confidence="high", style="kachoga"),
    dict(artwork_id="n1", wamei="メジロ", scientific_name="Zosterops japonicus",
         species_confidence="high", style="natural_history"),
    dict(artwork_id="k2", wamei="スズメ", scientific_name="Passer montanus",
         species_confidence="high", style=""),  # blank style = kachoga (older catalogs)
]


def test_style_filter(tmp_path):
    cat = _catalog(tmp_path, ROWS, styles=["natural_history"])
    assert [a.artwork_id for a in cat.candidates("Zosterops japonicus")] == ["n1"]
    assert cat.pick("Passer montanus") is None


def test_blank_style_defaults_to_kachoga(tmp_path):
    cat = _catalog(tmp_path, ROWS, styles=["kachoga"])
    assert cat.pick("Passer montanus").artwork_id == "k2"


def test_rotate_uses_both_styles(tmp_path):
    cat = _catalog(tmp_path, ROWS)
    days = [dt.date(2026, 1, 1) + dt.timedelta(d) for d in range(4)]
    assert {cat.pick("Zosterops japonicus", day=d).artwork_id for d in days} == {"k1", "n1"}


def test_prefer_first_style_with_fallback(tmp_path):
    cat = _catalog(tmp_path, ROWS, styles=["natural_history", "kachoga"], style_mode="prefer")
    days = [dt.date(2026, 1, 1) + dt.timedelta(d) for d in range(4)]
    assert {cat.pick("Zosterops japonicus", day=d).artwork_id for d in days} == {"n1"}
    assert cat.pick("Passer montanus").artwork_id == "k2"  # no natural_history art -> fallback


def test_unknown_style_rejected(tmp_path):
    with pytest.raises(ValueError):
        _catalog(tmp_path, ROWS, styles=["ukiyoe"])
