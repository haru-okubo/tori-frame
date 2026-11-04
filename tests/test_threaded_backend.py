import datetime as dt
import threading
import time

import pytest
from PIL import Image

from birdframe.display import InkyBackend, ThreadedBackend
from birdframe.render import Frame, PanelSpec


def fr(*names):
    return Frame(indices=Image.new("L", (800, 480), 1), panels=[PanelSpec(n, n) for n in names], idle=None)


class Slow:
    def __init__(self, sec=0.3):
        self.sec, self.got, self.thread = sec, [], None

    def show(self, frame, now):
        self.thread = threading.current_thread().name
        time.sleep(self.sec)
        self.got.append([p.wamei for p in frame.panels])


def test_show_returns_immediately_and_latest_wins():
    inner = Slow(0.3)
    b = ThreadedBackend(inner)
    now = dt.datetime(2026, 10, 30, 9)
    t0 = time.monotonic()
    b.show(fr("A"), now)
    time.sleep(0.05)                 # A is now refreshing
    b.show(fr("A", "B"), now)        # queued ...
    b.show(fr("A", "B", "C"), now)   # ... replaced by the newest state
    assert time.monotonic() - t0 < 0.15   # caller (listening loop) never blocks
    assert b.wait_idle(5)
    assert inner.got == [["A"], ["A", "B", "C"]]
    assert b.skipped == 1 and inner.thread == "eink-refresh"
    b.close()


def test_close_waits_for_running_refresh():
    inner = Slow(0.3)
    b = ThreadedBackend(inner)
    b.show(fr("A"), dt.datetime(2026, 10, 30, 9))
    time.sleep(0.05)
    b.close()
    assert inner.got == [["A"]]


def test_refresh_error_does_not_kill_worker():
    class Bad(Slow):
        def show(self, frame, now):
            if frame.panels[0].wamei == "X":
                raise RuntimeError("spi")
            super().show(frame, now)
    inner = Bad(0.01)
    b = ThreadedBackend(inner)
    b.show(fr("X"), dt.datetime(2026, 10, 30, 9)); b.wait_idle(2)
    b.show(fr("A"), dt.datetime(2026, 10, 30, 9)); b.wait_idle(2)
    assert inner.got == [["A"]]
    b.close()


class FakeInky:
    NORMAL, MEDIUM, FAST = 0x08, 0x06, 0x07

    def __init__(self):
        self.speed = self.NORMAL


def _backend_with(inky):
    b = object.__new__(InkyBackend)
    b.inky = inky
    return b


def test_inky_speed_medium_and_validation():
    b = _backend_with(FakeInky())
    assert b._set_speed("medium") == "medium" and b.inky.speed == FakeInky.MEDIUM
    assert b._set_speed("FAST") == "fast" and b.inky.speed == FakeInky.FAST
    with pytest.raises(ValueError):
        b._set_speed("turbo")


def test_inky_speed_old_library_falls_back():
    class Old:
        pass
    assert _backend_with(Old())._set_speed("medium") == "default"
