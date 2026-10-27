"""The map layouts the maintainer enters by hand in ia enter (its Map layouts page), and ia layouts, which writes them
to the data repo's map-layouts.json (data 2.0.0).

ImperialCommander2 has the campaign maps' layouts (ia tiles); no source has the skirmish and raid maps', so those are
entered here, map by map, from the map's image, its rules sheet and the Skirmish Guide.

staging/map-layouts/entries.json:
    {"maps": {"<map id>": {"tiles": [{"tile_id": "<id>", "side": "A", "count": 2}], "done": true, "note": "..."}}}

The maps entered here are those of the skirmish and raid missions, and any other map with no layout yet. ia layouts
writes the maps marked done, replacing the rows they had; the other maps' rows stay as they are. A map can't use more
copies of a tile (both sides together) than all the products hold."""
import json
from collections import Counter

from ia_tools import settings
from ia_tools.dataset import dumps

ENTRY_TYPES = ('skirmish-mission-cards', 'raid-missions')
SIDES = ('A', 'B')
# The tile codes typed in the panel's quick add, as the Vassal module names its pieces ("05A", "TS 1A", "HotE01A").
CODES = {
    'Imperial Assault': '', 'Twin Shadows': 'TS', 'Return to Hoth': 'H', 'The Bespin Gambit': 'BG',
    "Jabba's Realm": 'JR', 'Heart of the Empire': 'HotE', 'Tyrants of Lothal': 'ToL',
}


def entries_path():
    return settings.STAGING / 'map-layouts' / 'entries.json'


def load():
    path = entries_path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'maps': {}}


def save(entries):
    path = entries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')


def products_of(dataset, content_type):
    """{record id: [source names]} through source-contents."""
    names = {s['id']: s['name'] for s in dataset.records('sources')}
    found = {}
    for row in dataset.records('source-contents'):
        if row['content_type'] == content_type:
            found.setdefault(row['content_id'], []).append(names[row['source_id']])
    return found


def tiles(dataset):
    """[{"id", "name", "number", "product", "code", "copies", "side_a", "side_b"}] in the file's order. copies is the
    copies in all products together."""
    names = {s['id']: s['name'] for s in dataset.records('sources')}
    product, copies = {}, Counter()
    for row in dataset.records('source-contents'):
        if row['content_type'] == 'map-tiles':
            product.setdefault(row['content_id'], names[row['source_id']])
            copies[row['content_id']] += row['quantity']
    return [{'id': t['id'], 'name': t['name'], 'number': t['number'], 'product': product.get(t['id']),
             'code': CODES.get(product.get(t['id']), ''), 'copies': copies[t['id']],
             'side_a': t['side_a'], 'side_b': t['side_b']} for t in dataset.records('map-tiles')]


def maps(dataset):
    """The maps entered here, in maps.json's order: [{"id", "name", "image", "missions", "products", "rows"}], rows
    being the layout rows the data has for the map."""
    cards = {}
    for content_type in {m['content_type'] for m in dataset.records('missions')}:
        cards |= {(content_type, r['id']): r['name'] for r in dataset.records(content_type)}
    mission_products = products_of(dataset, 'missions')
    missions = {}
    for mission in dataset.records('missions'):
        if mission['map_id']:
            missions.setdefault(mission['map_id'], []).append(mission)
    rows = Counter(r['map_id'] for r in dataset.records('map-layouts'))
    found = []
    for record in dataset.records('maps'):
        own = missions.get(record['id'], [])
        if not (any(m['content_type'] in ENTRY_TYPES for m in own) or not rows[record['id']]):
            continue
        products = sorted({p for m in own for p in mission_products.get(m['id'], [])})
        found.append({'id': record['id'], 'name': record['name'], 'image': record['image'],
                      'missions': [cards[m['content_type'], m['content_id']] for m in own],
                      'products': products, 'rows': rows[record['id']]})
    return found


def panel(dataset):
    """What the Map layouts page shows."""
    entries = load()
    return {'maps': maps(dataset), 'tiles': tiles(dataset), 'products': list(CODES), 'codes': CODES,
            'entries': entries['maps'],
            'problems': {map_id: check_map(entry, dataset) for map_id, entry in entries['maps'].items()}}


def check_map(entry, dataset, known_tiles=None):
    """Problems with one map's entry."""
    known = known_tiles or {t['id']: t for t in tiles(dataset)}
    problems, used, seen = [], Counter(), set()
    for row in entry.get('tiles', []):
        tile = known.get(row.get('tile_id'))
        if tile is None:
            problems.append(f"Unknown tile {row.get('tile_id')!r}")
            continue
        label = f"{tile['name']}{row.get('side')}"
        if row.get('side') not in SIDES:
            problems.append(f"{tile['name']}: side {row.get('side')!r} isn't A or B")
        count = row.get('count')
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            problems.append(f'{label}: count {count!r} isn\'t a whole number of at least 1')
            continue
        if (tile['id'], row.get('side')) in seen:
            problems.append(f'{label} is listed twice')
        seen.add((tile['id'], row.get('side')))
        used[tile['id']] += count
    for tile_id, count in used.items():
        if count > known[tile_id]['copies']:
            problems.append(f"{known[tile_id]['name']}: {count} used, but the products have {known[tile_id]['copies']}")
    if entry.get('done') and not entry.get('tiles'):
        problems.append('Marked done with no tiles')
    return problems


def plan(dataset, entries=None):
    """(rows, summary, problems): the whole map-layouts file after importing the done maps."""
    entries = (entries or load())['maps']
    enterable = {m['id']: m for m in maps(dataset)}
    known = {t['id']: t for t in tiles(dataset)}
    problems = [f'{map_id}: not a map entered here' for map_id in entries if map_id not in enterable]
    done = [m for m in enterable if entries.get(m, {}).get('done')]
    for map_id in done:
        problems += [f"{enterable[map_id]['name']}: {p}" for p in check_map(entries[map_id], dataset, known)]
    replaced = set(done)
    rows = [r for r in dataset.records('map-layouts') if r['map_id'] not in replaced]
    for map_id in done:
        rows += [{'map_id': map_id, 'tile_id': t['tile_id'], 'side': t['side'], 'count': t['count']}
                 for t in entries[map_id]['tiles']]
    summary = {'maps': len(enterable), 'done': len(done), 'left': len(enterable) - len(done),
               'rows': sum(len(entries[m]['tiles']) for m in done),
               'replacing': sum(1 for m in done if enterable[m]['rows'])}
    return rows, summary, problems


def run(dataset, check=False):
    """(summary, problems); writes map-layouts.json unless checking or there are problems."""
    rows, summary, problems = plan(dataset)
    if not problems and not check:
        dataset.path('map-layouts').write_text(dumps(rows), encoding='utf-8')
    return summary, problems
