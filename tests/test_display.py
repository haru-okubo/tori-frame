import datetime as dt

import numpy as np
from PIL import Image

from birdframe.display import ControllerConfig, DisplayController, in_quiet_hours
from birdframe.render import Frame, PanelSpec

T0 = dt.datetime(2026, 10, 20, 7, 0, 0)
A, B, C = PanelSpec("スズメ", "Passer montanus"), PanelSpec("メジロ", "Zosterops japonicus"), PanelSpec("ヒヨドリ", "Hypsipetes amaurotis")


class FakeRenderer:
    def render(self, panels, idle=None, day=None):
        return Frame(indices=Image.new("L", (800, 480), 1), panels=list(panels), idle=idle)


class FullRenderer(FakeRenderer):
    layout = "full"


class RecBackend:
    def __init__(self):
        self.shown = []

    def show(self, frame, now):
        self.shown.append((now, [p.wamei for p in frame.panels], frame.idle))


def ctrl(**kw):
    be = RecBackend()
    return DisplayController(FakeRenderer(), be, ControllerConfig(**kw)), be


def at(sec):
    return T0 + dt.timedelta(seconds=sec)


def test_refresh_only_on_set_change_and_interval():
    c, be = ctrl(min_interval_sec=180)
    assert c.show_startup(at(0))  # idle at boot, does not start the interval clock
    assert c.on_present([A], at(5))  # first bird right away
    assert not c.on_present([A], at(10))  # same set
    assert c.on_present([B, A], at(200))  # set changed, interval ok -> refresh
    assert be.shown[-1][1] == ["メジロ", "スズメ"]
    assert not c.on_present([A, B], at(260))  # same set, different order -> no refresh
    assert not c.on_present([A], at(300))  # changed but < 180 s since last refresh
    assert c.pending
    assert not c.tick(at(370))
    assert c.tick(at(381))  # deferred state applied once allowed
    assert be.shown[-1][1] == ["スズメ"]


def test_idle_shows_last_seen_then_seasonal():
    c, be = ctrl(min_interval_sec=0, last_seen_max_age_h=1)
    c.on_present([C], at(0))
    c.on_present([], at(60))
    idle = be.shown[-1][2]
    assert idle.reason == "last_seen" and idle.species == C
    c.tick(at(2 * 3600))  # last seen too old -> seasonal default (October = autumn)
    idle = be.shown[-1][2]
    assert idle.reason == "seasonal" and idle.season == "autumn"


def test_quiet_hours_defer():
    c, be = ctrl(min_interval_sec=0, quiet_start="22:00", quiet_end="06:00")
    night = dt.datetime(2026, 10, 20, 23, 0)
    assert not c.on_present([A], night)
    assert c.pending
    assert c.tick(dt.datetime(2026, 10, 21, 6, 0))
    assert in_quiet_hours(dt.datetime(2026, 1, 1, 3, 0), "22:00", "06:00")
    assert not in_quiet_hours(dt.datetime(2026, 1, 1, 12, 0), "22:00", "06:00")
    assert in_quiet_hours(dt.datetime(2026, 1, 1, 13, 0), "12:30", "14:00")


def test_state_file_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    c, _ = ctrl(min_interval_sec=0, state_path=p)
    c.on_present([B], at(0))
    c2, _ = ctrl(min_interval_sec=0, state_path=p)
    assert c2.last_seen[0] == B


def test_same_bird_never_redraws_full_layout():
    be = RecBackend()
    c = DisplayController(FullRenderer(), be, ControllerConfig(min_interval_sec=0))
    assert c.on_present([A], at(0))            # first draw
    for t in (5, 10, 400):                      # same bird keeps being detected
        assert not c.on_present([A], at(t))
    assert not c.on_present([A, B][:1], at(500))
    assert c.on_present([A, B], at(600))        # collage: new combination -> redraw
    assert not c.on_present([B, A], at(700))    # same combination, different order -> no redraw
    assert c.on_present([A], at(800))
    n = len(be.shown)
    assert not c.on_present([], at(900))        # bird gone: idle shows last_seen A == same picture
    assert not c.tick(at(5000)) and len(be.shown) == n
    assert not c.on_present([A], at(5100))      # same bird returns -> still no redraw
    assert c.on_present([B], at(5200))          # a different bird -> redraw


