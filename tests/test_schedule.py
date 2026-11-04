import datetime as dt

from birdframe.display import ControllerConfig, ScheduleConfig, ScheduledController
from birdframe.render import Frame, PanelSpec
from PIL import Image

S = {n: PanelSpec(n, s) for n, s in [("スズメ", "Passer montanus"), ("メジロ", "Zosterops japonicus"),
                                     ("ヒヨドリ", "Hypsipetes amaurotis"), ("シジュウカラ", "Parus cinereus"),
                                     ("キジバト", "Streptopelia orientalis")]}
D = dt.datetime(2026, 10, 30)


class R:
    layout = "full"

    def render(self, panels, idle=None, day=None):
        return Frame(indices=Image.new("L", (800, 480), 1), panels=list(panels), idle=idle)


class BE:
    def __init__(self):
        self.shown = []

    def show(self, frame, now):
        self.shown.append((now, [p.wamei for p in frame.panels]))


def mk(tmp_path=None):
    be = BE()
    c = ScheduledController(R(), be, ControllerConfig(state_path=(tmp_path / "s.json") if tmp_path else None),
                            schedule=ScheduleConfig())
    return c, be


def hm(h, m=0, s=0, day=0):
    return D + dt.timedelta(days=day, hours=h, minutes=m, seconds=s)


def hear(c, names, t):
    return c.on_present([S[n] for n in names], t)


def test_day_each_bird_15_min_and_rocket_pencil():
    c, be = mk()
    assert hear(c, ["スズメ"], hm(8))                       # 1 bird -> shown at once
    assert be.shown[-1][1] == ["スズメ"]
    assert not hear(c, ["スズメ"], hm(8, 1))                # same bird -> no redraw
    hear(c, [], hm(8, 3))                                   # bird gone -> screen unchanged
    assert hear(c, ["メジロ"], hm(8, 5))                    # 5 min later another bird -> side by side
    assert be.shown[-1][1] == ["スズメ", "メジロ"]
    assert hear(c, ["メジロ", "ヒヨドリ"], hm(8, 8))
    assert be.shown[-1][1] == ["スズメ", "メジロ", "ヒヨドリ"]
    assert hear(c, ["シジュウカラ"], hm(8, 12))             # 4th bird pushes out the oldest
    assert be.shown[-1][1] == ["メジロ", "ヒヨドリ", "シジュウカラ"]
    assert not hear(c, ["メジロ"], hm(8, 13))               # already shown -> nothing
    # 8:21: メジロ (8:05) has had its 15 min, the others not -> only メジロ drops
    assert hear(c, ["キジバト"], hm(8, 21))
    assert be.shown[-1][1] == ["ヒヨドリ", "シジュウカラ", "キジバト"]
    assert len(be.shown) == 5


def test_redetection_does_not_extend_and_expiry_redraws_keeping_newest():
    c, be = mk()
    hear(c, ["スズメ"], hm(8)); hear(c, ["スズメ", "メジロ"], hm(8, 5))
    for m in range(6, 40):                                  # スズメ keeps singing; no new bird
        hear(c, ["スズメ"], hm(8, m)); c.tick(hm(8, m, 30))
    # 8:15 スズメ out (re-hearing did not extend it); メジロ is the newest -> stays even after 8:20
    assert [x[1] for x in be.shown] == [["スズメ"], ["スズメ", "メジロ"], ["メジロ"]]
    assert be.shown[-1][0] == hm(8, 15)
    assert hear(c, ["ヒヨドリ"], hm(8, 40))                 # メジロ long expired -> new bird alone
    assert be.shown[-1][1] == ["ヒヨドリ"]


def test_expiry_one_by_one_until_newest_alone():
    """Example: カラス 10:00, メジロ 10:05, スズメ 10:10, nothing else."""
    S["ハシブトガラス"] = PanelSpec("ハシブトガラス", "Corvus macrorhynchos")
    c, be = mk()
    hear(c, ["ハシブトガラス"], hm(10)); hear(c, [], hm(10, 1))
    hear(c, ["メジロ"], hm(10, 5)); hear(c, [], hm(10, 6))
    hear(c, ["スズメ"], hm(10, 10)); hear(c, [], hm(10, 11))
    shots = []
    t = hm(10, 11)
    while t < hm(12):
        if c.tick(t):
            shots.append((t, be.shown[-1][1]))
        t += dt.timedelta(seconds=5)
    assert shots == [(hm(10, 15), ["メジロ", "スズメ"]), (hm(10, 20), ["スズメ"])]
    assert [p.wamei for p in c.group] == ["スズメ"]


