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
uv run ia skirmish-maps          # data 2.0.0: check the skirmish and raid maps' reviewed tile placements
uv run ia skirmish-maps --write  # write their rows into map-layouts.json, and their images drawn from the tiles
uv run ia hires-tiles            # the tile scans (tiles/) fitted onto ours at 128 px per square, with a review page
uv run ia tile-orientation       # which way up each side's number pill reads, on its scan and our image, with a review page
uv run ia tile-orientation --write  # store every side upright in the data repo, its placements turned to match
uv run ia card-types --fetch     # data 2.0.0: cache the wiki's card text, to propose card types
uv run ia card-types --check     # validate the card types confirmed in ia enter (Card types)
uv run ia card-types             # write them into reward-cards.json and imperial-class-cards.json
uv run ia missions --check       # data 2.0.0: validate the scenarios and story rewards entered in ia enter (Missions)
uv run ia missions               # write them into skirmish-missions.json and mission-rewards.json
uv run ia mats                   # data 2.0.0: stage the 13 skirmish map mats as sources in staging/mats/ (migration 19)
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
  positions and rotations (`ia ic2`) and the Vassal module's tile images as the data repo stores them (turned
  upright by `ia tile-orientation --write`): 64 px per square, tiles only (no doors or
  tokens), transparent around them. IC2's own tile images, fetched once into `staging/ic2/textures/`, only tell which
  way each Vassal image is turned: by their colours, or, when that's close, by which turn fits the neighbouring tiles'
  tabs into their notches. Aftermath's turns are checked against the Vassal module's Aftermath save. A map whose
  sections replace each other during the mission is drawn with its start section only. `--write` puts the images in
  the data repo, and each map's `map-layouts.json` rows: its tile sides' copies, and where each image places them.
- **`ia skirmish-maps`** (data 2.0.0) writes the skirmish, four-player and raid maps' `map-layouts.json` rows from
  their tile placements, `staging/skirmish-maps/final.json`. No source has them: they were found by matching each
  map's tile sides against the Vassal skirmish module's boards (`vassal-2/`) and our map images, and reviewed map by
  map (the prototype and the rulings are in `staging/skirmish-maps/`). Rows hold each side's copies and placements
  (`ia_tools/layouts.py`); `ia maps --write` writes the campaign maps' the same way. `--write` also draws each map's
  image from its rows and the tiles' images, like the campaign maps (in place of the Skirmish Map Project's).
  Every map image is framed on its tiles' squares plus 16 px all round (`campaign_maps.compose`), so a square's
  pixel position follows from the placements.
- **`ia hires-tiles`** fits the maintainer's tile scans (`tiles/<Prefix>_<n><side>.png`, ~299 px per square, cut on
  their outline, any turn) onto the dataset's tile images at 128 px per square: SIFT and a similarity (or, for a
  plain tile, its outline at each quarter turn), refined by ECC, then drawn into the dataset side's frame (so grids
  and tabs land where ours are), with one tone curve per product histogram-matched to ours (chosen from samples in
  `staging/tile-samples/`). It stages them in `staging/hires-tiles/` with a manifest and a review page: every side
  in file order, a collapsible section per product, flagged fits marked (a weak fit, or a scan that fits another
  side's image better), and for each side the spot of a map where it touches the most other tiles, drawn with the
  current tiles and with the new ones. `--only` refits some sides (keeping the last full run's tone curves),
  `--review` rebuilds the page. The 13 sides scanned later, several to a page, were cut out of their scans by
  `staging/missing-tiles/`.
- **`ia tile-orientation`** finds which way up each tile side's number pill (its product's icon, two digits and a
  smaller A or B) reads, on its scan and on the dataset's image, so every side can be stored upright. Each product's
  pill template is bootstrapped from the scans' pills that segment as upright (two tall glyphs, then a shorter one on
  their baseline), then rebuilt from every pill it finds clearly; it's matched on each scan at the 4 quarter turns.
  Each scan's code is read from its glyph cells by their nearest neighbours among the other scans' (labelled with
  their sides' codes; Tesseract can't read the font), so a scan of the wrong side shows. Our images (64 px per
  square) are too small to read: their turn is the scan's turn through its `ia hires-tiles` fit, checked by matching
  the shrunk template. `staging/tile-orientation/` gets `turns.json` and a review page listing the sides that need a
  new scan (the same file as another side's, or reading another code), the Vassal images that are another side's,
  and the ones to check; `rulings.json` (`{"side key": {"scan": turn, "vassal": turn}}`) overrides a turn.
  `--write` turns the data repo's tile images upright (once: every image must still be the Vassal module's), with
  `map-tiles.json`'s width and height, every `map-layouts.json` placement's rotation (rotation − turn) and the
  skirmish maps' `final.json` turns to match, so `ia maps --write` and `ia skirmish-maps --write` draw every map the
  same.
- **Card types** (data 2.0.0; `/card-types`) goes through the reward Feats and the Imperial class cards, a tab each,
  with their `type` (Feat, or Group Attachment for a card attached to an Imperial deployment group) proposed from the
  wiki's text, which is shown under each card. Flags point at what needs a closer look: no text, or a name the wiki
  spells differently. Mark cards done one by one or all those shown; entries are saved to
  `staging/card-types/entries.json`, and `ia card-types` writes them once every card is done.
- **Missions** (data 2.0.0; `/missions`) has two views. *Skirmish scenarios* shows the skirmish mission cards by map,
  each with A/B buttons for the letter printed on it. *Story rewards* goes through the story missions one at a time:
  add reward cards or Campaign deployment cards from the search box, or credits, mark alternatives as *choice*, and
  mark the mission done (with no rows if it gives none). Entries are saved to `staging/mission-entries/entries.json`;
  `ia missions` writes them only once every card has a scenario, replacing the rows of the story missions marked done.
  Story mission cards give no rewards, so none are required.

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
