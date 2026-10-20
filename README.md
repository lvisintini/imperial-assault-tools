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
uv run ia scrape --gaps          # or: everything the audit found missing, from any product, into staging/gaps/
uv run ia wiki                   # cache every product's components and copies from the wiki
uv run ia wiki --propose         # stage edits to every source's code, dates, wave and type, from that cache
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
- **`ia scrape <album>...`** downloads one or more albums into `staging/<product>/`. It writes `originals/` plus a
  `manifest.json` with each image's album path, guessed content type, hints (affiliation, tier, hero, ...), size and
  hash, and any dataset records with the same name. Album covers no album lists are staged too: boardwars keeps some
  card backs only as a cover. To stage more of a product that's already imported, scrape just the albums you need into
  a new folder with `--folder <name>`, so the product's staging (and its import log) stays as it was.
- **`ia scrape --gaps`** stages every image the last audit found **unseen** into `staging/gaps/`, whatever product it
  comes from. Each staged image records the existing product it belongs to: its album's, or for the skirmish maps
  (whose album doesn't say) the one `SKIRMISH_MAP_PRODUCTS` in `ia_tools/classify.py` names. The folder has no product of
  its own, so in `ia enter` each image's page has a **product** field, pre-filled from the scrape.
- **`ia wiki`** caches what every product contains, and how many copies, from the
  [Imperial Assault wiki](https://imperial-assault.fandom.com/wiki/Imperial_Assault): each product page the main page
  lists, through the MediaWiki API, into `staging/wiki/` (`pages/` holds the raw answers, `products.json` the parsed
  components with their headings, counts and notes, plus each product's code, wave, dates and dataset source id).
  Fetched pages are reused; `--refresh` fetches them again. The pages are written by hand, so the parse keeps every
  component's raw line and leaves matching components to records to whoever reads it. Packs that ship inside another
  product (Luke and Vader in the Core Set) get no source id until the dataset has `sources.included_in`.
  `ia wiki --propose [FOLDER]` reads the cache instead (no network) and stages an `ia propose` edit (folder
  `wiki-sources` by default) for every source whose `product_code`, `announced_date`, `release_date`, `wave` or
  `type` differs from the wiki's. The dates and wave come from the main page, and the type from the product page's
  infobox. Sources that already have a proposal in the folder are left alone, so it can be run again.
- **`ia propose <type> <id> field=value...`** proposes a change to an existing record (a rename, a corrected field)
  into a staging folder (`edits` unless `--folder` says otherwise), with an optional `--note`. Values are JSON when
  they parse as JSON (`wave=2`) and text otherwise (`name=IG-88`).
- **`ia enter`** is a local web app. For each image it shows the original, a preview of how it will be imported, and an
  existing card of the same type. You decide what each image is:
  - a new record, using a form built from the dataset's JSON Schemas;
  - the same card as an existing record, which only adds a `source-contents` row;
  - an extra image for another card (a hero's wounded side);
  - skip for now, or never import.

  Agenda decks and imperial classes, which have no image, are added under "Records without an image". Proposed changes
  to existing records are under "Edits to existing records": change the values if you want, choose whether the image
  files are renamed to match, and apply or skip each one. Decisions are saved as you go to
  `staging/<product>/entries.json`.
- **`ia import <product>`** checks everything first: schemas, ids, foreign keys, image paths, and that each iaspec is
  unique and follows the dataset's rule (`elite` for elite non-unique cards, then the name; see `ia_tools/iaspec.py`).
  If anything fails it reports every problem and writes nothing. Otherwise it:
  - assigns the next ids;
  - writes the records in the dataset's exact JSON format;
  - adds the `source-contents` rows;
  - writes the large and small PNGs at the sizes the dataset's tests expect;
  - appends the imported originals' hashes to the register;
  - applies the edits you chose, moving image files when they're renamed. A rename is refused while a card back's
    `variant` still holds the old name.

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
