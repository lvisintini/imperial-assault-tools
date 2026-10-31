"""ia wiki --skirmish: every skirmish mission card, its map and format, and its card image, from the Imperial Assault
wiki (data 2.0.0's skirmish-missions; the wiki is this collection's image source, as boardwars has none).

The wiki's "Skirmish Mission" page lists every skirmish map with its two missions, under the product they come in:

    [[Core Set]]
    * Mos Eisley Outskirts [[Mos Eisley Outskirts map|(Map)]]
    ** [[Get to the Ship]]
    ** [[Smuggled Goods]]

Each mission's page has an infobox with the card image (`image1`), the product (`source`) and, for four-player
missions, `type` ("Four Player Team Battle", "Four Player Free-For-All"). ia wiki --skirmish caches the pages, downloads
the card images to staging/wiki/skirmish/, and writes staging/wiki/skirmish.json, in the overview's order:

    {"missions": [{"name", "page", "map": {"text", "id"}, "format", "source": raw text, "source_id",
                   "image": {"file", "url", "sha1", "width", "height", "path"}, "problems": [...]}]}

The map comes from the overview (some infoboxes have none); a map the dataset can't place is a problem. The data
repo's skirmish missions migration reads this file; its images are written from the downloaded originals."""
import hashlib
import json
import re
from datetime import datetime, timezone

from ia_tools import settings
from ia_tools.match import NameIndex, normalise
from ia_tools.staging import slugify
from ia_tools.wiki import API_URL, LINK, clean, source_for
from ia_tools.wiki_missions import BATCH, fetch_pages, infobox

OVERVIEW = 'Skirmish Mission'
WIKI = 'https://imperial-assault.fandom.com/'
INFOBOX = re.compile(r'\{\{\s*Skirmish[ _]Mission[ _]Infobox', re.I)
FORMATS = ('Standard', 'Four Player Team Battle', 'Four Player Free-For-All')
# The overview's map names that aren't the dataset's.
MAP_ALIASES = {
    'Chopper Base, Atallon': 'Chopper Base Atollon', 'Imperial Labor Camp': 'Imperial Labour Camp',
    'Moisture Farms': 'Moisture Farm', 'Mustafar Command Hub': 'Imperial Command Hub',
}


def parse_overview(wikitext):
    """[{"product", "map", "mission"}] from the overview page, in its order."""
    product, map_, found = None, None, []
    for line in wikitext.splitlines():
        if line.startswith('**'):
            links = LINK.findall(line)
            found.append({'product': product, 'map': map_, 'mission': links[0][0] if links else clean(line[2:])})
        elif line.startswith('*'):
            text = re.sub(r'\[\[[^\]|]*\|\(Map\)\]\]', '', line[1:])  # "[[Mos Eisley Outskirts map|(Map)]]"
            map_ = re.sub(r'\s*\(Map\)\s*$', '', clean(text)).strip()
        elif line.startswith('[[') and not re.match(r'\[\[(File|Image|Category):', line, re.I):
            product = clean(line)
    return found


def image_info(client, files):
    """{file: imageinfo (url, size, sha1)} for wiki file names."""
    found = {}
    for i in range(0, len(files), BATCH):
        batch = files[i:i + BATCH]
        answer = client.get(API_URL, params={
            'action': 'query', 'prop': 'imageinfo', 'iiprop': 'size|mime|sha1|url', 'format': 'json',
            'formatversion': 2, 'titles': '|'.join(f'File:{f}' for f in batch)}).json()['query']
        renamed = {n['from']: n['to'] for n in answer.get('normalized', [])}
        pages = {p['title']: p for p in answer['pages']}
        for f in batch:
            page = pages.get(renamed.get(f'File:{f}', f'File:{f}'), {})
            found[f] = page['imageinfo'][0] if 'imageinfo' in page else None
    return found


def download(client, url):
    """An uploaded file's original bytes. The image server answers only requests that come from the wiki's pages
    (Referer), and converts to WebP unless asked for the original."""
    client.session.headers['Referer'] = WIKI
    return client.get(url, params={'format': 'original'}).content


def run(client, dataset, root=None, refresh=False, log=print):
    out = (root or settings.STAGING) / 'wiki'
    (out / 'pages').mkdir(parents=True, exist_ok=True)
    (out / 'skirmish').mkdir(exist_ok=True)
    overview = fetch_pages(client, out, 'skirmish', {OVERVIEW: [OVERVIEW]}, lambda p: bool(p['wikitext']), refresh,
                           log)[OVERVIEW]
    listing = parse_overview(overview['wikitext'])
    pages = fetch_pages(client, out, 'skirmish', {m['mission']: [m['mission']] for m in listing},
                        lambda p: infobox(p['wikitext'], INFOBOX) is not None, refresh, log)
    fields = {name: infobox(page['wikitext'], INFOBOX) for name, page in pages.items()}
    files = sorted({f.get('image1') or f.get('image') for f in fields.values()} - {None, ''})
    info = image_info(client, files)

    maps = {normalise(m['name']): m for m in dataset.records('maps')}
    index = NameIndex(dataset, ['sources'])
    missions = []
    for listed in listing:
        name, problems = listed['mission'], []
        box = fields.get(name)
        if box is None:
            missions.append({'name': name, 'page': None, 'problems': ['no wiki page with a skirmish mission infobox']})
            continue
        map_ = maps.get(normalise(MAP_ALIASES.get(listed['map'], listed['map'])))
        if map_ is None:
            problems.append(f"map {listed['map']!r} not in the dataset")
        own_map = clean(box.get('map', ''))
        if map_ and own_map and normalise(MAP_ALIASES.get(own_map, own_map)).removesuffix('skirmishmap') \
                != normalise(map_['name']):
            problems.append(f"the page's map {own_map!r} isn't the overview's {listed['map']!r}")
        format_ = box.get('type') or 'Standard'
        if format_ not in FORMATS:
            problems.append(f'unknown format {format_!r}')
        source_text = clean(box.get('source', ''))
        source_id = source_for(index, source_text) if source_text else None
        file = box.get('image1') or box.get('image')
        image = None
        if not file or not info.get(file):
            problems.append('no card image')
        else:
            meta = info[file]
            path = out / 'skirmish' / f'{slugify(name)}{"." + file.rsplit(".", 1)[-1].lower()}'
            if refresh or not path.exists() or hashlib.sha1(path.read_bytes()).hexdigest() != meta['sha1']:
                path.write_bytes(download(client, meta['url']))
                log(f'downloaded {file}')
            if hashlib.sha1(path.read_bytes()).hexdigest() != meta['sha1']:
                problems.append(f'{file}: the download is not the wiki\'s original (sha1 differs)')
            image = {'file': file, 'url': meta['url'], 'sha1': meta['sha1'], 'width': meta['width'],
                     'height': meta['height'], 'path': str(path.relative_to(out))}
        missions.append({'name': name, 'page': pages[name]['title'], 'revid': pages[name]['revid'],
                         'map': {'text': listed['map'], 'id': map_ and map_['id']}, 'format': format_,
                         'source': source_text or None, 'source_id': source_id, 'image': image, 'problems': problems})
    cache = {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'api': API_URL,
             'overview_revid': overview['revid'], 'missions': missions}
    (out / 'skirmish.json').write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding='utf-8')
    return cache
