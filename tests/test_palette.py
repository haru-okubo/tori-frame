import numpy as np
import pytest
from PIL import Image

from birdframe import palette as pal


def test_quantize_indices_and_pure_colours():
    img = Image.new("RGB", (60, 20), (255, 255, 255))
    img.paste((0, 0, 0), (0, 0, 10, 20))
    img.paste((255, 0, 0), (20, 0, 30, 20))
    idx = np.asarray(pal.quantize(img, method="none"))
    assert idx.max() <= 5
    assert idx[5, 5] == pal.BLACK and idx[5, 25] == pal.RED and idx[5, 55] == pal.WHITE


def test_preview_white_is_white():
    assert pal.preview_palette()[pal.WHITE] == (255, 255, 255)


def test_inky_set_image_keeps_our_indices():
    """inky must not re-dither our 6-colour P image (checked against real inky code)."""
    e673 = pytest.importorskip("inky.inky_e673")
    ink = object.__new__(e673.Inky)  # bypass GPIO/EEPROM init
    ink.width, ink.height = 800, 480
    ink.cols, ink.rows, *_ = e673._RESOLUTION[(800, 480)]
    rng = np.random.default_rng(0)
    idx = rng.integers(0, 6, size=(480, 800), dtype=np.uint8)
    ink.set_image(pal.to_device_image(Image.fromarray(idx, "L")))
    remap = np.array([0, 1, 2, 3, 5, 6])  # inky's native codes (no 4)
    assert np.array_equal(ink.buf.reshape(480, 800), remap[idx])
