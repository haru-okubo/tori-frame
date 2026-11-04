import datetime as dt

import pytest

from birdframe.config import build_renderer, load_config
from birdframe.render import PanelSpec


@pytest.fixture(scope="module")
def renderer():
    return build_renderer(load_config())


def test_portrait_full_frame(renderer):
    f = renderer.render([PanelSpec("ヒヨドリ", "Hypsipetes amaurotis")], day=dt.date(2026, 10, 25))
    assert f.indices.size == (480, 800)
    dev = f.device_image()
    assert dev.size == (800, 480)  # panel is physically landscape


def test_landscape_classic():
    cfg = load_config()
    cfg["display"].update(layout="classic")
    f = build_renderer(cfg).render([PanelSpec("ヒヨドリ", "Hypsipetes amaurotis")], day=dt.date(2026, 10, 25))
    assert f.indices.size == (800, 480) and f.device_image().size == (800, 480)
