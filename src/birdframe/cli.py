"""CLI: `birdframe classify|simulate|render|run`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from birdframe.classify import classify_file, default_mask
from birdframe.model import PerchV2TFLite
from birdframe.smooth import SmootherConfig
from birdframe.species import PACKAGE_ROOT


def _default_model() -> Path:
    """int8 (Pi 4 2GB friendly) by default; fall back to fp16 if only that is present."""
    models = PACKAGE_ROOT / "data" / "models"
    for name in ("perch_v2_dynint8.tflite", "perch_v2_fp16.tflite"):
        if (models / name).is_file():
            return models / name
    return models / "perch_v2_dynint8.tflite"


def cmd_classify(args: argparse.Namespace) -> int:
    model_path = Path(args.model) if args.model else _default_model()
    model = PerchV2TFLite(model_path, num_threads=args.threads)
    mask = default_mask(full_japan=args.full_japan)
    smoother = SmootherConfig(
        window_sec=args.smooth_window,
        enter_hits=args.min_hits,
        enter_prob=args.threshold,
        exit_prob=args.exit_threshold,
        enter_score_sum=args.score_sum,
        max_present=args.max_present,
        min_hold_sec=args.min_hold,
    )
    result = classify_file(
        args.audio,
        model,
        mask,
        hop_sec=args.hop,
        top_k=args.top_k,
        window_prob_threshold=args.threshold,
        minute_min_hits=args.min_hits,
        score_mode=args.score_mode,
        smoother=smoother,
    )

    print(f"# file: {args.audio}")
    print(f"# model: {model_path.name}")
    print(f"# mask: {'japan-full' if args.full_japan else 'garden'} ({len(mask.species)} spp)")
    print(f"# windows: {len(result.windows)}")
    print(f"# inference_ms/window (mean): {result.inference_ms_per_window:.1f}")
    print()
    print("## per-window top")
    for wr in result.windows:
        if not wr.top:
            continue
        sp, logit, prob = wr.top[0]
        flag = "*" if prob >= args.threshold else " "
        print(
            f"{flag} t={wr.start_sec:7.1f}s  {sp.wamei:12s}  {sp.scientific_name:28s}  "
            f"p={prob:.3f}  logit={logit:.2f}  [{sp.ebird_code}]"
        )
        if args.verbose:
            for sp2, logit2, prob2 in wr.top[1:]:
                print(
                    f"           {sp2.wamei:12s}  {sp2.scientific_name:28s}  "
                    f"p={prob2:.3f}  logit={logit2:.2f}"
                )

    print()
    print(
        f"## minute aggregates (min_hits={args.min_hits}, thr={args.threshold})"
    )
    if not result.minutes:
        print("(none)")
    for d in result.minutes:
        print(
            f"  minute={d.minute:3d}  hits={d.hits}  mean_p={d.mean_prob:.3f}  "
            f"sum={d.score_sum:.3f}  {d.species.wamei} ({d.species.scientific_name})"
        )

    print()
    print("## present-species events (e-ink; only on change)")
    if not result.events:
        print("(none)")
    for e in result.events:
        names = ", ".join(
            f"{s.wamei}:{sc:.3f}" for s, sc in zip(e.species, e.scores)
        ) or "(clear)"
        print(f"  t={e.t_sec:7.1f}s  {e.kind:6s}  {names}")

    if args.json_out:
        payload = {
            "file": str(args.audio),
            "mask": "japan-full" if args.full_japan else "garden",
            "inference_ms_per_window": result.inference_ms_per_window,
            "windows": [
                {
                    "start_sec": wr.start_sec,
                    "top": [
                        {
                            "wamei": sp.wamei,
                            "scientific_name": sp.scientific_name,
                            "ebird_code": sp.ebird_code,
                            "prob": prob,
                            "logit": logit,
                        }
                        for sp, logit, prob in wr.top
                    ],
                }
                for wr in result.windows
            ],
            "minutes": [
                {
                    "minute": d.minute,
                    "hits": d.hits,
                    "mean_prob": d.mean_prob,
                    "score_sum": d.score_sum,
                    "wamei": d.species.wamei,
                    "scientific_name": d.species.scientific_name,
                }
                for d in result.minutes
            ],
            "events": [
                {
                    "t_sec": e.t_sec,
                    "kind": e.kind,
                    "changed": e.changed,
                    "species": [
                        {"wamei": s.wamei, "scientific_name": s.scientific_name, "score": sc}
                        for s, sc in zip(e.species, e.scores)
                    ],
                }
                for e in result.events
            ],
        }
        Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n# wrote {args.json_out}")
    return 0


def _setup_logging(verbose: bool) -> None:
    import logging

    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _pipeline(cfg, model_override=None):
    from birdframe.config import build_smoother_config, resolve
    from birdframe.smooth import PresenceSmoother

    m = cfg["model"]
    model_path = Path(model_override) if model_override else (resolve(m["path"]) or _default_model())
    if not model_path.is_file():
        model_path = _default_model()
    model = PerchV2TFLite(model_path, num_threads=int(m["threads"]))
    mask = default_mask(full_japan=bool(m["full_japan"]))
    return model, mask, PresenceSmoother(build_smoother_config(cfg)), model_path


def cmd_run(args: argparse.Namespace) -> int:
    from birdframe.config import build_controller, build_renderer, describe_display, load_config, resolve
    from birdframe.display import FileBackend, InkyBackend, ThreadedBackend
    from birdframe.runtime import MicSource, run_loop

    _setup_logging(args.verbose)
    cfg = load_config(args.config)
    model, mask, smoother, model_path = _pipeline(cfg, args.model)
    d = cfg["display"]
    backend_name = args.backend or d["backend"]
    speed = str(d.get("refresh_speed") or "medium")
    inner = InkyBackend(speed=speed) if backend_name == "inky" else FileBackend(resolve(d["out_dir"]))
    backend = ThreadedBackend(inner)  # refresh in the background; listening continues
    ctrl = build_controller(cfg, build_renderer(cfg), backend)
    a = cfg["audio"]
    src = MicSource(device=a["device"], samplerate=int(a["samplerate"]), hop_sec=float(a["hop_sec"]))
    print(f"# birdframe run: model={model_path.name} backend={backend_name} "
          f"refresh_speed={speed} refresh=background {describe_display(cfg)}")
    try:
        stats = run_loop(src, model, mask, smoother, ctrl, threshold=float(cfg["detect"]["threshold"]))
    finally:
        backend.close()
    print(f"# stopped after {stats['windows']} windows, {ctrl.refreshes} refreshes")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    import datetime as dt

    import numpy as np

    from birdframe.config import build_controller, build_renderer, load_config
    from birdframe.display import FileBackend
    from birdframe.runtime import FileSource, run_loop

    cfg = load_config(args.config)
    if args.min_interval is not None:
        cfg["display"]["min_interval_sec"] = args.min_interval
    if args.no_quiet:
        cfg["display"]["quiet_hours"] = None
    model, mask, smoother, model_path = _pipeline(cfg, args.model)
    start = dt.datetime.fromisoformat(args.start) if args.start else dt.datetime.now().replace(microsecond=0)
    backend = FileBackend(args.out, write_device_png=args.device_png)
    if args.no_quiet:
        cfg["display"]["schedule"] = None
    ctrl = build_controller(cfg, build_renderer(cfg), backend, state_path_override=None)
    clock = lambda t: start + dt.timedelta(seconds=t)  # noqa: E731
    src = FileSource(args.audio, hop_sec=float(cfg["audio"]["hop_sec"]))
    duration = src.wav.size / 32000

    def show_window(t, top):
        if args.verbose and top:
            print(f"  t={t:6.1f}s  {top[0][0].wamei} p={top[0][2]:.3f}")

    stats = run_loop(src, model, mask, smoother, ctrl, threshold=float(cfg["detect"]["threshold"]),
                     clock=clock, on_window=show_window)
    deferred = False
    if args.flush and ctrl.pending:  # show what the frame would switch to once allowed
        when = (ctrl.last_refresh or start) + dt.timedelta(seconds=ctrl.cfg.min_interval_sec)
        when = max(when, clock(duration))
        deferred = ctrl.tick(when)
    print(f"# model: {model_path.name}  windows: {stats['windows']}  "
          f"mean infer {np.mean(stats['infer_ms']):.0f} ms/window")
    for when, names in stats["events"]:
        print(f"  {when:%H:%M:%S}  present -> {', '.join(names) or '(none)'}")
    print(f"# refreshes: {ctrl.refreshes}" + (" (last one deferred by min_interval; --no-flush to skip)" if deferred else ""))
    for p in backend.written:
        print(f"  {p}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    import datetime as dt

    from birdframe.config import build_renderer, load_config
    from birdframe.render import IdleInfo, PanelSpec, season_of
    from birdframe.species import load_species_csv
    from birdframe.species import DEFAULT_GARDEN_CSV

    cfg = load_config(args.config)
    if args.dither:
        cfg["display"]["dither"] = args.dither
    r = build_renderer(cfg)
    sci = {s.wamei: s.scientific_name for s in load_species_csv(DEFAULT_GARDEN_CSV)}
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    specs = [PanelSpec(w, sci.get(w, "")) for w in (args.species.split(",") if args.species else [])]
    if args.idle:
        if specs:
            when = dt.datetime.combine(day, dt.time.fromisoformat(args.idle_time))
            idle = IdleInfo(specs[0], "last_seen", when=when, season=season_of(day))
        else:
            s = cfg["idle"]["seasonal"][season_of(day)]
            idle = IdleInfo(PanelSpec(s[0], s[1]), "seasonal", season=season_of(day))
        frame = r.render([], idle=idle, day=day)
    else:
        frame = r.render(specs, day=day)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.preview().save(out, optimize=True)
    if args.device_png:
        frame.device_image().save(out.with_suffix(".device.png"))
    print(f"{out}  artworks={frame.artworks}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="birdframe",
        description="Japanese garden-bird classifier (Perch v2, garden mask default)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser(
        "classify",
        help="Classify a local audio file (wav/flac/ogg/mp3/m4a/…)",
    )
    c.add_argument(
        "audio",
        type=Path,
        help="Audio file — phone m4a/mp3 OK if ffmpeg is installed",
    )
    c.add_argument("--model", type=Path, default=None, help="Path to perch_v2_*.tflite")
    c.add_argument(
        "--full-japan",
        action="store_true",
        help="Use full Japan list instead of default garden-30 mask",
    )
    c.add_argument("--hop", type=float, default=5.0, help="Hop seconds between windows")
    c.add_argument("--top-k", type=int, default=5)
    c.add_argument(
        "--threshold",
        type=float,
        default=0.08,
        help="Window top-1 enter probability (default 0.08)",
    )
    c.add_argument(
        "--exit-threshold",
        type=float,
        default=0.04,
        help="Hysteresis exit probability while already present",
    )
    c.add_argument(
        "--min-hits",
        type=int,
        default=2,
        help="Hits in rolling window / per-minute to enter",
    )
    c.add_argument(
        "--score-sum",
        type=float,
        default=0.25,
        help="Alt enter rule: sum of probs in rolling 60s",
    )
    c.add_argument("--smooth-window", type=float, default=60.0, help="Rolling lookback seconds")
    c.add_argument("--min-hold", type=float, default=30.0, help="Min seconds to hold a species")
    c.add_argument("--max-present", type=int, default=1, help="Max species shown at once")
    c.add_argument("--threads", type=int, default=4)
    c.add_argument(
        "--score-mode",
        default="full_softmax",
        choices=["full_softmax", "masked_softmax", "logit"],
    )
    c.add_argument("--json-out", type=Path, default=None)
    c.add_argument("-v", "--verbose", action="store_true")
    c.set_defaults(func=cmd_classify)

    r = sub.add_parser("run", help="Mic -> classify -> smoother -> e-ink (main loop)")
    r.add_argument("--config", type=Path, default=None, help="YAML (defaults: config/birdframe.example.yaml)")
    r.add_argument("--backend", choices=["inky", "file"], default=None)
    r.add_argument("--model", type=Path, default=None)
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("simulate", help="Run the loop on an audio file; write the PNG frames it would show")
    s.add_argument("audio", type=Path)
    s.add_argument("--config", type=Path, default=None)
    s.add_argument("--model", type=Path, default=None)
    s.add_argument("--out", type=Path, default=Path("out/frames/sim"))
    s.add_argument("--start", default=None, help="Virtual start time, e.g. 2026-10-20T07:30:00")
    s.add_argument("--min-interval", type=float, default=None, help="Override min seconds between refreshes")
    s.add_argument("--no-quiet", action="store_true", help="Ignore quiet hours")
    s.add_argument("--no-flush", dest="flush", action="store_false",
                   help="Do not render a refresh still deferred at end of file")
    s.add_argument("--device-png", action="store_true", help="Also write 6-colour device PNGs")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_simulate)

    d = sub.add_parser("render", help="Render one frame for given species (or idle) to PNG")
    d.add_argument("--species", default="", help="Comma-separated 和名, e.g. メジロ,ヒヨドリ")
    d.add_argument("--idle", action="store_true", help="Idle screen (last seen = first --species, else seasonal)")
    d.add_argument("--idle-time", default="07:42")
    d.add_argument("--date", default=None, help="YYYY-MM-DD (artwork rotation / season)")
    d.add_argument("--dither", choices=["vivid", "fs", "none"], default=None)
    d.add_argument("--config", type=Path, default=None)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--device-png", action="store_true")
    d.set_defaults(func=cmd_render)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
