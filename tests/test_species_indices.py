"""Sanity: garden perch_index matches labels.txt."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "models" / "labels.txt"
GARDEN = ROOT / "data" / "species" / "species_japan_garden.csv"


@pytest.mark.skipif(not LABELS.is_file(), reason="labels.txt not downloaded")
def test_garden_indices_align():
    from birdframe.species import load_species_csv

    labels = [ln.strip() for ln in LABELS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = load_species_csv(GARDEN)
    assert len(rows) >= 25
    for sp in rows:
        assert labels[sp.perch_index] == sp.scientific_name_perch
