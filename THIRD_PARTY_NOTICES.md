# Third-party notices / 第三者のライセンス

このリポジトリのコードは MIT ですが、以下はそれぞれの権利者のライセンスに従います。
The MIT license above covers this repository's code only. The following keep their own terms.

| 対象 / Component | ライセンス / License | 備考 / Notes |
|---|---|---|
| Google Perch v2 モデルとラベル (model weights & labels) | Apache-2.0 | https://www.kaggle.com/models/google/bird-vocalization-classifier — 同梱せず `scripts/download_model.py` でダウンロード |
| ernensbjorn/perch-v2-int8-tflite (TFLite 変換版) | Apache-2.0 | https://huggingface.co/ernensbjorn/perch-v2-int8-tflite — 同梱せずダウンロード |
| Pimoroni `inky` (palette values used in `palette.py`) | MIT | https://github.com/pimoroni/inky |
| Noto Sans/Serif CJK フォント | SIL OFL 1.1 | OS のパッケージを使用（同梱なし） |
| 日本鳥学会『日本鳥類目録 改訂第8版』掲載鳥類リスト | 同学会の利用条件（二次加工可・出典表示） | `data/species/SOURCES.md` |
| 絵（花鳥画・博物画） | パブリックドメイン／CC0（作品ごと） | 画像は同梱せず `scripts/download_artworks.py` でダウンロード。出典とライセンスは `data/artworks/artworks.csv` と `data/artworks/SOURCES.md`。小原古邨のカラスの1作品は、日本国外での利用時に初出年の確認が必要（`SOURCES.md` 参照） |
| Xeno-canto の録音（評価用） | 多くが CC BY-NC | **同梱していません。** `scripts/download_test_audio.py` は手元での評価専用。再配布しないでください |
