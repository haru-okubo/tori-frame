"""End-to-end classification pipeline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from birdframe.audio import SAMPLE_RATE, iter_windows, load_mono
from birdframe.model import PerchV2TFLite
from birdframe.smooth import PresentEvent, SmootherConfig, events_from_windows
from birdframe.species import DEFAULT_GARDEN_CSV, DEFAULT_SPECIES_CSV, Species, SpeciesMask


@dataclass
class WindowResult:
    start_sec: float
    top: list[tuple[Species, float, float]]  # species, logit, prob


@dataclass
class MinuteDetection:
    minute: int
    species: Species
    hits: int
    mean_prob: float
    score_sum: float


@dataclass
class ClassifyResult:
    windows: list[WindowResult]
    minutes: list[MinuteDetection]
    events: list[PresentEvent] = field(default_factory=list)
    inference_ms_per_window: float = 0.0


def classify_file(
    path: str | Path,
    model: PerchV2TFLite,
    mask: SpeciesMask,
    *,
    hop_sec: float = 5.0,
    top_k: int = 5,
    window_prob_threshold: float = 0.08,
    minute_min_hits: int = 2,
    score_mode: str = "full_softmax",
    smoother: SmootherConfig | None = None,
) -> ClassifyResult:
    """Classify an audio file; mask to garden/Japan species; emit present events."""
    waveform = load_mono(path)
    hop_samples = int(hop_sec * SAMPLE_RATE)
    windows = iter_windows(waveform, hop_samples=hop_samples)

    import time

    results: list[WindowResult] = []
    times: list[float] = []
    minute_votes: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    for start_sec, w in windows:
        t0 = time.perf_counter()
        logits = model.embed_logits(w)
        dt = (time.perf_counter() - t0) * 1000.0
        times.append(dt)
        top = mask.topk(logits, k=top_k, mode=score_mode)
        results.append(WindowResult(start_sec=start_sec, top=top))
        if top and top[0][2] >= window_prob_threshold:
            sp, _logit, prob = top[0]
            minute = int(start_sec // 60)
            minute_votes[minute][sp.perch_index].append(prob)

    detections: list[MinuteDetection] = []
    for minute, by_sp in sorted(minute_votes.items()):
        for perch_index, probs in by_sp.items():
            if len(probs) >= minute_min_hits:
                detections.append(
                    MinuteDetection(
                        minute=minute,
                        species=mask.by_index[perch_index],
                        hits=len(probs),
                        mean_prob=float(np.mean(probs)),
                        score_sum=float(np.sum(probs)),
                    )
                )
    detections.sort(key=lambda d: (d.minute, -d.hits, -d.mean_prob))

    cfg = smoother or SmootherConfig(
        enter_prob=window_prob_threshold,
        exit_prob=max(0.02, window_prob_threshold * 0.5),
        enter_hits=minute_min_hits,
    )
    events = events_from_windows(
        results, window_prob_threshold=window_prob_threshold, config=cfg
    )

    mean_ms = float(np.mean(times)) if times else 0.0
    return ClassifyResult(
        windows=results,
        minutes=detections,
        events=events,
        inference_ms_per_window=mean_ms,
    )


def default_mask(*, full_japan: bool = False) -> SpeciesMask:
    """Default allow-list is the garden subset (user-approved)."""
    if full_japan:
        return SpeciesMask.from_csv(DEFAULT_SPECIES_CSV)
    path = DEFAULT_GARDEN_CSV
    if not path.is_file():
        return SpeciesMask.from_csv(DEFAULT_SPECIES_CSV, garden_only=True)
    return SpeciesMask.from_csv(path)
