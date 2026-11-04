"""Every artwork's bird box must survive the tile crop at all stack sizes (1-3 birds)."""
import pytest
from birdframe.config import load_config, build_renderer

TILES = [(480, 800), (480, 397), (480, 262)]
R = build_renderer(load_config())
ARTS = sorted({a.artwork_id: a for l in R.catalog.by_wamei.values() for a in l}.values(),
              key=lambda a: a.artwork_id)


@pytest.mark.parametrize("art", ARTS, ids=lambda a: a.artwork_id)
def test_bird_box_never_cut(art):
    img = R.catalog.load(art)
    W, H = img.size
    for w, h in TILES:
        tile = R._cover_tile(img, art, w / h)
        assert abs(tile.width / tile.height - w / h) < 0.02
        mode, win, _ = R.last_plan
        if mode == "pad":
            continue  # padded layout keeps the whole box by construction
        bx0, by0, bx1, by1 = art.box[0] * W, art.box[1] * H, art.box[2] * W, art.box[3] * H
        inside = (min(win[2], bx1) - max(win[0], bx0)) * (min(win[3], by1) - max(win[1], by0))
        assert inside >= 0.985 * (bx1 - bx0) * (by1 - by0), (art.artwork_id, w, h, mode)


def test_non_solo_art_is_not_used_alone():
    from birdframe.render import PanelSpec
    import datetime as dt
    spec = PanelSpec("キセキレイ", "Motacilla cinerea")
    for d in range(1, 30):
        f = R.render([spec], day=dt.date(2026, 10, d))
        assert f.artworks != ["met_36710"]


def test_garden_mask_indices_match_model_labels():
    import csv
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    labels = (root / "data/models/labels.txt").read_text(encoding="utf-8").splitlines()
    for r in csv.DictReader(open(root / "data/species/species_japan_garden.csv", encoding="utf-8")):
        assert labels[int(r["perch_index"])] == r["scientific_name_perch"], r["wamei"]
