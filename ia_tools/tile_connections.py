"""Tile connections (data 2.0.0): how many connector tabs each map tile has (the same on both sides), counted by the
maintainer on ia enter's Tile connections page, one key per tile. ia tile-connections writes them into the data repo's
map-tiles.json, as `connections` after `height`.

Entries are saved to staging/tile-connections/entries.json:
    {"tiles": {"<tile id>": {"connections": 3}}, "confirmed": true}
ia tile-connections writes only when every tile has a number and the maintainer has confirmed them (any later change
takes the confirmation back).

The page's last step flags tiles whose number differs from a count of the tabs on side A's outline (outline_tabs): a
second look, shown only after every tile is entered so it never steers the count."""
import json

from ia_tools import settings
from ia_tools.dataset import dumps

FIELD = 'connections'
AFTER = 'height'
LIMIT = 9  # one key per tile


def entries_path():
    return settings.STAGING / 'tile-connections' / 'entries.json'


def load():
    path = entries_path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'tiles': {}, 'confirmed': False}


def save(entries):
    path = entries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')


def set_tile(tile_id, connections):
    """Save one tile's number (None clears it); any change takes the confirmation back."""
    entries = load()
    if connections is None:
        entries['tiles'].pop(tile_id, None)
    else:
        entries['tiles'][tile_id] = {FIELD: connections}
    entries['confirmed'] = False
    save(entries)
    return entries


def set_confirmed(confirmed):
    entries = load()
    entries['confirmed'] = bool(confirmed)
    save(entries)
    return entries


def check(value):
    """Problems with one tile's number."""
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= LIMIT:
        return [f'{value!r} is not a whole number from 0 to {LIMIT}']
    return []


def outline_tabs(alpha, width, height, px):
    """The tabs on a side's outline: alpha (a PIL "L" image) of the side at px per square, its grid width x height
    squares inside tab margins (a quarter square on an axis with tabs). A tab is the outline reaching into the margin
    beside a square's edge, at the middle of that edge."""
    margin_x = (alpha.width - width * px) // 2
    margin_y = (alpha.height - height * px) // 2
    tabs = 0
    for i in range(width):
        x = margin_x + i * px + px // 2
        if margin_y:
            tabs += alpha.getpixel((x, margin_y // 2)) > 127
            tabs += alpha.getpixel((x, alpha.height - 1 - margin_y // 2)) > 127
    for j in range(height):
        y = margin_y + j * px + px // 2
        if margin_x:
            tabs += alpha.getpixel((margin_x // 2, y)) > 127
            tabs += alpha.getpixel((alpha.width - 1 - margin_x // 2, y)) > 127
    return tabs


def counted(dataset, tile):
    """outline_tabs of a tile's side A small image (64 px per square), or None without the image."""
    from PIL import Image

    path = dataset.root / 'images' / 'small' / tile['side_a']
    if not path.is_file():
        return None
    with Image.open(path) as image:
        alpha = image.convert('RGBA').getchannel('A')
    return outline_tabs(alpha, tile['width'], tile['height'], 64)


def panel(dataset):
    """What the Tile connections page shows: the tiles in file order, the entries, and the outline counts (for the
    confirmation step only)."""
    tiles = [{'id': t['id'], 'name': t['name'], 'product': t['name'].rsplit(' ', 1)[0], 'squares': t['squares'],
              'side_a': t['side_a'], 'side_b': t['side_b'], 'current': t.get(FIELD)}
             for t in dataset.records('map-tiles')]
    outline = {t['id']: counted(dataset, t) for t in dataset.records('map-tiles')}
    return {'tiles': tiles, 'entries': load(), 'outline': outline, 'limit': LIMIT}


def with_connections(record, connections):
    """The record with `connections` set: in place where it has one, after `height` otherwise."""
    if FIELD in record:
        return record | {FIELD: connections}
    out = {}
    for key, value in record.items():
        out[key] = value
        if key == AFTER:
            out[FIELD] = connections
    return out if FIELD in out else out | {FIELD: connections}


def plan(dataset, entries=None):
    """(map-tiles records after writing, summary, problems)."""
    entries = entries or load()
    tiles = dataset.records('map-tiles')
    known = {t['id'] for t in tiles}
    problems = [f'{tile_id}: not a map tile' for tile_id in entries['tiles'] if tile_id not in known]
    records, left = [], []
    for tile in tiles:
        entry = entries['tiles'].get(tile['id'])
        if entry is None:
            left.append(tile['name'])
            records.append(tile)
            continue
        problems += [f"{tile['name']}: {p}" for p in check(entry.get(FIELD))]
        records.append(with_connections(tile, entry.get(FIELD)))
    if left:
        problems.append(f"{len(left)} tiles have no number yet ({', '.join(left[:5])}{', …' if len(left) > 5 else ''})")
    elif not entries.get('confirmed'):
        problems.append('the numbers are not confirmed yet (the page\'s last step)')
    summary = {'tiles': len(tiles), 'entered': len(tiles) - len(left), 'left': len(left),
               'confirmed': bool(entries.get('confirmed'))}
    return records, summary, problems


def run(dataset, check_only=False):
    """(summary, problems); writes map-tiles.json unless checking or there are problems."""
    records, summary, problems = plan(dataset)
    if not problems and not check_only:
        dataset.path('map-tiles').write_text(dumps(records), encoding='utf-8')
    return summary, problems
