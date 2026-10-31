"""ia tiles: the map tiles (Vassal's images) and the campaign maps' layouts (ImperialCommander2), staged for the data
repo's map tiles migration (data 2.0.0).

Writes staging/map-tiles/:
- manifest.json:
    {"tiles": [{"product", "number", "name", "side_a", "side_b"}],
     "layouts": [{"ic2": file, "name", "campaign", "mission": {"content_type", "id"} | null,
                  "tiles": [{"product", "number", "side", "count"}]}],
     "checks": {...}}
- images/map-tiles/<name>-<side>.png: the Vassal images, under the dataset's names;
- copies.csv: product, number, name, copies (1 each), for the maintainer to fill in with how many of each tile a box
  has.

A layout's count is how many times IC2 places the side in the mission, across all its map sections. Some maps are
built from sections that replace each other during the mission (Heart of the Empire's Into a Corner places tile 18B
44 times), so a count can exceed the copies in a box.

Each Vassal image is checked against IC2's size for its tile (64 px per square, plus 0 or 32 px on each axis for
the tabs). IC2's missions are matched to the dataset's campaign missions by name; a mission with no card (each
campaign's introduction and finale) has mission null. The bundled Aftermath save's tiles are checked against IC2's.
The tools only measure the images; they never look at them."""
import csv
import json
import shutil
from collections import Counter
from pathlib import Path

from ia_tools import ic2, settings, vassal
from ia_tools.match import normalise
from ia_tools.staging import slugify

SQUARE = 64
TABS = (0, 32)
# IC2's expansions, as the dataset's products.
EXPANSIONS = {
    'Core': 'Imperial Assault', 'Twin': 'Twin Shadows', 'Hoth': 'Return to Hoth', 'Bespin': 'The Bespin Gambit',
    'Jabba': "Jabba's Realm", 'Empire': 'Heart of the Empire', 'Lothal': 'Tyrants of Lothal',
}
# A tile's name starts with its product's: the Core Set's is "Imperial Assault", which the tiles don't say.
NAMES = {'Imperial Assault': 'Core Set'}
CAMPAIGN_TYPES = ('campaign-story-missions', 'campaign-threat-missions', 'campaign-hero-side-missions',
                  'campaign-ally-side-missions', 'campaign-regular-side-missions', 'agenda-cards')


def tile_name(product, number):
    return f'{NAMES.get(product, product)} {number:02d}'


def fits(size, squares):
    """Whether an image's (width, height) is the tile's squares, either way round, with or without tabs."""
    width, height = squares
    return any(size[0] - SQUARE * w in TABS and size[1] - SQUARE * h in TABS for w, h in ((width, height), (height, width)))


def campaign_missions(dataset):
    """{normalised name: [(content_type, id)]} for every campaign mission card."""
    found = {}
    for row in dataset.records('missions'):
        if row['content_type'] in CAMPAIGN_TYPES:
            card = next(r for r in dataset.records(row['content_type']) if r['id'] == row['content_id'])
            found.setdefault(normalise(card['name']), []).append((row['content_type'], card['id']))
    return found


def plan(module, cache, dataset):
    """(manifest, problems)."""
    from PIL import Image

    module = Path(module)
    pieces = vassal.tiles(module / 'buildFile')
    sizes = {(EXPANSIONS[t['expansion']], t['number']): (t['width'], t['height']) for t in cache['tiles']}
    problems, tiles = [], {}
    for piece in pieces:
        key = (piece['product'], piece['number'])
        with Image.open(module / 'images' / piece['image']) as image:
            size = image.size
        if key not in sizes:
            problems.append(f"{piece['piece']}: IC2 has no {key[0]} tile {key[1]}")
        elif not fits(size, sizes[key]):
            problems.append(f"{piece['piece']}: {size[0]}x{size[1]} px isn't {sizes[key][0]}x{sizes[key][1]} squares")
        tile = tiles.setdefault(key, {'product': key[0], 'number': key[1], 'name': tile_name(*key)})
        tile[f"side_{piece['side'].lower()}"] = piece['image']
    problems += [f'{tile_name(*key)}: no Vassal piece' for key in sizes if key not in tiles]
    problems += [f"{t['name']}: one side only" for t in tiles.values() if not ('side_a' in t and 'side_b' in t)]

    missions = campaign_missions(dataset)
    layouts = []
    for mission in cache['missions']:
        found = missions.get(normalise(mission['name']), [])
        if len(found) > 1:
            problems.append(f"{mission['file']} {mission['name']}: several missions have that name")
        used = []
        for texture, count in mission['tiles'].items():
            expansion, number, side = ic2.TEXTURE.match(texture).groups()
            used.append({'product': EXPANSIONS[expansion], 'number': int(number), 'side': side, 'count': count})
        layouts.append({'ic2': f"{mission['folder']}/{mission['file']}", 'name': mission['name'],
                        'campaign': mission['campaign'],
                        'mission': dict(zip(('content_type', 'id'), found[0])) if len(found) == 1 else None,
                        'tiles': used})
    matched = {(l['mission']['content_type'], l['mission']['id']) for l in layouts if l['mission']}
    problems += [f'{t} {i}: IC2 has no layout for it' for ids in missions.values() for t, i in ids if (t, i) not in matched]
    names = Counter(l['name'] for l in layouts)
    problems += [f'IC2 has {n} missions named {name}' for name, n in names.items() if n > 1]

    by_image = {p['image']: p for p in pieces}
    aftermath = {f"{by_image[i]['product']} {by_image[i]['number']}{by_image[i]['side']}": n
                 for i, n in vassal.save_tiles(module / 'Aftermath.vsav', set(by_image)).items()}
    ic2_aftermath = {f"{t['product']} {t['number']}{t['side']}": t['count']
                     for l in layouts if l['name'] == 'Aftermath' for t in l['tiles']}
    if aftermath != ic2_aftermath:
        problems.append(f'Aftermath: the Vassal save has {aftermath}, IC2 {ic2_aftermath}')
    order = list(EXPANSIONS.values())
    manifest = {'ic2_commit': cache['commit'],
                'tiles': sorted(tiles.values(), key=lambda t: (order.index(t['product']), t['number'])),
                'layouts': layouts,
                'checks': {'images': len(pieces), 'tiles': len(tiles), 'layouts': len(layouts),
                           'matched': len(matched), 'without a mission': [l['name'] for l in layouts if not l['mission']],
                           'aftermath save': aftermath == ic2_aftermath}}
    return manifest, problems


def run(module, cache, dataset, out=None):
    out = Path(out or settings.STAGING / 'map-tiles')
    manifest, problems = plan(module, cache, dataset)
    if problems:
        return manifest, problems
    images = out / 'images' / 'map-tiles'
    images.mkdir(parents=True, exist_ok=True)
    for tile in manifest['tiles']:
        for side in ('a', 'b'):
            target = f"{slugify(tile['name'])}-{side}.png"
            shutil.copyfile(Path(module) / 'images' / tile[f'side_{side}'], images / target)
            tile[f'side_{side}'] = f'map-tiles/{target}'
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    with open(out / 'copies.csv', 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['product', 'number', 'name', 'copies'])
        writer.writerows([t['product'], t['number'], t['name'], 1] for t in manifest['tiles'])
    return manifest, []
