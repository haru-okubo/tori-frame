# bird-frame

Local Japanese garden-bird “電子額縁”: a microphone listens, **Google Perch v2**
(Apache-2.0) identifies the bird, and a 7.3" colour e-ink panel shows a
public-domain Japanese 花鳥画 of that species. Fully local, **no BirdNET**
weights, code, or region lists.

Target hardware: **Raspberry Pi 4 (2 GB) + Pimoroni Inky Impression 7.3"
(Spectra 6, 800×480, 6 colours) + USB microphone.** (Pi 5 works too.)

## Features

- Audio → 32 kHz mono → 5 s windows; Perch v2 TFLite (**dynamic-int8, ~105 MB, default**; fp16 optional)
- Logits masked to an independently built **Japan species list** (OSJ 8th ed. × Perch labels);
  default mask = ~30 garden species (`--full-japan` for all)
- Rolling 60 s presence smoother with hysteresis → `present` events (max 3 species)
- Display controller: refresh **only when the set of present species changes**,
  minimum interval (default 900 s), quiet hours (default 22:00–06:00), idle screen
  (last bird seen, or a seasonal default)
- Layout `full` (default): portrait 480×800 painting fills the whole screen (bird never cut; wide birds get a paper-tone extension), tiny 名前+作者 signature in a corner; panel image is rotated onto the 800×480 Inky (`display.rotation` 90 = frame turned clockwise, 270 = counter-clockwise; `display.orientation: landscape` / `layout: classic` for the old look; `display.signature.enabled: false` hides all text)
- Spectra 6 colour rendering: artwork crop → Floyd–Steinberg dither onto the
  Pimoroni Spectra 6 palette, paper-white layout, caption in Noto Serif/Sans CJK JP (OFL);
  1–3 panels side by side
- Backends: `InkyBackend` (real panel via `inky`) and `FileBackend` (PNG simulation)

## Quick start (dev box / laptop)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/download_model.py          # int8 TFLite + labels (Apache-2.0)
python scripts/download_artworks.py       # PD artworks -> assets/originals/ (gitignored)

birdframe classify path/to/audio.wav -v                 # per-window predictions
birdframe simulate path/to/audio.wav --out out/frames/sim   # PNG frames the panel would show
birdframe render --species メジロ,スズメ --out /tmp/x.png  # render one frame directly
birdframe render --idle --species ヒヨドリ --idle-time 07:42 --out /tmp/idle.png
```

Japanese fonts: `sudo apt install fonts-noto-cjk` (paths configurable in the YAML).

`simulate` runs the same smoother + controller as `run` on a virtual clock
(`--start 2026-10-20T07:30:00`, `--min-interval 0` to see every change,
`--no-quiet` to ignore quiet hours, `--device-png` to also write the raw 6-colour image).

## Configuration

Copy `config/birdframe.example.yaml` → `config/birdframe.yaml` (gitignored) and
override only what you need; unspecified keys fall back to the example.
Key settings:

| key | default | meaning |
|-----|---------|---------|
| `model.path` | `data/models/perch_v2_dynint8.tflite` | TFLite model |
| `audio.device` / `audio.samplerate` | `null` / `48000` | mic (name substring or index from `python -m sounddevice`) |
| `detect.*` | thr 0.08, min_hits 2, window 60 s, hold 30 s | presence smoother |
| `display.min_interval_sec` | `900` | minimum time between panel refreshes |
| `display.quiet_hours` | `22:00`–`06:00` | no refreshes (set `null` to disable) |
| `display.dither` | `vivid` | `vivid` (white balance + saturation boost + FS) or `fs` (plain FS) |
| `idle.mode` | `last_seen` | `last_seen` (falls back to seasonal after 24 h) or `seasonal` |
| `idle.seasonal` | 春ウグイス / 夏ツバメ / 秋スズメ / 冬メジロ | idle species per season |

## Raspberry Pi 4 install

Use **Raspberry Pi OS 64-bit** (tested on the 2026-10-06 release, Debian 13 trixie) — `ai-edge-litert` ships aarch64 wheels only.

```bash
sudo apt update
sudo apt install -y git python3-venv python3-dev fonts-noto-cjk libportaudio2 ffmpeg
sudo raspi-config nonint do_i2c 0      # Inky EEPROM detection
sudo raspi-config nonint do_spi 0
# If inky reports "Chip Select 0 in use", add this line to /boot/firmware/config.txt and reboot:
#   dtoverlay=spi0-0cs

git clone https://github.com/haru-okubo/tori-frame.git ~/bird-frame && cd ~/bird-frame
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[pi]"                   # inky, sounddevice, ai-edge-litert …
python scripts/download_model.py         # ~105 MB int8 model
python scripts/download_artworks.py      # PD artworks (~100 MB originals)

