# Sample frames (simulated)

Rendered on the dev box with `birdframe render` / `birdframe simulate`
(`dither: vivid`). Colours use Pimoroni's measured Spectra 6 ink palette
(inky `SATURATED_PALETTE`, scaled so panel white = 255) — an on-screen
approximation, not a photo of the panel.

| file | what |
|------|------|
| single_mejiro.png, single_suzume.png | one species |
| single_mejiro_fs.png | same as single_mejiro, plain Floyd–Steinberg (`dither: fs`) for comparison |
| two_hiyodori_shijukara.png | two species |
| two_with_missing_art.png | species without artwork yet → name-only panel |
| three_suzume_mejiro_uguisu.png | three species |
| idle_last_seen.png | no birds: last seen bird + time |
| idle_seasonal.png | no birds, nothing seen in 24 h: seasonal default (autumn → スズメ) |
| sim/frame_*.png | `birdframe simulate` on a local test file (スズメ 30 s → メジロ 45 s → silence), default config (min interval 180 s) |

The PNG files are not included in this repository. Regenerate them with `./scripts/make_sample_frames.sh` after `python scripts/download_artworks.py`.
