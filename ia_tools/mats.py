"""The skirmish map mats (data 2.0.0, #47): FFG sold 13 skirmish maps on their own, as neoprene mats with their own
product codes. ia mats stages each as a source: its values from the wiki cache, and its image from FFG's product page,
as the Wayback Machine archived it (FFG's site is gone, and boardwars has no mat images).

- name, product_code: the mat page's infobox (name, sku), e.g. "Training Ground", SWI38.
- wave: the main page's wave for the mat (8 to 11). announced_date: null (the main page's dates are the waves').
- release_date: the infobox's, or null where it has none.
- map: the map record of the same name (MAP_NAMES where the product's name differs from the map's).
- image: the product page's og:image, fitted to the sources' size like boardwars' originals (images.process).

staging/mats/:
    originals/<sku>.<ext>, the downloaded images (fetched once);
    large/sources/<slug>.png and small/sources/<slug>.png;
    manifest.json: {"mats": [{"product_code", "name", "wave", "release_date", "map_id", "map", "image",
                              "original", "page", "snapshot"}]}
The data repo's migration 19 reads the manifest."""
import json
import re
from datetime import datetime
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


def parse_date(text):
    """An infobox date ("2016-07-14", "28 Feb 2019") as YYYY-MM-DD, or None."""
    for pattern in ('%Y-%m-%d', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime((text or '').strip(), pattern).date().isoformat()
        except ValueError:
            pass
    return None


def mats(dataset):
    """[{"product_code", "name", "wave", "release_date", "map_id", "map", "page"}] for the wiki cache's skirmish map
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
                      'release_date': parse_date(box.get('release_date')), 'map_id': maps.get(map_name),
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
    """(manifest, problems): stage every mat's image and the manifest."""
    found, problems = mats(dataset)
    if problems:
        return None, problems
    out = out_dir()
    for mat in found:
        path, snapshot = original(client, mat, log)
        processed = images.process(path, 'sources')
        mat['image'] = f"sources/{slugify(mat['name'])}.png"
        mat['original'] = path.name
        mat['snapshot'] = snapshot
        mat['upscaled'] = processed['upscaled']
        for size in ('large', 'small'):
            target = out / size / mat['image']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(processed[size])
    manifest = {'mats': found}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest, []
