"""Main loop: audio source -> Perch -> smoother -> display controller."""

from __future__ import annotations

import datetime as dt
import logging
import queue
import signal
import time
from typing import Iterator

import numpy as np
import resampy

from birdframe.audio import SAMPLE_RATE, WINDOW_SAMPLES, iter_windows, load_mono
from birdframe.display import DisplayController
from birdframe.model import PerchV2TFLite
from birdframe.render import PanelSpec
from birdframe.smooth import PresenceSmoother
from birdframe.species import SpeciesMask

log = logging.getLogger(__name__)


class FileSource:
    """Windows from an audio file; t = seconds from file start."""

    def __init__(self, path, hop_sec: float = 5.0):
        self.wav = load_mono(path)
        self.hop = int(hop_sec * SAMPLE_RATE)

    def windows(self) -> Iterator[tuple[float, np.ndarray]]:
        yield from iter_windows(self.wav, hop_samples=self.hop)


class MicSource:
    """Continuous capture via sounddevice (PortAudio); yields 5 s windows at 32 kHz."""

    def __init__(self, device=None, samplerate: int = 48000, hop_sec: float = 5.0):
        import sounddevice as sd

        self.sd = sd
        self.device = device
        self.sr = int(samplerate)
        self.hop = hop_sec
        self.q: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self.dropped = 0

    def _cb(self, indata, frames, time_info, status):
        if status:
            log.debug("audio status: %s", status)
        try:
            self.q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            self.dropped += 1

    def windows(self) -> Iterator[tuple[float, np.ndarray]]:
        need = int(5.0 * self.sr)
        hop = int(self.hop * self.sr)
        buf = np.zeros(0, dtype=np.float32)
        t0 = time.monotonic()
        consumed = 0
        with self.sd.InputStream(device=self.device, channels=1, samplerate=self.sr,
                                 dtype="float32", blocksize=int(self.sr * 0.5), callback=self._cb):
            log.info("mic open: device=%s sr=%d", self.device, self.sr)
            while True:
                buf = np.concatenate([buf, self.q.get()])
                while buf.size >= need:
                    w = buf[:need]
                    if self.sr != SAMPLE_RATE:
                        w = resampy.resample(w, self.sr, SAMPLE_RATE).astype(np.float32)
                    w = w[:WINDOW_SAMPLES] if w.size >= WINDOW_SAMPLES else np.pad(w, (0, WINDOW_SAMPLES - w.size))
                    yield consumed / self.sr, w
                    buf = buf[hop:]
                    consumed += hop
                if self.q.qsize() > 20 and time.monotonic() - getattr(self, "_warned", -1e9) > 60:
                    self._warned = time.monotonic()
                    log.warning("inference falling behind (%d blocks queued, %.0fs uptime)",
                                self.q.qsize(), time.monotonic() - t0)


def _spec(sp) -> PanelSpec:
    return PanelSpec(sp.wamei, sp.scientific_name)


def run_loop(source, model: PerchV2TFLite, mask: SpeciesMask, smoother: PresenceSmoother,
             controller: DisplayController, *, threshold: float, clock=None,
             score_mode: str = "full_softmax", on_window=None) -> dict:
    """Process windows until the source ends (file) or SIGTERM/SIGINT (mic).

    `clock(t_sec)` maps source time to wall time (simulate uses a virtual clock).
    """
    clock = clock or (lambda _t: dt.datetime.now())
    stop = {"flag": False}

    def _stop(*_):
        stop["flag"] = True

    old = {s: signal.signal(s, _stop) for s in (signal.SIGTERM, signal.SIGINT)}
    current: tuple[PanelSpec, ...] = ()
    stats = {"windows": 0, "events": [], "infer_ms": []}
    controller.show_startup(clock(0.0))  # idle screen at boot
    try:
        for t, w in source.windows():
            if stop["flag"]:
                break
            t0 = time.perf_counter()
            top = mask.topk(model.embed_logits(w), k=3, mode=score_mode)
            stats["infer_ms"].append((time.perf_counter() - t0) * 1000)
            stats["windows"] += 1
            if top:
                log.info("window t=%.0fs top=%s p=%.3f logit=%.1f 2nd=%s p=%.3f infer=%.1fs",
                         t, top[0][0].wamei, top[0][2], top[0][1],
                         top[1][0].wamei if len(top) > 1 else "-", top[1][2] if len(top) > 1 else 0.0,
                         stats["infer_ms"][-1] / 1000)
            cfg = smoother.config
            if top and top[0][2] >= min(cfg.enter_prob, cfg.exit_prob, threshold):
                evs = smoother.push(t, top[0][0], top[0][2])
            else:
                evs = smoother.push(t, None, 0.0)
            now = clock(t)
            for e in evs:
                if not e.changed:
                    continue
                new = tuple(_spec(s) for s in e.species)
                if set(new) != set(current):
                    stats["events"].append((now, [p.wamei for p in new]))
                    log.info("present: %s", ", ".join(p.wamei for p in new) or "(none)")
                current = new
            if on_window:
                on_window(t, top)
            if current or controller.wanted:
                controller.on_present(current, now)  # no-op unless the set changed
            else:
                controller.tick(now)  # e.g. apply a refresh deferred by min_interval
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    return stats