# ------------------------------------------------------------ night recap
N0 = dt.datetime(2026, 10, 20, 21, 0, 0)


def recap_ctrl(**kw):
    be = RecBackend()
    cfg = dict(min_interval_sec=30, quiet_start="22:00", quiet_end="06:00", recap_end="00:00",
               recap_interval_sec=300)
    cfg.update(kw)
    return DisplayController(FullRenderer(), be, ControllerConfig(**cfg)), be


def test_night_recap_rotates_todays_birds_then_stops():
    c, be = recap_ctrl()
    c.on_present([A], N0)
    c.on_present([B, C], N0 + dt.timedelta(minutes=10))
    c.on_present([], N0 + dt.timedelta(minutes=20))
    n = len(be.shown)
    t = dt.datetime(2026, 10, 20, 22, 0, 5)
    shown = []
    while t < dt.datetime(2026, 10, 21, 6, 0, 0):
        if c.tick(t):
            shown.append((t, be.shown[-1][1]))
        t += dt.timedelta(seconds=5)
    assert shown, "recap should start at 22:00"
    assert all(len(x[1]) == 1 for x in shown)  # one bird at a time
    assert all(a[1] != b[1] for a, b in zip(shown, shown[1:]))  # never the same bird twice in a row
    assert {x[1][0] for x in shown} == {"スズメ", "メジロ", "ヒヨドリ"}
    assert all(x[0].hour >= 22 for x in shown)  # nothing after midnight
    gaps = [(b[0] - a[0]).total_seconds() for a, b in zip(shown, shown[1:])]
    assert min(gaps) >= 300
    assert len(be.shown) == n + len(shown)


def test_night_recap_nothing_detected_today_no_refresh():
    c, be = recap_ctrl()
    c.last_seen = (A, N0 - dt.timedelta(days=1))
    t = dt.datetime(2026, 10, 20, 22, 0, 0)
    for i in range(0, 7200, 5):
        c.tick(t + dt.timedelta(seconds=i))
    assert be.shown == []


def test_night_recap_live_birds_not_shown_but_remembered():
    c, be = recap_ctrl()
    t = dt.datetime(2026, 10, 20, 22, 30, 0)
    c.on_present([A], t)  # first bird of the day heard during recap
    assert be.shown[-1][1] == ["スズメ"]  # shown via recap (it is today's only bird)
    c.on_present([A, B], t + dt.timedelta(seconds=10))
    assert len(be.shown) == 1  # live set not drawn during quiet hours
    assert c.tick(t + dt.timedelta(seconds=301)) and be.shown[-1][1] == ["メジロ"]


def test_night_recap_off_by_default_keeps_quiet(tmp_path):
    be = RecBackend()
    c = DisplayController(FullRenderer(), be, ControllerConfig(min_interval_sec=0, quiet_start="22:00",
                                                               quiet_end="06:00", state_path=tmp_path / "s.json"))
    c.on_present([A], N0)
    c.on_present([B], dt.datetime(2026, 10, 20, 22, 30))
    assert be.shown[-1][1] == ["スズメ"] and len(be.shown) == 1
    c2 = DisplayController(FullRenderer(), RecBackend(), ControllerConfig(state_path=tmp_path / "s.json",
                                                                          quiet_end="06:00"))
    assert [p.wamei for p in c2.today] == ["スズメ", "メジロ"]  # today's list survives a restart


def test_night_recap_pace_independent_of_min_interval():
    c, be = recap_ctrl(min_interval_sec=900)
    c.on_present([A, B], N0)
    t = dt.datetime(2026, 10, 20, 22, 0, 0)
    times = [t + dt.timedelta(seconds=i) for i in range(0, 1800, 5) if c.tick(t + dt.timedelta(seconds=i))]
    assert len(times) >= 5  # every 5 min, not every 15 min
