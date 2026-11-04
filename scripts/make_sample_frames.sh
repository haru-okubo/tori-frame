#!/usr/bin/env bash
# Regenerate out/frames/*.png sample frames (deterministic date for artwork rotation).
set -euo pipefail
cd "$(dirname "$0")/.."
D=2026-10-20
O=out/frames
birdframe render --date $D --species メジロ --out $O/single_mejiro.png
birdframe render --date $D --species メジロ --dither fs --out $O/single_mejiro_fs.png
birdframe render --date $D --species スズメ --out $O/single_suzume.png
birdframe render --date $D --species ヒヨドリ,シジュウカラ --out $O/two_hiyodori_shijukara.png
birdframe render --date $D --species ハシブトガラス,エナガ --out $O/two_with_missing_art.png
birdframe render --date $D --species スズメ,メジロ,ウグイス --out $O/three_suzume_mejiro_uguisu.png
birdframe render --date $D --idle --species ヒヨドリ --idle-time 07:42 --out $O/idle_last_seen.png
birdframe render --date $D --idle --out $O/idle_seasonal.png
