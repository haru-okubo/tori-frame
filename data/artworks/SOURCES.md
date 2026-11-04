# Artwork provenance (first pass)

Catalog: [`artworks.csv`](artworks.csv). Crop boxes: [`crops.yaml`](crops.yaml).

## Policy

- Only commercially usable Open Access / public-domain works.
- Prefer museum APIs that flag public domain (Met Open Access CC0, Art Institute of Chicago CC0).
- Wikimedia Commons files included only when the file page license is Public domain or CC0.
- **No fabricated metadata** — titles, artists, dates, and URLs come from museum APIs or Commons `imageinfo`/`extmetadata`.
- Avoid Sannomaru Shōzokan official Jakuchū Dōshoku Sai-e images (permission required).

## Sources used

| Source | License used here | Notes |
|--------|-------------------|-------|
| Metropolitan Museum of Art Open Access | CC0 | Object endpoint `collectionapi.metmuseum.org/.../objects/{id}`; v1 search is HTTP 410 since Oct 2026, use `/public/collection/v1.1/search?...&departmentId=6&limit=&offset=`. Album pages = `[primaryImage] + additionalImages` (image file names recorded per row). Bairei 百鳥画譜 正編 78573, 続編 57539. |
| Art Institute of Chicago | CC0 for `is_public_domain=true` images | IIIF `https://www.artic.edu/iiif/2/{image_id}/full/2000,/0/default.jpg` |
| Wikimedia Commons | Public domain / CC0 as marked per file | Bairei kachō gafu plates; NDL scans; some Hiroshige/Koson/Seitei |
| Cleveland Museum of Art (via Commons) | CC0 | Hiroshige kingfisher |
| Biodiversity Heritage Library (via Internet Archive mirror) | Public domain (BHL item rights: “Public domain. The BHL considers that this work is no longer under copyright protection.”) | Siebold, *Fauna japonica … Aves* (1833–1850), Harvard MCZ Ernst Mayr Library copy = IA `faunajaponicasi4sieb`. Page image `https://archive.org/download/faunajaponicasi4sieb/page/n{order-1}.jpg` (~2300×3380, hand-coloured). BHL page IDs from `_names.xml` are used as object_url. BHL website itself is behind a JS challenge from this box; IA serves the same scan. |
| Wikimedia Commons (natural-history plates) | Public domain per file page (only `Public domain` files used; CC BY-SA re-uploads of PD plates were skipped) | Gould *Birds of Europe* 1837 (BHL scans), Gould *Birds of Asia*, Naumann *Naturgeschichte der Vögel Mitteleuropas* 1901, Keulemans *Onze vogels in huis en tuin* 1873, Lilford *Coloured figures* 1885–97, Temminck & Laugier *Planches coloriées* 1838. |
| 国立国会図書館デジタルコレクション (NDL) | Public domain (manifest `Access Restrictions: PDM`; 公開範囲「インターネット公開（保護期間満了）」→ NDL: 自由に利用可、申請不要) | IIIF `https://dl.ndl.go.jp/api/iiif/{pid}/R{koma:07d}/full/3000,/0/default.jpg`. 『梅園禽譜』 pid 1286915 (毛利梅園, d.1851); 水谷豊文『禽譜』6上 pid 1287442 (d.1833). Terms: https://www.ndl.go.jp/jp/use/reproduction/index.html — credit 国立国会図書館 as source. |

## Ohara Koson note

Koson died **1945**. Works are public domain in **Japan** (life+70). AIC marks many 1920s–30s Koson prints as **not** public domain. Commons often tags them Public domain. For product/commercial use outside Japan, **confirm each print’s first publication date** (US: generally PD if published 1930 or earlier as of 2026). Crow plate kept as a gap-filler with an explicit license caveat in `artworks.csv`.

## Watanabe Seitei

Died 1918 → PD in Japan. Commons marks Sparrows Flying (Met 14.76.61.39) Public domain.

## Gaps

As of 2026-10-20 every garden-30 species has at least one medium/high artwork.
Weakest slots (medium only): シロハラ (梅園 雀鶫/白ツグミ), イソヒヨドリ (uncoloured Bairei, female-type),
ハクセキレイ (labels say セキレイ/鶺鴒 generically; plumage favours ハク). キジバト now has two medium
plates but no plate showing the barred neck patch.

## Species-identity rules used (2026-10-20 pass)

- A period label (kanji + kana gloss) on the page is required for album/manuscript plates; plumage must agree.
- Kanji alone is not trusted where period usage differs from modern names. Rejected for that reason:
  Bairei 続編 金鳩 (gloss ニシキバト), 続編 page glossed アカガシラ (a duck, not アカゲラ), Keisai
  “Gray Thrush” (label 畫眉鳥, not シロハラ), 水谷 サンセウクイ (サンショウクイ, not a wagtail),
  水谷 テラツツキ plates (generic woodpecker label, fanciful colours), Cleveland 1920.163 Hiroshige
  “Grosbeak” (a Java sparrow-type bird, not シメ), Brooklyn Hiroshige bunting (Commons file only 254 px).
