"""Display backends and the refresh controller.

The controller turns smoother 'present' events into e-ink refreshes:
- refresh only when the *set* of present species changes (order/score ignored)
- at most one refresh per `min_interval_sec` (latest wanted state is kept
  pending and applied when allowed)
- no refreshes during quiet hours (applied after they end), except the
  optional "night recap": from quiet start until `recap_end` the birds detected
  that day are shown one at a time in turn (every `recap_interval_sec`)
- idle screen (last seen bird, or a seasonal default) when nobody is present
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from birdframe.render import Frame, FrameRenderer, IdleInfo, PanelSpec, season_of

log = logging.getLogger(__name__)


class DisplayBackend(Protocol):
    def show(self, frame: Frame, now: dt.datetime) -> None: ...


class FileBackend:
    """Writes PNG simulations (what the panel would show) to a directory."""

    def __init__(self, out_dir: str | Path, write_device_png: bool = False):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.write_device_png = write_device_png
        self.count = 0
        self.written: list[Path] = []

    def show(self, frame: Frame, now: dt.datetime) -> None:
        self.count += 1
        names = "+".join(p.wamei for p in frame.panels) or "idle"
        path = self.out_dir / f"frame_{self.count:03d}_{now:%Y%m%d-%H%M%S}_{names}.png"
        frame.preview().save(path, optimize=True)
        frame.preview().save(self.out_dir / "latest.png", optimize=True)
        if self.write_device_png:
            frame.device_image().save(path.with_suffix(".device.png"))
        self.written.append(path)
        log.info("frame -> %s", path)


class InkyBackend:
    """Pimoroni Inky Impression 7.3" Spectra 6 (E673) via the MIT `inky` library."""

    SPEEDS = ("normal", "medium", "fast")

    def __init__(self, border: str = "white", busy_wait: bool = True, speed: str = "medium"):
        try:
            from inky.auto import auto

            self.inky = auto(ask_user=False, verbose=True)
        except Exception as e:  # EEPROM detect can fail on some HATs
            log.warning("inky auto-detect failed (%s); falling back to inky_e673", e)
            from inky.inky_e673 import Inky

            self.inky = Inky()
        if (self.inky.width, self.inky.height) != (800, 480):
            raise RuntimeError(f"unexpected panel size {self.inky.width}x{self.inky.height}")
        border_col = getattr(self.inky, border.upper(), None)
        if border_col is not None:
            self.inky.set_border(border_col)
        self.busy_wait = busy_wait
        self.speed = self._set_speed(speed)

    def _set_speed(self, speed: str) -> str:
        """inky>=2.6 Spectra 6 refresh speed: normal ~29.6 s, medium ~22.9 s, fast ~15 s (colours shift)."""
        speed = (speed or "normal").lower()
        if speed not in self.SPEEDS:
            raise ValueError(f"display.refresh_speed must be one of {self.SPEEDS}, got {speed!r}")
        const = getattr(self.inky, speed.upper(), None)
        if const is None or not hasattr(self.inky, "speed"):
            log.warning("inky library has no refresh speed option; using its default")
            return "default"
        self.inky.speed = const
        log.info("inky refresh speed: %s", speed)
        return speed

    def show(self, frame: Frame, now: dt.datetime) -> None:
        # Six-colour "P" image -> inky skips its own dithering and maps 1:1.
        self.inky.set_image(frame.device_image())
        self.inky.show(busy_wait=self.busy_wait)