def test_expiry_does_not_redraw_at_night_or_at_6am():
    c, be = mk()
    hear(c, ["スズメ"], hm(18, 50)); hear(c, ["スズメ", "メジロ"], hm(18, 55)); hear(c, [], hm(18, 56))
    assert be.shown[-1][1] == ["スズメ", "メジロ"]
    n0 = len(be.shown)
    c.tick(hm(19))                                           # 19:00 -> night recap as before
    assert len(be.shown) == n0 + 1 and len(be.shown[-1][1]) == 1
    n1 = len(be.shown)
    for i in range(0, 1200, 5):                              # 6:00-6:20 next day: no redraw by itself
        c.tick(hm(6, day=1) + dt.timedelta(seconds=i))
    assert len(be.shown) == n1


def test_expiry_while_refreshing_is_one_redraw_of_latest():
    c, be = mk()
    hear(c, ["スズメ"], hm(8)); hear(c, ["スズメ", "メジロ"], hm(8, 1)); hear(c, [], hm(8, 2))
    hear(c, ["ヒヨドリ"], hm(8, 2)); hear(c, [], hm(8, 3))
    n0 = len(be.shown)
    assert c.tick(hm(8, 16)) and be.shown[-1][1] == ["ヒヨドリ"]   # スズメ and メジロ both up -> one redraw
    assert len(be.shown) == n0 + 1


def test_startup_drops_expired_birds(tmp_path):
    c, be = mk(tmp_path)
    hear(c, ["スズメ"], hm(8)); hear(c, ["スズメ", "メジロ"], hm(8, 5))
    c2, be2 = mk(tmp_path)
    c2.show_startup(hm(9))
    assert be2.shown[-1][1] == ["メジロ"] and len(be2.shown) == 1
    assert not c2.tick(hm(9, 1))


def test_all_expired_new_bird_alone():
    c, be = mk()
    hear(c, ["スズメ"], hm(8)); hear(c, ["スズメ", "メジロ"], hm(8, 5)); hear(c, [], hm(8, 6))
    assert hear(c, ["ヒヨドリ"], hm(8, 20))                 # スズメ 20 min, メジロ exactly 15 min -> both out
    assert be.shown[-1][1] == ["ヒヨドリ"]


def test_expired_bird_heard_again_rejoins_as_newest():
    c, be = mk()
    hear(c, ["スズメ"], hm(8)); hear(c, [], hm(8, 1))
    hear(c, ["メジロ"], hm(8, 10)); hear(c, [], hm(8, 11))
    assert c.tick(hm(8, 15)) and be.shown[-1][1] == ["メジロ"]   # スズメ (8:00) out at 8:15
    assert hear(c, ["スズメ"], hm(8, 16))                   # heard again -> back as the newest
    assert be.shown[-1][1] == ["メジロ", "スズメ"]
    assert c.arrived["スズメ"] == hm(8, 16)


def test_night_rotation_every_30_min_and_late_freeze():
    c, be = mk()
    hear(c, ["スズメ"], hm(9)); hear(c, [], hm(9, 1))
    hear(c, ["メジロ"], hm(12)); hear(c, [], hm(12, 1))
    hear(c, ["ヒヨドリ"], hm(15)); hear(c, [], hm(15, 1))
    n0 = len(be.shown)
    t, shots = hm(18, 50), []
    while t < hm(6, 30, day=1):
        if c.tick(t):
            shots.append((t, be.shown[-1][1]))
        t += dt.timedelta(seconds=5)
    night = [x for x in shots if x[0] < hm(0, 0, day=1)]
    assert night and night[0][0] == hm(19)                       # starts at 19:00
    assert all(len(x[1]) == 1 for x in night)
    assert all(a[1] != b[1] for a, b in zip(night, night[1:]))   # never the same bird twice in a row
    gaps = {(b[0] - a[0]).total_seconds() for a, b in zip(night, night[1:])}
    assert gaps == {1800.0}                                      # every 30 min
    assert {x[1][0] for x in night} == {"スズメ", "メジロ", "ヒヨドリ"}
    assert all(x[0] < hm(0, 0, day=1) for x in shots)            # 00:00-06:00 frozen (and no redraw at 6:00 by itself)
    hear(c, ["キジバト"], hm(2, day=1))                         # heard late at night: recorded, not shown
    assert len(be.shown) == n0 + len(night)
    assert hear(c, ["シジュウカラ"], hm(6, 40, day=1))          # next morning: shown at once
    assert be.shown[-1][1] == ["シジュウカラ"]
    assert [p.wamei for p in c.today] == ["キジバト", "シジュウカラ"] or [p.wamei for p in c.today] == ["シジュウカラ"]