- `medium` = label fits but colour is missing (uncoloured Bairei) or the label is generic or ambiguous.

## Crop clip regions

`crops.yaml` entries may carry `clip: [x0, y0, x1, y1]`, the usable area of the scan. The display
window never leaves it, which keeps NDL colour charts and rulers, facing pages and mounts out of frame.

## Scripts

```bash
python scripts/download_artworks.py
python scripts/process_artworks.py   # -> out/contact_sheet.png (Spectra 6 colour preview)
python scripts/process_artworks.py --new-since HEAD --out out/contact_sheet_new.png  # only rows added since a git rev
```

## AIC note (2026-10)

Art Institute of Chicago IIIF image URLs returned HTTP 403 from this environment. Metadata was confirmed via API (`is_public_domain=true`); download mirrors use Wikimedia Commons equivalents where available.

## QA log (2026-10-20, colour pass)

- `commons_bairei_yamabato_fuji` downgraded to **low**: the birds are green; the matching Bairei
  kachō gafu plate is titled on Commons “Japanese wisteria and white-bellied green pigeons”
  (= アオバト), so it is not キジバト. The キジバト slot uses `commons_bairei_yamabato_tsutsuji`.
- Crop boxes in `crops.yaml` re-checked visually against originals; 23 boxes corrected.
- Artist kanji (`artists.csv`) were added by this project from the romanized names.

## QA log (2026-10-20, remaining garden species)

- Added 20 rows (Met 12, NDL 8) for ヒガラ, ヤマガラ, エナガ, シロハラ, ツグミ, ジョウビタキ, イソヒヨドリ,
  シメ, ホオジロ, アオジ, ハクセキレイ, plus colour upgrades for アカゲラ, カワラヒワ and キジバト.
  Reasoning for each identification is in the `notes` column.
- Every crop was checked against the original with a 10% grid, then re-checked on the dithered
  sheet `out/contact_sheet_new.png`.

## Art styles

`artworks.csv` has a `style` column: `kachoga` (Japanese prints, paintings and Edo bird albums,
including 梅園禽譜 and 水谷禽譜) or `natural_history` (19th-century scientific colour plates).
A blank value means `kachoga`. The display picks styles via `art.styles` / `art.style_mode` in the config.

## Natural-history pass (2026-10-20)

31 rows, at least one plate for each of the 30 garden species. 20 are from *Fauna Japonica*
(Japanese specimens; many are type descriptions). Synonyms are checked against current names:

| FJ plate name | current | | FJ plate name | current |
|---|---|---|---|---|
| Columba (Turtur) gelastis | Streptopelia orientalis | | Lusciola aurorea | Phoenicurus auroreus |
| Alcedo ispida bengalensis | Alcedo atthis bengalensis | | Motacilla lugens | Motacilla alba lugens |
| Picus kisuki | Yungipicus kizuki | | Coccothraustes vulgaris japonicus | C. coccothraustes japonicus |
| Pica cyana | Cyanopica cyanus | | Pyrrhula orientalis | Pyrrhula pyrrhula griseiventris |
| Parus minor | Parus minor (Perch: P. cinereus) | | Fringilla kawarahiba minor | Chloris sinica minor |
| Parus (Megisturus) trivirgatus | Aegithalos caudatus trivirgatus | | Orpheus amaurotis | Hypsipetes amaurotis |
| Salicaria cantans | Horornis diphone cantans | | Sturnus cineraceus | Spodiopsar cineraceus |
| Turdus daulias (jun.) | Turdus pallidus (juvenile) | | Emberiza cioides / personata | same |

FJ has no plate for キジ, アカゲラ, ハシボソガラス, ヒガラ, ツバメ, ツグミ, イソヒヨドリ, スズメ,
キセキレイ or カワラバト (the text describes them without figures). Those slots use Gould, Naumann,
Keulemans, Lilford and Temminck plates of the same species. These are often European subspecies,
which the `notes` column records.

Rejected after visual check:
- FJ Tab. XXVII “Turdus pallens”: the birds have a white supercilium and orange flanks, i.e. Eyebrowed
  Thrush plumage (マミチャジナイ), not シロハラ.
- Gould *Birds of Europe* “Pallid Thrush, Turdus pallidus”: spotted breast, not Pale Thrush.
- Jerdon 1847 “Petrocincla manillensis”: all-blue bird, not the chestnut-bellied Japanese philippensis.
  Gould's Blue Thrush is used for the species instead.
- FJ Tab. XVIII is *Ficedula coronata* (センダイムシクイ), not メジロ (メジロ is Tab. XXII).
- CC BY-SA 4.0 Commons uploads of Dresser and Gould plates (swallow, sparrow, coal tit): skipped
  because the licence claim is unclear; PD alternatives were used.

Caveats:
- Thorburn (d. 1935) co-credited on the Lilford tree-sparrow plate: published before 1897, and life+70
  has expired everywhere relevant.
- Temminck シロハラ adult is coloured too rufous (medium). The FJ シロハラ is a juvenile (medium).
- `out/contact_sheet_natural_history.png` = Spectra 6 preview of this style.