class ThreadedBackend:
    """Runs the slow e-ink refresh in a worker thread so listening never stops.

    `show()` returns at once. While a refresh is running, newer frames replace
    any frame still waiting, so after the refresh the panel gets the latest
    state (intermediate states are skipped).
    """

    def __init__(self, inner):
        self.inner = inner
        self._cv = threading.Condition()
        self._pending: tuple[Frame, dt.datetime] | None = None
        self._busy = False
        self._closed = False
        self.completed = 0
        self.skipped = 0
        self._thread = threading.Thread(target=self._run, name="eink-refresh", daemon=True)
        self._thread.start()

    def show(self, frame: Frame, now: dt.datetime) -> None:
        with self._cv:
            if self._pending is not None:
                self.skipped += 1
            self._pending = (frame, now)
            self._cv.notify_all()

    def _run(self) -> None:
        while True:
            with self._cv:
                while self._pending is None and not self._closed:
                    self._cv.wait()
                if self._pending is None:
                    return
                frame, now = self._pending
                self._pending = None
                self._busy = True
            names = ", ".join(p.wamei for p in frame.panels) or "idle"
            t0 = time.monotonic()
            try:
                self.inner.show(frame, now)
                log.info("refresh done: %s (%.1fs)", names, time.monotonic() - t0)
            except Exception:
                log.exception("refresh failed: %s", names)
            finally:
                with self._cv:
                    self._busy = False
                    self.completed += 1
                    self._cv.notify_all()

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until nothing is pending or refreshing (tests / shutdown)."""
        with self._cv:
            return self._cv.wait_for(lambda: self._pending is None and not self._busy, timeout)

    def close(self, timeout: float = 60.0) -> None:
        """Let a running refresh finish (never cut the panel off mid-waveform), then stop."""
        self.wait_idle(timeout)
        with self._cv:
            self._closed = True
            self._cv.notify_all()
        self._thread.join(timeout=5)


@dataclass
class ControllerConfig:
    min_interval_sec: float = 900.0
    quiet_start: str | None = None  # "22:00"
    quiet_end: str | None = None  # "06:00"
    idle_mode: str = "last_seen"  # "last_seen" | "seasonal"
    last_seen_max_age_h: float = 24.0  # older than this -> seasonal default
    seasonal: dict[str, PanelSpec] = field(default_factory=lambda: {
        "spring": PanelSpec("ウグイス", "Horornis diphone"),
        "summer": PanelSpec("ツバメ", "Hirundo rustica"),
        "autumn": PanelSpec("スズメ", "Passer montanus"),
        "winter": PanelSpec("メジロ", "Zosterops japonicus"),
    })
    state_path: Path | None = None
    recap_end: str | None = None  # "00:00": night recap from quiet_start until this time; None = off
    recap_interval_sec: float = 300.0


def _parse_hm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def in_quiet_hours(now: dt.datetime, start: str | None, end: str | None) -> bool:
    if not start or not end:
        return False
    a, b, t = _parse_hm(start), _parse_hm(end), now.time()
    return (a <= t < b) if a <= b else (t >= a or t < b)


class DisplayController:
    def __init__(
        self,
        renderer: FrameRenderer,
        backend: DisplayBackend,
        config: ControllerConfig | None = None,
        clock: Callable[[], dt.datetime] = dt.datetime.now,
    ):
        self.renderer = renderer
        self.backend = backend
        self.cfg = config or ControllerConfig()
        self.clock = clock
        self.wanted: tuple[PanelSpec, ...] = ()
        self.shown_key: object = None
        self.last_refresh: dt.datetime | None = None
        self.last_seen: tuple[PanelSpec, dt.datetime] | None = None
        self.refreshes = 0
        self.today: list[PanelSpec] = []  # species detected during the current day (first-seen order)
        self.today_key: str | None = None
        self.recap_idx = -1
        self.recap_last: dt.datetime | None = None
        self._load_state()

    # --------------------------------------------------------------- input
    def on_present(self, species: list[PanelSpec] | tuple[PanelSpec, ...], now: dt.datetime | None = None) -> bool:
        """Feed the latest present-species list (score order). Returns True if refreshed."""
        now = now or self.clock()
        self.wanted = tuple(species)[:3]
        if self.wanted:
            self.last_seen = (self.wanted[0], now)
            self._remember_today(self.wanted, now)
        return self.tick(now)

    # ------------------------------------------------------- night recap
    def _day_key(self, now: dt.datetime) -> str:
        """A 'day' runs from quiet_end (e.g. 06:00) to the next quiet_end, so a
        recap that runs past midnight still shows the evening's birds."""
        b = _parse_hm(self.cfg.quiet_end) if self.cfg.quiet_end else dt.time(0, 0)
        shifted = now - dt.timedelta(hours=b.hour, minutes=b.minute)
        return shifted.date().isoformat()

    def _remember_today(self, species, now: dt.datetime) -> None:
        k = self._day_key(now)
        if k != self.today_key:
            self.today_key, self.today, self.recap_idx = k, [], -1
        added = False
        for sp in species:
            if all(sp.wamei != t.wamei for t in self.today):
                self.today.append(sp)
                added = True
        if added:
            self._save_state()

    def in_recap(self, now: dt.datetime) -> bool:
        if not (self.cfg.recap_end and self.cfg.quiet_start and self.cfg.quiet_end):
            return False
        return in_quiet_hours(now, self.cfg.quiet_start, self.cfg.recap_end) and \
            in_quiet_hours(now, self.cfg.quiet_start, self.cfg.quiet_end)

    def _recap_tick(self, now: dt.datetime) -> bool:
        if self._day_key(now) != self.today_key or not self.today:
            return False  # nothing detected today -> leave the screen alone
        # The recap has its own pace (independent of min_interval_sec); 60 s floor
        # because one e-ink refresh takes ~30 s.
        gap = max(self.cfg.recap_interval_sec, 60.0)
        if self.recap_last is not None and (now - self.recap_last).total_seconds() < gap:
            return False
        if self.last_refresh is not None and (now - self.last_refresh).total_seconds() < 60.0:
            return False
        n = len(self.today)
        idx = (self.recap_idx + 1) % n
        sp = self.today[idx]
        key = ("birds", frozenset([(sp.scientific_name, sp.wamei)]))
        if key == self.shown_key and n > 1:  # never the same bird twice in a row
            idx = (idx + 1) % n
            sp = self.today[idx]
            key = ("birds", frozenset([(sp.scientific_name, sp.wamei)]))
        self.recap_idx = idx
        self.recap_last = now
        if key == self.shown_key:
            return False  # only one bird today and it is already on screen
        frame = self.renderer.render([sp], day=now.date())
        self.backend.show(frame, now)
        log.info("night recap: %s (%d/%d)", sp.wamei, idx + 1, n)
        self.shown_key = key
        self.last_refresh = now
        self.refreshes += 1
        self._save_state()
        return True

    def show_startup(self, now: dt.datetime | None = None) -> bool:
        """Boot screen. Does not start the min-interval clock, so a bird heard
        right after boot is shown immediately."""
        now = now or self.clock()
        if not self.tick(now):
            return False
        self.last_refresh = None
        return True

    def tick(self, now: dt.datetime | None = None) -> bool:
        """Apply the pending state if allowed. Call periodically (e.g. every window)."""
        now = now or self.clock()
        if in_quiet_hours(now, self.cfg.quiet_start, self.cfg.quiet_end):
            if self.in_recap(now):
                return self._recap_tick(now)
            return False
        self.recap_last = None
        key = self._key(now)
        if key == self.shown_key:
            return False
        if self.last_refresh is not None and (now - self.last_refresh).total_seconds() < self.cfg.min_interval_sec:
            return False
        frame = self._render(now)
        self.backend.show(frame, now)
        self.shown_key = key
        self.last_refresh = now
        self.refreshes += 1
        self._save_state()
        return True

    @property
    def pending(self) -> bool:
        return self._key(self.clock()) != self.shown_key

    # ------------------------------------------------------------ helpers
    def _idle_info(self, now: dt.datetime) -> IdleInfo:
        season = season_of(now.date())
        if self.cfg.idle_mode == "last_seen" and self.last_seen:
            spec, when = self.last_seen
            if (now - when).total_seconds() <= self.cfg.last_seen_max_age_h * 3600:
                return IdleInfo(spec, "last_seen", when=when, season=season)
        return IdleInfo(self.cfg.seasonal[season], "seasonal", season=season)

    def _key(self, now: dt.datetime) -> object:
        """What the panel would look like. Equal keys -> no refresh (no flicker).

        In the "full" layout the idle screen is just the last/seasonal bird's painting
        with the same tiny signature, so it is identical to showing that bird live:
        both map to the same key and a bird that stays (or comes back) is not redrawn.
        """
        full = getattr(self.renderer, "layout", "classic") == "full"
        if self.wanted:
            return ("birds", frozenset((p.scientific_name, p.wamei) for p in self.wanted))
        idle = self._idle_info(now)
        if full:
            return ("birds", frozenset([(idle.species.scientific_name, idle.species.wamei)]))
        return ("idle", idle.reason, idle.species, idle.when, idle.season)

    def _render(self, now: dt.datetime) -> Frame:
        if self.wanted:
            return self.renderer.render(list(self.wanted), day=now.date())
        return self.renderer.render([], idle=self._idle_info(now), day=now.date())

    def _load_state(self) -> None:
        p = self.cfg.state_path
        if not p or not Path(p).exists():
            return
        try:
            s = json.loads(Path(p).read_text(encoding="utf-8"))
            if s.get("last_seen"):
                ls = s["last_seen"]
                self.last_seen = (PanelSpec(ls["wamei"], ls["scientific_name"]),
                                  dt.datetime.fromisoformat(ls["when"]))
            td = s.get("today") or {}
            if td.get("day"):
                self.today_key = td["day"]
                self.today = [PanelSpec(x["wamei"], x["scientific_name"]) for x in td.get("species", [])]
        except Exception as e:
            log.warning("ignoring bad state file %s: %s", p, e)

    def _save_state(self) -> None:
        p = self.cfg.state_path
        if not p:
            return
        s = {"last_seen": None, "shown": [x.wamei for x in self.wanted],
             "today": {"day": self.today_key,
                       "species": [{"wamei": x.wamei, "scientific_name": x.scientific_name} for x in self.today]}}
        if self.last_seen:
            spec, when = self.last_seen
            s["last_seen"] = {"wamei": spec.wamei, "scientific_name": spec.scientific_name,
                              "when": when.isoformat()}
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")


