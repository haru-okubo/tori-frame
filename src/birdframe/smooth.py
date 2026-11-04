"""Rolling aggregation and hysteresis for stable 'present species' events.

Designed for e-ink frames that should only refresh when the displayed
species set actually changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from birdframe.species import Species


@dataclass
class WindowHit:
    start_sec: float
    species: Species
    prob: float


@dataclass(frozen=True)
class PresentEvent:
    """A stable presence decision suitable for driving a display."""

    t_sec: float
    species: tuple[Species, ...]  # sorted by score desc
    scores: tuple[float, ...]  # aligned with species
    kind: str  # "enter" | "update" | "clear"
    changed: bool  # True if display should refresh


@dataclass
class SmootherConfig:
    window_sec: float = 60.0
    """Rolling lookback for aggregation."""
    enter_hits: int = 2
    """Min windows with top-1 >= enter_prob inside the lookback to enter."""
    enter_prob: float = 0.08
    """Per-window probability to count as a hit (enter)."""
    enter_score_sum: float = 0.25
    """Or: sum of probs in lookback must reach this (OR with enter_hits)."""
    exit_hits: int = 1
    """Hysteresis: stay present if this many hit windows remain (at exit_prob)."""
    exit_prob: float = 0.04
    """Lower threshold while already present."""
    max_present: int = 1
    """How many species to show at once (e-ink usually 1)."""
    min_hold_sec: float = 30.0
    """Do not clear/replace a species sooner than this after enter/update."""
    emit_on_score_delta: float = 0.35
    """Re-emit 'update' if top score rises by this much (optional refresh)."""


@dataclass
class PresenceSmoother:
    """Stateful rolling smoother over a stream of window top-1 hits."""

    config: SmootherConfig = field(default_factory=SmootherConfig)
    _hits: list[WindowHit] = field(default_factory=list)
    _present: dict[int, float] = field(default_factory=dict)  # perch_index -> entered_at
    _last_scores: dict[int, float] = field(default_factory=dict)
    _last_emit_species: tuple[int, ...] = ()

    def push(self, start_sec: float, species: Species | None, prob: float) -> list[PresentEvent]:
        """Ingest one window result; return 0–1 display events."""
        cfg = self.config
        if species is not None and prob >= min(cfg.enter_prob, cfg.exit_prob):
            self._hits.append(WindowHit(start_sec, species, prob))
        # Drop hits outside lookback
        cutoff = start_sec - cfg.window_sec
        self._hits = [h for h in self._hits if h.start_sec >= cutoff]

        scores = self._aggregate(start_sec)
        next_present = self._decide_present(scores, start_sec)

        # Build ordered display list
        ordered = sorted(next_present, key=lambda i: -scores.get(i, 0.0))[: cfg.max_present]
        ordered_t = tuple(ordered)
        changed = ordered_t != self._last_emit_species

        # Score-delta update for same species
        kind = "clear"
        if ordered:
            kind = "enter" if not self._last_emit_species else "update"
            if (
                not changed
                and self._last_emit_species
                and ordered_t == self._last_emit_species
            ):
                old = self._last_scores.get(ordered[0], 0.0)
                new = scores.get(ordered[0], 0.0)
                if new - old >= cfg.emit_on_score_delta:
                    changed = True
                    kind = "update"
                else:
                    kind = "update"
                    changed = False
        elif self._last_emit_species:
            kind = "clear"
            changed = True
        else:
            changed = False

        self._present = {i: self._present.get(i, start_sec) for i in next_present}
        # Enforce min_hold: keep species that entered recently even if scores dipped
        for i, entered in list(self._present.items()):
            if start_sec - entered < cfg.min_hold_sec and i not in next_present:
                # already filtered in _decide_present via hold — keep scores snapshot
                pass

        events: list[PresentEvent] = []
        if changed or (ordered and not self._last_emit_species):
            # Resolve Species objects from latest hits / present
            sp_map = {h.species.perch_index: h.species for h in self._hits}
            species_out = tuple(sp_map[i] for i in ordered if i in sp_map)
            scores_out = tuple(scores.get(i, 0.0) for i in ordered if i in sp_map)
            if len(species_out) != len(ordered) and not ordered:
                species_out, scores_out = (), ()
            events.append(
                PresentEvent(
                    t_sec=start_sec,
                    species=species_out,
                    scores=scores_out,
                    kind=kind if ordered else "clear",
                    changed=True,
                )
            )
            self._last_emit_species = tuple(s.perch_index for s in species_out)
            self._last_scores = {s.perch_index: sc for s, sc in zip(species_out, scores_out)}
        return events

    def _aggregate(self, now: float) -> dict[int, float]:
        cfg = self.config
        by: dict[int, list[float]] = {}
        for h in self._hits:
            thr = cfg.exit_prob if h.species.perch_index in self._present else cfg.enter_prob
            if h.prob >= thr:
                by.setdefault(h.species.perch_index, []).append(h.prob)
        return {i: float(np.sum(ps)) for i, ps in by.items()}

    def _decide_present(self, scores: dict[int, float], now: float) -> set[int]:
        cfg = self.config
        hits_count: dict[int, int] = {}
        for h in self._hits:
            thr = cfg.exit_prob if h.species.perch_index in self._present else cfg.enter_prob
            if h.prob >= thr:
                hits_count[h.species.perch_index] = hits_count.get(h.species.perch_index, 0) + 1

        present: set[int] = set()
        # Keep existing with hysteresis
        for i in list(self._present):
            entered = self._present[i]
            if now - entered < cfg.min_hold_sec:
                present.add(i)
                continue
            n = hits_count.get(i, 0)
            s = scores.get(i, 0.0)
            if n >= cfg.exit_hits or s >= cfg.enter_score_sum * 0.5:
                present.add(i)

        # Enter new
        for i, n in hits_count.items():
            if i in present:
                continue
            s = scores.get(i, 0.0)
            if n >= cfg.enter_hits or s >= cfg.enter_score_sum:
                present.add(i)
                self._present[i] = now
        return present


def events_from_windows(
    windows: list,  # WindowResult-like with .start_sec and .top
    *,
    window_prob_threshold: float,
    config: SmootherConfig | None = None,
) -> list[PresentEvent]:
    """Run PresenceSmoother over offline window results; return change events only."""
    sm = PresenceSmoother(config=config or SmootherConfig())
    out: list[PresentEvent] = []
    for wr in windows:
        if wr.top and wr.top[0][2] >= min(
            sm.config.enter_prob, sm.config.exit_prob, window_prob_threshold
        ):
            sp, _, prob = wr.top[0]
            # Still push low probs for hysteresis tracking when above exit_prob
            evs = sm.push(wr.start_sec, sp, prob)
        else:
            evs = sm.push(wr.start_sec, None, 0.0)
        out.extend(e for e in evs if e.changed)
    return out
