from birdframe.smooth import PresenceSmoother, SmootherConfig
from birdframe.species import Species


def _sp(idx: int, name: str) -> Species:
    return Species(
        perch_index=idx,
        ebird_code="x",
        scientific_name=name,
        scientific_name_perch=name,
        wamei=name,
        english_name=name,
        in_garden=True,
    )


def test_hysteresis_enter_and_hold():
    cfg = SmootherConfig(
        window_sec=60,
        enter_hits=2,
        enter_prob=0.1,
        exit_prob=0.05,
        enter_score_sum=99,  # force hits path
        max_present=1,
        min_hold_sec=30,
        emit_on_score_delta=9,
    )
    sm = PresenceSmoother(cfg)
    a = _sp(1, "A")
    # one hit — should not enter yet
    ev = sm.push(0.0, a, 0.2)
    assert ev == [] or not any(e.kind == "enter" for e in ev)
    # second hit — enter
    ev = sm.push(5.0, a, 0.2)
    assert any(e.changed and e.kind == "enter" for e in ev)
    # low score within hold — should not clear
    ev = sm.push(10.0, a, 0.01)
    assert not any(e.kind == "clear" for e in ev)
