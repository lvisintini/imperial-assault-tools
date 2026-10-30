"""The skirmish map mats (data 2.0.0, #47): FFG sold 13 skirmish maps on their own, as neoprene mats with their own
product codes. ia mats stages each as a source: its values from the wiki cache, and its image from FFG's product page,
as the Wayback Machine archived it (FFG's site is gone, and boardwars has no mat images).

- name, product_code: the mat page's infobox (name, sku), e.g. "Training Ground", SWI38.
- wave, announced_date, release_date: the main page's, which lists each mat under a wave with that wave's dates, as
  for every other source. The mat pages' own release dates don't fit them (some precede their wave's announcement),
  so they aren't used.
- map: the map record of the same name (MAP_NAMES where the product's name differs from the map's).
- image: the product page's og:image, fitted to the sources' size like boardwars' originals (images.process).

staging/mats/:
    originals/<sku>.<ext>, the downloaded images (fetched once);
    large/sources/<slug>.png and small/sources/<slug>.png;
    manifest.json: {"mats": [{"product_code", "name", "wave", "announced_date", "release_date", "map_id", "map",
                              "image", "original", "page", "snapshot", "upscaled"}]}
The data repo's migration 19 reads the manifest."""
import json
import re
from pathlib import PurePosixPath

from ia_tools import images, settings, wiki
from ia_tools.card_types import infobox
from ia_tools.staging import slugify

WAYBACK = 'https://web.archive.org/web/2019/'
OG_IMAGE = re.compile(r'<meta property="og:image" content="([^"]+)"')
PRODUCT_PAGE = re.compile(r'\[(https?://www\.fantasyflightgames\.com/\S+)')
# Mats whose product is named differently from its map.
MAP_NAMES = {'Anchorhead Cantina': 'Anchorhead Bar', 'Mos Eisley Back Alley': 'Mos Eisley Back Alleys'}


def out_dir():
    return settings.STAGING / 'mats'


def mats(dataset):
    """[{"product_code", "name", "wave", "announced_date", "release_date", "map_id", "map", "page"}] for the wiki cache's skirmish map
    products, in product code order, and the problems found."""
    pages = settings.STAGING / 'wiki' / 'pages'
    maps = {m['name']: m['id'] for m in dataset.records('maps')}
    found, problems = [], []
    for product in wiki.load()['products']:
        path = pages / f"{slugify(product['title'])}.json"
        if not path.exists():
            continue
        _, box = infobox(json.loads(path.read_text(encoding='utf-8'))['parse']['wikitext'])
        if box.get('type') != 'Skirmish Map':
            continue
        name = box['name']
        map_name = MAP_NAMES.get(name, name)
        wave = re.fullmatch(r'Wave (\d+)', product['wave'] or '')
        link = PRODUCT_PAGE.search(box.get('link', ''))
        if map_name not in maps:
            problems.append(f'{name}: no map named {map_name!r}')
        if not link:
            problems.append(f'{name}: no FFG product page on the wiki')
        found.append({'product_code': box['sku'], 'name': name, 'wave': int(wave.group(1)) if wave else None,
                      'announced_date': wiki.parse_date(product['announced']),
                      'release_date': wiki.parse_date(product['released']), 'map_id': maps.get(map_name),
                      'map': map_name, 'page': link and link.group(1)})
    return sorted(found, key=lambda m: m['product_code']), problems


def original(client, mat, log=print):
    """(path of the downloaded image, snapshot URL): the archived product page's og:image, fetched once."""
    folder = out_dir() / 'originals'
    folder.mkdir(parents=True, exist_ok=True)
    meta = folder / f"{mat['product_code']}.json"
    if meta.exists():
        cached = json.loads(meta.read_text(encoding='utf-8'))
        return folder / cached['file'], cached['snapshot']
    page = client.get(WAYBACK + mat['page'])
    found = OG_IMAGE.search(page.text)
    if not found:
        raise ValueError(f"{mat['name']}: no og:image on {page.url}")
    url = found.group(1)
    path = folder / f"{mat['product_code']}{PurePosixPath(url).suffix.lower() or '.png'}"
    path.write_bytes(client.get(url).content)
    meta.write_text(json.dumps({'snapshot': page.url, 'image': url, 'file': path.name}, indent=2), encoding='utf-8')
    log(f"{mat['product_code']} {mat['name']}: {url}")
    return path, page.url


def run(client, dataset, log=print):
    """(manifest, problems): stage every mat's image and the manifest. Images already staged are kept (each encode is
    a TinyPNG compression), so a run for new values only rewrites the manifest."""
    found, problems = mats(dataset)
    if problems:
        return None, problems
    out = out_dir()
    path = out / 'manifest.json'
    before = {m['product_code']: m for m in json.loads(path.read_text(encoding='utf-8'))['mats']} if path.exists() \
        else {}
    for mat in found:
        source, snapshot = original(client, mat, log)
        mat['image'] = f"sources/{slugify(mat['name'])}.png"
        mat['original'] = source.name
        mat['snapshot'] = snapshot
        targets = {size: out / size / mat['image'] for size in ('large', 'small')}
        if mat['product_code'] in before and all(t.exists() for t in targets.values()):
            mat['upscaled'] = before[mat['product_code']]['upscaled']
            continue
        processed = images.process(source, 'sources')
        mat['upscaled'] = processed['upscaled']
        for size, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(processed[size])
    manifest = {'mats': found}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest, []