cp config/birdframe.example.yaml config/birdframe.yaml
arecord -l                               # find the USB mic card
python -m sounddevice                    # note its name/index -> audio.device in the YAML

# smoke test without the panel (writes PNGs to out/frames/live/)
birdframe run --config config/birdframe.yaml --backend file -v
# real panel
birdframe run --config config/birdframe.yaml -v
```

Run at boot with systemd (edit `User`/paths in the unit if not `pi`):

```bash
sudo cp deploy/birdframe.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now birdframe
journalctl -u birdframe -f
```

Notes:
- The first artwork load per species builds a ≤1600 px cache in `assets/cache/`.
- Inference on the box: ~670 ms per 5 s window (4 threads, x86). On a Pi 4 (2 GB) it is about 2.8 s per 5 s window.
  `run` logs a warning if inference falls behind real time.
- Spectra 6 full refresh takes tens of seconds; the 180 s minimum interval protects the panel.

## Evaluation (local only)

- `docs/eval_garden31.txt`: 31 Xeno-canto clips, garden mask.
- `docs/eval_int8_vs_fp16.txt`: int8 vs fp16 — 26/31 both, identical predictions on all 31,
  similar latency on the box, ~3× lower peak RSS for int8.

```bash
python scripts/download_test_audio.py    # XC clips (often CC BY-NC: local testing only, gitignored)
python scripts/eval_clips.py --models data/models/perch_v2_dynint8.tflite data/models/perch_v2_fp16.tflite
```

### Model artifacts

| Artifact | Source | License |
|----------|--------|---------|
| `perch_v2_dynint8.tflite` (default) | Hugging Face `ernensbjorn/perch-v2-int8-tflite` | Apache-2.0 |
| `perch_v2_fp16.tflite` (`--variant perch_v2_fp16.tflite`) | same repo | Apache-2.0 |
| Class labels | HF `labels.txt` (14,795) | Apache-2.0 |

**Label index caveat:** Google’s GCS `labels.csv` has a leading taxonomy tag
(`inat2024_fsd50k`) that is **not** a TFLite class. This repo indexes against
`data/models/labels.txt` (14,795 rows) so `perch_index` matches logit positions.

## Species list

See [`data/species/SOURCES.md`](data/species/SOURCES.md) — 日本鳥学会『日本鳥類目録 改訂第8版』
mapped to Perch scientific names → `data/species/species_japan*.csv`.

## Artwork

Public-domain Japanese bird prints for the garden list: `data/artworks/`
(catalog, bird crop boxes in `crops.yaml`, artist kanji in `artists.csv`).
See [`data/artworks/SOURCES.md`](data/artworks/SOURCES.md) for licenses, caveats and gaps.
Only `high`/`medium` species-confidence entries are shown by default
(`art.min_confidence`); species without art get a name-only panel.

Two art styles (`style` column): `kachoga` (Japanese 花鳥画 prints and Edo bird albums) and
`natural_history` (19th-century scientific colour plates, mainly Siebold's *Fauna Japonica*).
Choose with `art.styles` (e.g. `[natural_history]`) and `art.style_mode`
(`rotate` mixes them day by day; `prefer` uses the first listed style that has art for the species).

```bash
python scripts/process_artworks.py       # out/contact_sheet.png (Spectra 6 preview of every crop)
python scripts/process_artworks.py --style natural_history --out out/contact_sheet_natural_history.png
./scripts/make_sample_frames.sh          # out/frames/*.png
```

Sample frames: [`out/frames/`](out/frames/README.md). Preview colours use Pimoroni's
measured Spectra 6 palette — an approximation of the real panel.

## Layout

```text
src/birdframe/     library + CLI (model, smoother, palette, art, render, display, runtime, config)
config/            birdframe.example.yaml
deploy/            systemd unit
scripts/           model/artwork/test-audio download, species build, eval, contact sheet
data/species/      committed CSVs + provenance
data/artworks/     artwork catalog + crops + provenance
data/models/       TFLite downloads (gitignored)
samples/           MANIFEST only; audio gitignored
out/               contact sheet + sample frames
docs/              eval notes
```

## License

MIT for this repository’s code (see LICENSE). Upstream model/labels Apache-2.0.
`inky` (Pimoroni) MIT — palette values used in `palette.py`. Noto CJK fonts OFL (system package, not bundled).
OSJ checklist: follow their notice (secondary processing allowed; attribute).
Xeno-canto clips are often CC BY-NC — **local testing only**, do not commit or redistribute.
