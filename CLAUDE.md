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
- Dataset ids are numbers in data 1.x (the next id is the highest + 1) and UUIDs from data 2.0.0 (new records get a
  uuid4). The tools read which from the schema (`Dataset.uses_uuids`), so they work with either checkout; tests
  translate 1.x ids with `tests.conftest.legacy_id`.
- Type names are data 2.0.0's (`ia_tools/dataset.py` `CONTENT_TYPES`). For a 1.x checkout, `Dataset.stored()` maps the
  renamed ones back (`RENAMED`: `skirmish-maps`, `story-mission-cards`, `threat-mission-cards`), and
  `Dataset.content_types()` lists only those the checkout has. 1.x's `side-mission-cards` was split in three in 2.0.0;
  the tools don't import side missions into 1.x data. Tests that need a 2.0.0-only file skip on 1.x.

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
- `ia_tools/campaign_maps.py` (`ia maps`): the campaign maps drawn from IC2's placements (`ic2.parse_sections`) with
  the Vassal tiles; how IC2 and Vassal place and turn tiles is in its docstring.
- `ia_tools/layouts.py` (`ia layouts`, and `ia enter`'s Map layouts page, `static/layouts.html`): the skirmish and raid
  maps' layouts, entered by hand into `staging/map-layouts/entries.json` and written to the data repo's
  `map-layouts.json`.
- `ia_tools/card_types.py` (`ia card-types`, and `ia enter`'s Card types page, `static/card-types.html`): whether each
  reward Feat and Imperial class card is a Feat or a Group Attachment, proposed from the wiki's card text (pages
  cached as `staging/wiki/pages/card-*.json`, found by title, the class and item categories, then the wiki's
  search), confirmed into `staging/card-types/entries.json`.
- `ia_tools/mats.py` (`ia mats`): the 13 skirmish map mats as sources, from the wiki cache (infobox name and sku; the main
  page's wave and dates) with images from FFG's product pages as the Wayback Machine archived them (og:image,
  fitted like other sources), staged in `staging/mats/` with a manifest that the data repo's migration 19 reads.
- `ia_tools/mission_entries.py` (`ia missions`, and `ia enter`'s Missions page, `static/missions.html`): the skirmish
  mission cards' scenarios and the story missions' rewards, entered by hand into `staging/mission-entries/entries.json`
  and written to `skirmish-missions.json` and `mission-rewards.json`.
- `ia_tools/importer.py` (`ia import`): plan (all checks; raises `ImportProblems`) then apply. It writes the
  dataset's exact JSON format (`dataset.dumps`: indent 2, no trailing newline) and the image sizes in `images.py`
  (mirrors the data repo's `ImageTestHelper`; `tests/test_images.py` cross-checks them).
- `ia_tools/iaspec.py`: the dataset's iaspec rule, used for the entry app's suggestions and checked on import. The data
  repo's `TestCanonicalNames` checks the same rule; keep the two in step.

## Commands

```bash
uv sync
uv run pytest                    # needs the data repo at IA_DATA_ROOT (data/, schemas/, tests/ are enough)
uv run ia audit | scrape <url> | enter | import <product> [--check]
```

After an import, run `uv run pytest` in the data repo, and record this repo's commit in the data PR.
