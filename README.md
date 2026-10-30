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
uv run ia wiki --missions        # cache each campaign mission's hero and rewards (staging/wiki/missions.json)
uv run ia stage epilogues --type epilogue-cards --tts save.zip   # stage images that aren't on boardwars
uv run ia enter                  # opens http://localhost:8001: go through the cards
uv run ia import tyrants-of-lothal --check   # validate only
uv run ia import tyrants-of-lothal           # write records, images and source-contents rows
uv run ia maps --sample Aftermath   # data 2.0.0: draw campaign maps from IC2's layouts (all of them without --sample)
uv run ia layouts --check        # data 2.0.0: validate the map layouts entered in ia enter (Map layouts)
uv run ia layouts                # write them into map-layouts.json
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
  `ia wiki --missions` fetches every mission record's page (story, threat and side mission cards, agenda cards that are
  missions) and every hero's page, and writes `staging/wiki/missions.json`, keyed by record id: each mission's hero
  (from its infobox, else from the hero page that names it) and its rewards (`reward`, `imperial_reward`,
  `threat_reward`) matched to reward and deployment cards, credits, and "Any 1 <category> ally" as a choice of the
  category's cards. A group ally is its regular card. Anything it can't place is listed as a problem, not guessed.
  Data 2.0.0's missions migration reads this file.
- **`ia stage <slug> --type <type> [files] [--tts SAVE] [--product NAME]`** stages images that aren't on boardwars
  into `staging/<slug>/`, in the scraper's format, for `ia enter` and `ia import`: image files, or a Tabletop
  Simulator saved object (`--tts`, a .zip with its `Mods/Images`). From a save, every card's face is an item of
  `--type` and every distinct back a card back of it, named by position ("Card 3", "Back B, of cards 3 and 4").
  Single-card images only (no sheets).
- **`ia propose <type> <id> field=value...`** proposes a change to an existing record (a rename, a corrected field)
  into a staging folder (`edits` unless `--folder` says otherwise), with an optional `--note`. Values are JSON when
  they parse as JSON (`wave=2`) and text otherwise (`name=IG-88`).
- **`ia enter`** is a local web app. For each image it shows the original, a preview of how it will be imported, and an
  existing card of the same type. You decide what each image is:
  - a new record, using a form built from the dataset's JSON Schemas. In data 2.0.0 a card's `back_id` is picked
    from the existing backs or a back staged with it, and is pre-filled with the back its existing siblings share
    (the same hero, class or deck; deployment cards of its affiliation; upgrades of its tier; or every card of its
    type), else the back staged for it. A new back is named `<deck>: <variant>` ("Rebel Hero: Biv Bodhrik");
  - the same card as an existing record, which only adds a `source-contents` row;

  With data 2.0.0, a new or linked card also has a **copies** field: how many of it the product has
  (`source-contents.quantity`, 1 unless you change it).
  - an extra image for another card (a hero's wounded side);
  - skip for now, or never import.

  Agenda decks, imperial classes and (data 2.0.0) miniatures, which have no image, are added under "Records without
  an image", each with its copies in the product. Proposed changes
  to existing records are under "Edits to existing records": change the values if you want, choose whether the image
  files are renamed to match, and apply or skip each one. Decisions are saved as you go to
  `staging/<product>/entries.json`.
- **`ia import <product>`** checks everything first: schemas, ids, foreign keys, image paths, and that each iaspec is
  unique and follows the dataset's rule (`elite` for elite non-unique cards, then the name; see `ia_tools/iaspec.py`).
  If anything fails it reports every problem and writes nothing. Otherwise it:
  - assigns ids (the next numbers in data 1.x, new UUIDs from 2.0.0);
  - writes the records in the dataset's exact JSON format;
  - adds the `source-contents` rows. In data 2.0.0 a mission card (and an agenda card that is a mission) gets a
    `missions` index row, and its product row points at that row instead of the card;
  - writes the large and small PNGs at the sizes the dataset's tests expect. A data 2.0.0 card back is sized as the
    cards whose `back_id` it is, or (when no staged card uses it) as the scrape guessed;
  - appends the imported originals' hashes to the register;
  - applies the edits you chose, moving image files when they're renamed. In data 1.x a rename is refused while a card
    back's `variant` still holds the old name.

  It never overwrites an existing image.
- **`ia maps`** (data 2.0.0) draws the campaign maps into `staging/campaign-maps/`, from ImperialCommander2's tile
  positions and rotations (`ia ic2`) and the Vassal module's tile images: 64 px per square, tiles only (no doors or
  tokens), transparent around them. IC2's own tile images, fetched once into `staging/ic2/textures/`, only tell which
  way each Vassal image is turned: by their colours, or, when that's close, by which turn fits the neighbouring tiles'
  tabs into their notches. Aftermath's turns are checked against the Vassal module's Aftermath save. A map whose
  sections replace each other during the mission is drawn with its start section only.
- **Map layouts** (data 2.0.0; `ia enter`'s Map layouts page, `/layouts`) is where the skirmish and raid maps' tiles
  are entered, since no source has them (the campaign maps' come from ImperialCommander2, through `ia tiles`). Each
  map's image is shown next to the tile sides picked for it, with their counts. Sides are added from the tile grid
  (filtered by product) or typed as Vassal names the pieces (`05A` for the Core Set, `TS 1B`, `JR3A x2`). A map
  can't use more copies of a tile than the products hold. Entries are saved to `staging/map-layouts/entries.json`;
  `ia layouts` writes the maps marked done into `map-layouts.json`, replacing the rows they had.

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
