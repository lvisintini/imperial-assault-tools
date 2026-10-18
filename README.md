# imperial-assault-tools

Tools for filling the gaps in [imperial-assault-data](https://github.com/lvisintini/imperial-assault-data). They scrape
cards.boardwars.eu, audit it against the dataset, help you enter card data in the browser, and import the result. Every
image in the dataset comes from boardwars.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12+ if needed). Keep the dataset checked out next to
this repo, or point `IA_DATA_ROOT` at it:

```
Src/
├── imperial-assault-data/    # the dataset (IA_DATA_ROOT)
└── imperial-assault-tools/   # this repo
```

```bash
uv sync
uv run pytest
```

## The workflow

```bash
uv run ia audit                  # crawl all of boardwars; report in staging/audit/report.md
uv run ia scrape https://cards.boardwars.eu/Expansion-Boxes/Tyrants-of-Lothal/
uv run ia enter                  # opens http://localhost:8001: go through the cards
uv run ia import tyrants-of-lothal --check   # validate only
uv run ia import tyrants-of-lothal           # write records, images and source-contents rows
```

Then, in the data repo, run `uv run pytest`, look at the result with `uv run python serve_site.py`, and open a PR that
says which commit of this repo produced it.

- **`ia audit`** crawls every album (honouring robots.txt, one request per second). It hashes each original in memory
  and compares the hash with `crawler/original-images-sha512.txt`: the SHA-512s of everything the 2017–18 batches
  downloaded, which boardwars still serves unchanged. Each image gets a status:
  - **seen**: the hash is in the list;
  - **unseen-known**: not in the list, but a record with the same type and name exists (probably a re-uploaded scan);
  - **unseen**: a candidate gap;
  - **skipped**: listed in `known-skipped-sha512.txt`.

  An interrupted audit resumes from `staging/audit/hashes.jsonl`.
- **`ia scrape <album>`** downloads one album into `staging/<product>/`. It writes `originals/` plus a `manifest.json`
  with each image's album path, guessed content type, hints (affiliation, tier, hero, ...), size and hash, and any
  dataset records with the same name.
- **`ia enter`** is a local web app. For each image it shows the original, a preview of how it will be imported, and an
  existing card of the same type. You decide what each image is:
  - a new record, using a form built from the dataset's JSON Schemas;
  - the same card as an existing record, which only adds a `source-contents` row;
  - an extra image for another card (a hero's wounded side);
  - skip for now, or never import.

  Agenda decks and imperial classes, which have no image, are added under "Records without an image". Decisions are
  saved as you go to `staging/<product>/entries.json`.
- **`ia import <product>`** checks everything first: schemas, ids, foreign keys, image paths and iaspec uniqueness. If
  anything fails it reports every problem and writes nothing. Otherwise it:
  - assigns the next ids;
  - writes the records in the dataset's exact JSON format;
  - adds the `source-contents` rows;
  - writes the large and small PNGs at the sizes the dataset's tests expect;
  - appends the imported originals' hashes to the register.

  It never overwrites an existing image.

| Variable | Default | |
|---|---|---|
| `IA_DATA_ROOT` | `../imperial-assault-data` | the dataset checkout |
| `IA_STAGING` | `./staging` | downloads and entries (git-ignored) |
| `IA_PORT` | `8001` | `ia enter` port |
| `TINIFY_KEY` | unset | compress with TinyPNG, like the existing images; otherwise Pillow quantises to a palette PNG |

## Legacy code

`crawler/` (Scrapy) and `imperial_assault_tools/` (AssemblyLine batch scripts, OpenCV alignment, `eog` prompts) built the
dataset in 2017–18. They're kept for reference only and don't run on current Python. `ia_tools` reuses their knowledge
of the boardwars layout, the image sizes and the file naming rules. `assets/templates/` (alignment templates) and
`crawler/original-images-sha512.txt` are still used, or may be.