# =====================================================================
# Production schedule (agreed 2026-10-30)
# =====================================================================
@dataclass
class ScheduleConfig:
    day_start: str = "06:00"      # live display from here ...
    day_end: str = "19:00"        # ... until here; then the night recap
    night_end: str = "00:00"      # recap until here; then the screen is frozen until day_start
    group_window_min: float = 15  # each bird stays this many minutes from its own arrival, then drops out (the newest stays)
    night_interval_min: float = 30  # recap: one of today's birds every N minutes
    max_birds: int = 3            # 4th bird pushes out the oldest one


def _in_span(t: dt.time, a: dt.time, b: dt.time) -> bool:
    return (a <= t < b) if a <= b else (t >= a or t < b)


class ScheduledController(DisplayController):
    """Day: a newly heard bird is shown at once, side by side with the birds already
    on screen. Each bird keeps its place for `group_window_min` from its own arrival:
    when a new bird comes, birds whose time is up are dropped, the new one is added,
    and if more than `max_birds` remain the oldest is pushed out (rocket pencil).
    A bird already on screen heard again: no redraw, its arrival time is not extended.
    When a bird's time is up it is dropped and the screen is redrawn right then, even
    with no new bird; the last (newest) bird is never dropped and stays on screen.
    Night: today's birds (day = day_start..day_start) one at a time in turn.
    Late night: screen frozen (detections are still recorded)."""

    def __init__(self, renderer, backend, config: ControllerConfig | None = None,
                 schedule: ScheduleConfig | None = None, clock=dt.datetime.now):
        self.sch = schedule or ScheduleConfig()
        self.group: list[PanelSpec] = []
        self.arrived: dict[str, dt.datetime] = {}  # wamei -> arrival in the current group
        self._present_prev: set[str] = set()
        self._dirty = False  # the group changed because of a detection and is not drawn yet
        super().__init__(renderer, backend, config, clock)

    # ------------------------------------------------------------ phases
    def phase(self, now: dt.datetime) -> str:
        t = now.time()
        ds, de, ne = _parse_hm(self.sch.day_start), _parse_hm(self.sch.day_end), _parse_hm(self.sch.night_end)
        if _in_span(t, ds, de):
            return "day"
        if _in_span(t, de, ne):
            return "night"
        return "late"

    def _day_key(self, now: dt.datetime) -> str:
        b = _parse_hm(self.sch.day_start)
        return (now - dt.timedelta(hours=b.hour, minutes=b.minute)).date().isoformat()

    # ------------------------------------------------------------- input
    def on_present(self, species, now: dt.datetime | None = None) -> bool:
        now = now or self.clock()
        cur = tuple(species)
        names = {p.wamei for p in cur}
        new = [p for p in cur if p.wamei not in self._present_prev]  # newly heard birds
        self._present_prev = names
        self.wanted = cur[:3]
        if cur:
            self.last_seen = (cur[0], now)
            self._remember_today(cur, now)
        changed = False
        if new and self.phase(now) == "day":
            win = self.sch.group_window_min * 60
            for sp in new:
                if any(sp.wamei == g.wamei for g in self.group):
                    continue  # already on screen: no redraw, arrival time kept
                keep = [g for g in self.group
                        if g.wamei in self.arrived and (now - self.arrived[g.wamei]).total_seconds() < win]
                keep.append(sp)
                keep = keep[-self.sch.max_birds:]  # rocket pencil: oldest out
                self.arrived = {g.wamei: self.arrived.get(g.wamei, now) for g in keep}
                self.arrived[sp.wamei] = now
                self.group = keep
                changed = True
        if changed:
            self._dirty = True
            self._save_state()
        return self.tick(now)

    def _expire(self, now: dt.datetime) -> bool:
        """Day: drop birds whose own window is over; the newest one always stays.
        Returns True if the group changed."""
        if len(self.group) <= 1:
            return False
        win = self.sch.group_window_min * 60
        keep = [g for g in self.group
                if (now - self.arrived.get(g.wamei, now)).total_seconds() < win]
        if not keep:
            keep = [self.group[-1]]  # never empty the screen: the newest bird stays
        if len(keep) == len(self.group):
            return False
        gone = [g.wamei for g in self.group if g not in keep]
        on_screen = self._group_key(self.group) == self.shown_key
        self.group = keep
        self.arrived = {g.wamei: self.arrived[g.wamei] for g in keep if g.wamei in self.arrived}
        if on_screen:
            self._dirty = True  # redraw now (not after the night recap / at 6:00)
        log.info("expired: %s (left: %s)", ", ".join(gone), ", ".join(g.wamei for g in keep))
        self._save_state()
        return True

    def show_startup(self, now: dt.datetime | None = None) -> bool:
        now = now or self.clock()
        if self.phase(now) == "day":
            self._expire(now)  # restart after a while: don't show birds whose time is up
        frame = self.renderer.render(list(self.group), day=now.date()) if self.group else \
            self.renderer.render([], idle=self._idle_info(now), day=now.date())
        self.backend.show(frame, now)
        self.shown_key = self._group_key(self.group) if self.group else self._key_idle(now)
        self.refreshes += 1
        return True

    def tick(self, now: dt.datetime | None = None) -> bool:
        now = now or self.clock()
        ph = self.phase(now)
        if ph == "late":
            return False
        if ph == "night":
            return self._night_tick(now)
        self.recap_last = None
        self._expire(now)
        if not self.group or not self._dirty:
            return False  # day screen changes only when a bird comes or one's time is up
        key = self._group_key(self.group)
        if key == self.shown_key:
            self._dirty = False
            return False  # same bird / same combination: no redraw
        self.backend.show(self.renderer.render(list(self.group), day=now.date()), now)
        log.info("show: %s", ", ".join(p.wamei for p in self.group))
        self._dirty = False
        self.shown_key = key
        self.last_refresh = now
        self.refreshes += 1
        self._save_state()
        return True

    @property
    def pending(self) -> bool:
        return bool(self.group) and self._group_key(self.group) != self.shown_key

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _group_key(group) -> object:
        return ("birds", frozenset((p.scientific_name, p.wamei) for p in group))

    def _key_idle(self, now) -> object:
        idle = self._idle_info(now)
        return ("birds", frozenset([(idle.species.scientific_name, idle.species.wamei)]))

    def _night_tick(self, now: dt.datetime) -> bool:
        if self._day_key(now) != self.today_key or not self.today:
            return False
        if self.recap_last is not None and \
                (now - self.recap_last).total_seconds() < max(self.sch.night_interval_min * 60, 60):
            return False
        n = len(self.today)
        idx = (self.recap_idx + 1) % n
        if n > 1 and self._group_key([self.today[idx]]) == self.shown_key:
            idx = (idx + 1) % n  # never the same bird twice in a row
        sp = self.today[idx]
        self.recap_idx, self.recap_last = idx, now
        key = self._group_key([sp])
        if key == self.shown_key:
            return False
        self.backend.show(self.renderer.render([sp], day=now.date()), now)
        log.info("night: %s (%d/%d)", sp.wamei, idx + 1, n)
        self.shown_key = key
        self.last_refresh = now
        self.refreshes += 1
        self._save_state()
        return True

    def _load_state(self) -> None:
        super()._load_state()
        p = self.cfg.state_path
        if not p or not Path(p).exists():
            return
        try:
            s = json.loads(Path(p).read_text(encoding="utf-8"))
            g = s.get("group") or {}
            self.group = [PanelSpec(x["wamei"], x["scientific_name"]) for x in g.get("species", [])]
            start = g.get("start")  # older state files: one start time for the whole group
            self.arrived = {}
            for x in g.get("species", []):
                t = x.get("arrived") or start
                if t:
                    self.arrived[x["wamei"]] = dt.datetime.fromisoformat(t)
        except Exception as e:
            log.warning("ignoring bad group state in %s: %s", p, e)

    def _save_state(self) -> None:
        p = self.cfg.state_path
        if not p:
            return
        super()._save_state()
        s = json.loads(Path(p).read_text(encoding="utf-8"))
        s["group"] = {"species": [
            {"wamei": x.wamei, "scientific_name": x.scientific_name,
             "arrived": self.arrived[x.wamei].isoformat() if x.wamei in self.arrived else None}
            for x in self.group]}
        Path(p).write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
