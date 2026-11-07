"""map-layouts.json (data 2.0.0): its rows' order, and building a map's rows from where its tiles are placed.

A row is one tile side a map uses: {"map_id", "tile_id", "side", "count", "placements"}. count is the copies the
mission takes; placements are where its images put them: [{"section", "x", "y", "rotation"}], section null for the
map's image or a hidden section's name, x and y the top-left square of the tile's turned grid (a map's frame starts at
0, 0, its hidden sections in the same frame), rotation the clockwise degrees that turn the side's stored image.

A tile a hidden section reuses (recycles) is placed more often than count; no one image places it more than count
times, and every copy is placed somewhere. ia maps writes the campaign maps' rows, ia skirmish-maps the skirmish and
raid maps'."""
from collections import Counter


def products_of(dataset, content_type):
    """{record id: [source names]} through source-contents."""
    names = {s['id']: s['name'] for s in dataset.records('sources')}
    found = {}
    for row in dataset.records('source-contents'):
        if row['content_type'] == content_type:
            found.setdefault(row['content_id'], []).append(names[row['source_id']])
    return found


def product_codes(dataset):
    """{source id: (product code, 0)}, or (the code before it, 1) for a product without one: the last coded product
    released on or before it (the Luke and Vader packs follow the Core Set), so it sorts right after that one."""
    sources = dataset.records('sources')
    coded = sorted((s['release_date'] or '9999', s['product_code']) for s in sources if s['product_code'])
    codes = {}
    for source in sources:
        if source['product_code']:
            codes[source['id']] = (source['product_code'], 0)
        else:
            before = [code for date, code in coded if date <= (source['release_date'] or '9999')]
            codes[source['id']] = (before[-1] if before else '', 1)
    return codes


def row_order(dataset, maps=None):
    """A sort key for map-layouts rows, the order map-layouts.json keeps: by the map's mission product (the earliest
    product code of its missions' products, see product_codes), the map's name, then the tile's product code
    descending, its number and the side. maps: the map records to name maps by (default: the dataset's)."""
    codes = product_codes(dataset)
    found = {}
    for row in dataset.records('source-contents'):
        found.setdefault((row['content_type'], row['content_id']), []).append(codes[row['source_id']])
    first = {}
    for mission in dataset.records('missions'):
        own = found.get(('missions', mission['id']), [])
        if mission['map_id'] and own:
            first[mission['map_id']] = min(own + [first.get(mission['map_id'], min(own))])
    names = {m['id']: m['name'].casefold() for m in (maps or dataset.records('maps'))}
    tile_codes = {t['id']: min(code for code, _ in found.get(('map-tiles', t['id']), [('~', 0)]))
                  for t in dataset.records('map-tiles')}
    rank = {code: i for i, code in enumerate(sorted(set(tile_codes.values()), reverse=True))}
    numbers = {t['id']: t['number'] for t in dataset.records('map-tiles')}

    def key(row):
        return (first.get(row['map_id'], ('~', 2)), names.get(row['map_id'], ''),
                rank.get(tile_codes.get(row['tile_id']), len(rank)), numbers.get(row['tile_id'], 0), row['side'])
    return key


def sort_rows(dataset, rows, maps=None):
    """map-layouts rows in the file's order (row_order)."""
    return sorted(rows, key=row_order(dataset, maps))


def rows_for(dataset, map_id, counts, placed, sections=()):
    """(rows, problems): a map's rows. counts: {(tile id, side): copies}; placed: [{"tile_id", "side", "section", "x",
    "y", "rotation"}] in any frame; sections: the map's hidden sections' names, in order."""
    names = {t['id']: t['name'] for t in dataset.records('map-tiles')}
    order = {None: 0} | {name: i + 1 for i, name in enumerate(sections)}
    problems = [f"a placement in {p['section']!r}, which isn't one of the map's sections" for p in placed
                if p['section'] not in order]
    x0 = min((p['x'] for p in placed), default=0)
    y0 = min((p['y'] for p in placed), default=0)
    by = {}
    for p in placed:
        by.setdefault((p['tile_id'], p['side']), []).append(
            {'section': p['section'], 'x': p['x'] - x0, 'y': p['y'] - y0, 'rotation': p['rotation']})
    problems += [f'{names.get(t, t)}{s}: placed but not in the layout' for t, s in by if (t, s) not in counts]
    rows = []
    for (tile_id, side), count in counts.items():
        label = f'{names.get(tile_id, tile_id)}{side}'
        own = sorted(by.get((tile_id, side), []), key=lambda p: (order.get(p['section'], len(order)), p['y'], p['x']))
        if len(own) < count:
            problems.append(f'{label}: {count} copies, but placed {len(own)} times')
        for section, n in Counter(p['section'] for p in own).items():
            if n > count:
                problems.append(f"{label}: {count} copies, but {section or 'the map'} places it {n} times")
        rows.append({'map_id': map_id, 'tile_id': tile_id, 'side': side, 'count': count, 'placements': own})
    return rows, problems