def test_night_no_birds_today_no_redraw():
    c, be = mk()
    hear(c, ["スズメ"], hm(9) - dt.timedelta(days=1))  # yesterday only
    n0 = len(be.shown)
    for i in range(0, 5 * 3600, 5):
        c.tick(hm(19) + dt.timedelta(seconds=i))
    assert len(be.shown) == n0


def test_birds_heard_at_night_join_rotation_but_not_live():
    c, be = mk()
    hear(c, ["スズメ"], hm(10)); hear(c, [], hm(10, 1))
    c.tick(hm(19))
    assert be.shown[-1][1] == ["スズメ"]
    n0 = len(be.shown)
    hear(c, ["メジロ"], hm(19, 10))
    assert len(be.shown) == n0                    # not shown live at night
    assert c.tick(hm(19, 30)) and be.shown[-1][1] == ["メジロ"]


def test_state_survives_restart(tmp_path):
    c, be = mk(tmp_path)
    hear(c, ["スズメ"], hm(8)); hear(c, ["スズメ", "メジロ"], hm(8, 5))
    c2, be2 = mk(tmp_path)
    assert [p.wamei for p in c2.group] == ["スズメ", "メジロ"]
    assert [p.wamei for p in c2.today] == ["スズメ", "メジロ"]
    c2.show_startup(hm(8, 6))
    assert be2.shown[-1][1] == ["スズメ", "メジロ"]
    assert not hear(c2, ["スズメ", "メジロ"], hm(8, 7))


def test_real_case_20261030_hiyodori_pushes_out_only_crow():
    """Pi log 2026-10-30: crow 09:46:11, メジロ 09:57:11, スズメ 09:59:36, ヒヨドリ 10:01:21.
    Only the crow has had its own 15 min -> メジロ・スズメ・ヒヨドリ (was wrongly ヒヨドリ alone)."""
    S["ハシブトガラス"] = PanelSpec("ハシブトガラス", "Corvus macrorhynchos")
    c, be = mk()
    hear(c, ["ハシブトガラス"], hm(9, 46, 11)); hear(c, [], hm(9, 47, 27))
    hear(c, ["メジロ"], hm(9, 57, 11)); hear(c, ["メジロ", "スズメ"], hm(9, 59, 36))
    assert be.shown[-1][1] == ["ハシブトガラス", "メジロ", "スズメ"]
    hear(c, ["メジロ", "ヒヨドリ"], hm(10, 1, 21))
    assert be.shown[-1][1] == ["メジロ", "スズメ", "ヒヨドリ"]
    # 1 min earlier the crow is still inside its 15 min -> pushed out as the oldest (same screen)
    c, be = mk()
    hear(c, ["ハシブトガラス"], hm(9, 46, 11)); hear(c, [], hm(9, 47, 27))
    hear(c, ["メジロ"], hm(9, 57, 11)); hear(c, ["メジロ", "スズメ"], hm(9, 59, 36))
    hear(c, ["メジロ", "ヒヨドリ"], hm(10, 0, 21))
    assert be.shown[-1][1] == ["メジロ", "スズメ", "ヒヨドリ"]


def test_old_state_file_with_group_start_loads(tmp_path):
    import json
    (tmp_path / "s.json").write_text(json.dumps({"group": {"start": "2026-10-30T10:01:21", "species": [
        {"wamei": "ヒヨドリ", "scientific_name": "Hypsipetes amaurotis"}]}}), encoding="utf-8")
    c, be = mk(tmp_path)
    assert [p.wamei for p in c.group] == ["ヒヨドリ"] and c.arrived["ヒヨドリ"] == hm(10, 1, 21)
    assert hear(c, ["スズメ"], hm(10, 10))
    assert be.shown[-1][1] == ["ヒヨドリ", "スズメ"]
    c2, _ = mk(tmp_path)
    assert c2.arrived == {"ヒヨドリ": hm(10, 1, 21), "スズメ": hm(10, 10)}
