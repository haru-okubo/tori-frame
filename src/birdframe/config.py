"""YAML config -> objects."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from birdframe.species import PACKAGE_ROOT

DEFAULT_CONFIG = PACKAGE_ROOT / "config" / "birdframe.example.yaml"


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Defaults from config/birdframe.example.yaml, overridden by `path`."""
    cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    if path:
        cfg = _merge(cfg, yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    return cfg


def resolve(p: str | Path | None) -> Path | None:
    if p is None:
        return None
    p = Path(p).expanduser()
    return p if p.is_absolute() else PACKAGE_ROOT / p


def build_renderer(cfg: dict):
    from birdframe.art import ArtCatalog
    from birdframe.render import FrameRenderer

    a, d = cfg["art"], cfg["display"]
    catalog = ArtCatalog(
        catalog=resolve(a["catalog"]), crops=resolve(a["crops"]),
        originals=resolve(a["originals"]), cache_dir=resolve(a["cache"]),
        min_confidence=a["min_confidence"],
        styles=a.get("styles") or None, style_mode=a.get("style_mode", "rotate"),
    )
    return FrameRenderer(
        catalog, method=d["dither"], saturation=d["saturation"], color_boost=d["color_boost"],
        contrast=d["contrast"], gamma=d["gamma"], mount=d["mount"],
        layout=d.get("layout", "full"), orientation=d.get("orientation", "portrait"),
        rotation=int(d.get("rotation", 90)),
        signature=bool((d.get("signature") or {}).get("enabled", True)),
        signature_size=int((d.get("signature") or {}).get("size", 15)),
        signature_corner=(d.get("signature") or {}).get("corner", "br"),
        art_context=float(d.get("art_context", 1.7)),
    )


def build_controller_config(cfg: dict, state_path_override: Path | None | bool = False):
    from birdframe.display import ControllerConfig
    from birdframe.render import PanelSpec

    d, i = cfg["display"], cfg["idle"]
    q = d.get("quiet_hours") or {}
    state = resolve(d.get("state_path")) if state_path_override is False else state_path_override
    return ControllerConfig(
        min_interval_sec=float(d["min_interval_sec"]),
        quiet_start=q.get("start"), quiet_end=q.get("end"),
        idle_mode=i["mode"], last_seen_max_age_h=float(i["last_seen_max_age_h"]),
        seasonal={k: PanelSpec(v[0], v[1]) for k, v in i["seasonal"].items()},
        state_path=state,
        recap_end=(d.get("night_recap") or {}).get("end"),
        recap_interval_sec=float((d.get("night_recap") or {}).get("interval_sec", 300)),
    )


def build_smoother_config(cfg: dict):
    from birdframe.smooth import SmootherConfig

    t = cfg["detect"]
    return SmootherConfig(
        window_sec=float(t["smooth_window_sec"]), enter_hits=int(t["min_hits"]),
        enter_prob=float(t["threshold"]), exit_prob=float(t["exit_threshold"]),
        enter_score_sum=float(t["score_sum"]), max_present=int(t["max_present"]),
        min_hold_sec=float(t["min_hold_sec"]),
    )


def build_schedule_config(cfg: dict):
    """display.schedule -> ScheduleConfig, or None (legacy min_interval/quiet_hours mode)."""
    from birdframe.display import ScheduleConfig

    sc = cfg["display"].get("schedule")
    if not sc:
        return None
    d = ScheduleConfig()
    return ScheduleConfig(
        day_start=str(sc.get("day_start", d.day_start)), day_end=str(sc.get("day_end", d.day_end)),
        night_end=str(sc.get("night_end", d.night_end)),
        group_window_min=float(sc.get("group_window_min", d.group_window_min)),
        night_interval_min=float(sc.get("night_interval_min", d.night_interval_min)),
        max_birds=int(sc.get("max_birds", d.max_birds)),
    )


def build_controller(cfg: dict, renderer, backend, state_path_override: Path | None | bool = False):
    from birdframe.display import DisplayController, ScheduledController

    cc = build_controller_config(cfg, state_path_override)
    sch = build_schedule_config(cfg)
    if sch is not None:
        return ScheduledController(renderer, backend, cc, schedule=sch)
    return DisplayController(renderer, backend, cc)


def describe_display(cfg: dict) -> str:
    d = cfg["display"]
    sch = build_schedule_config(cfg)
    if sch is not None:
        return (f"schedule: day {sch.day_start}-{sch.day_end} (each bird {sch.group_window_min:g} min then out, "
                f"newest stays, max {sch.max_birds}), night {sch.day_end}-{sch.night_end} every {sch.night_interval_min:g} min, "
                f"frozen {sch.night_end}-{sch.day_start}")
    return f"min_interval={d['min_interval_sec']}s quiet={d.get('quiet_hours')} night_recap={d.get('night_recap')}"
