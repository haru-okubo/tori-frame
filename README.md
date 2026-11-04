# 日本の鳥電子額縁（tori-frame）

庭に来た鳥の声をマイクで聞き分けて、その鳥の日本画（花鳥画）や博物画を電子ペーパーの額縁に映す装置のコードです。
作者：@tori_no_frame

- 鳥の声の聞き分けは **ラズパイの中だけ** で行います（録音した音はネットに送りません）。
- **Wi-Fi（インターネット）は使います**（モデルや絵のダウンロード、パソコンからの SSH 操作など）。

## 作り方（完全手順書）

部品の買い方、OS の書き込み、配線、インストール、額縁の加工までの手順は
**「日本の鳥電子額縁 完全手順書」（PDF）** にまとめています。手順書は @tori_no_frame で配布しています。

## ダウンロード

- このページの右上「Code」→「Download ZIP」、または `git clone https://github.com/haru-okubo/tori-frame.git`
- 手順書と同じ zip：**[bird-frame-code.zip（Release v1.0）](https://github.com/haru-okubo/tori-frame/releases/download/v1.0/bird-frame-code.zip)**
  （展開すると `bird-frame/` フォルダができます）

AI のモデルと絵の画像は大きいので入っていません。手順書の4章のコマンドでダウンロードします。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[pi]"                 # ラズパイ用（パソコンで試すときは ".[dev]"）
python scripts/download_model.py       # Perch v2 int8（約105MB、Apache-2.0）
python scripts/download_artworks.py    # パブリックドメインの絵
birdframe render --species メジロ --out /tmp/test.png   # 試しに1枚描く
```

## 使っているもの

| 部品 | 内容 |
|---|---|
| 本体 | Raspberry Pi 4 Model B（2GB） |
| 画面 | Pimoroni Inky Impression 7.3インチ（Spectra 6、800×480） |
| マイク | USB マイク |
| 額縁 | IKEA RÖDALM 13×18cm（加工して使用） |

## フォルダの中身

```text
src/birdframe/   本体（音・推定・絞り込み・判定・絵選び・色補正・描画・表示）
config/          設定の見本 birdframe.example.yaml
deploy/          自動起動（systemd）の設定
scripts/         モデル・絵のダウンロードなど
data/species/    日本の鳥のリスト（庭の30種を含む）と出典
data/artworks/   絵の一覧・切り抜き位置・出典とライセンス
tests/           テスト（pytest）
```

英語の開発メモは [README.en.md](README.en.md) にあります。

## クレジットと感謝

- **fugleramme**（arnegiacomo さん）— https://github.com/arnegiacomo/fugleramme
  「鳥の声を聞いて額縁に映す」というアイデアの元になった作品です。この額縁はそれを参考に、日本の鳥と日本画向けに別に作ったもので、fugleramme のコードは含んでいません。
- **Google Perch v2**（鳥の声AI、Apache-2.0）と、その int8 変換版 **ernensbjorn/perch-v2-int8-tflite**（Apache-2.0）。
- **絵の出典**：メトロポリタン美術館（Open Access, CC0）、シカゴ美術館（CC0）、国立国会図書館デジタルコレクション（保護期間満了。出典：国立国会図書館）、Biodiversity Heritage Library／Internet Archive（シーボルト『Fauna Japonica』ほか、パブリックドメイン）、Wikimedia Commons（パブリックドメイン／CC0 の作品のみ）。作品ごとの出典は `data/artworks/artworks.csv`。
- **日本鳥学会『日本鳥類目録 改訂第8版』**（種のリストの元データ）。
- Pimoroni `inky`（MIT）、Noto CJK フォント（OFL）。

## ライセンス

このリポジトリのコードは [MIT License](LICENSE) です。
モデル・絵・鳥のリストなど第三者のものは、それぞれのライセンスに従います（[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）。
