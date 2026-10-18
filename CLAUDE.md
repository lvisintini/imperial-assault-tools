# CLAUDE.md

Tools for filling gaps in the sibling dataset repo `../imperial-assault-data` (override with `IA_DATA_ROOT`). The data
repo stays data-only; anything with heavy dependencies or scraping lives here.

## Rules

- **Never open, view or Read image files**, whether staged originals, previews or dataset images. Inspect them only
  programmatically (size, format, hash). Visual checks and anything read off a card are done by the user, in `ia enter`.
- boardwars (cards.boardwars.eu) is the only image source. Keep crawling polite: `boardwars.Client` honours robots.txt
  and makes one request per second; don't bypass it.
- `crawler/` and `imperial_assault_tools/` are legacy 2017–18 code, kept as reference. Don't modernise them; port the
  logic you need into `ia_tools/`.
- Ids in the dataset stay numeric and contiguous: the next id is the highest id + 1.

## Layout

- `ia_tools/boardwars.py`: Zenphoto album parsing (breadcrumb path, sub-albums, images, pagination), the thumbnail →
  original URL rewrite, and the polite client.
- `ia_tools/classify.py`: album path → product, content type and hints. `match.py`: name normalisation and lookup.
- `ia_tools/audit.py` (`ia audit`): hash every original against `crawler/original-images-sha512.txt` (the "seen"
  register) and `known-skipped-sha512.txt`.
- `ia_tools/scrape.py` (`ia scrape`) → `staging/<product>/manifest.json` + `originals/`.
- `ia_tools/enter/` (`ia enter`): stdlib HTTP server (`server.py`), pure logic (`api.py`: form specs from the dataset's
  schemas, suggestions, per-entry validation), and the page in `static/` (plain JS). The entries.json format is
  documented in `staging.py`.
- `ia_tools/importer.py` (`ia import`): plan (all checks; raises `ImportProblems`) then apply. It writes the
  dataset's exact JSON format (`dataset.dumps`: indent 2, no trailing newline) and the image sizes in `images.py`
  (mirrors the data repo's `ImageTestHelper`; `tests/test_images.py` cross-checks them).

## Commands

```bash
uv sync
uv run pytest                    # needs the data repo at IA_DATA_ROOT (data/, schemas/, tests/ are enough)
uv run ia audit | scrape <url> | enter | import <product> [--check]
```

After an import, run `uv run pytest` in the data repo, and record this repo's commit in the data PR.
