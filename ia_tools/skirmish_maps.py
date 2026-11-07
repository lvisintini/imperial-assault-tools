"""ia skirmish-maps: the skirmish, four-player and raid maps' map-layouts rows, from their reviewed tile placements
(data 2.0.0).

No source has these maps' placements. They were found by matching the maps' tile sides against the Vassal skirmish
module's boards (vassal-2/, 50 px per square) and our Skirmish Map Project images, then reviewed map by map by the
maintainer (2026-11-06/07). The prototype and its review are in staging/skirmish-maps/: scripts/, rulings.json, and
final.json, which this reads:

    [{"map", "map_id", "placements": [{"tile_id", "side", "turn", "x", "y"}, ...]}, ...]

x, y: the top-left square of the tile's turned grid; turn: the quarter turns counter-clockwise (numpy's rot90) of the
side's stored image. A map's rows: one per tile side, count = its placements (these maps have no hidden sections),
rotation = (-90 * turn) mod 360 clockwise, the frame moved to start at 0, 0 (layouts.rows_for). The images aren't
touched: the maps keep the Skirmish Map Project's."""
import json
from collections import Counter

from ia_tools import settings

TYPES = ('skirmish-missions', 'raid-missions')


def final_path():
    return settings.STAGING / 'skirmish-maps' / 'final.json'


def rotation_of(turn):
    """Clockwise degrees for numpy's counter-clockwise quarter turns."""
    return (-90 * turn) % 360


def skirmish_maps(dataset):
    """{map id: name} of the skirmish and raid missions' maps."""
    names = {m['id']: m['name'] for m in dataset.records('maps')}
    return {m['map_id']: names[m['map_id']] for m in dataset.records('missions')
            if m['content_type'] in TYPES and m['map_id']}


def plan(dataset, final):
    """(rows, problems): the whole map-layouts file with the skirmish and raid maps' rows from final."""
    from ia_tools.layouts import rows_for, sort_rows

    wanted = skirmish_maps(dataset)
    given = {m['map_id']: m for m in final}
    problems = [f'{name}: no placements' for map_id, name in wanted.items() if map_id not in given]
    problems += [f"{m['map']}: not a skirmish or raid map" for m in final if m['map_id'] not in wanted]
    rows = [r for r in dataset.records('map-layouts') if r['map_id'] not in given]
    for map_id, entry in given.items():
        if map_id not in wanted:
            continue
        placed = [{'tile_id': p['tile_id'], 'side': p['side'], 'section': None, 'x': p['x'], 'y': p['y'],
                   'rotation': rotation_of(p['turn'])} for p in entry['placements']]
        bad = [p for p in entry['placements'] if not (isinstance(p['x'], int) and isinstance(p['y'], int))]
        problems += [f"{entry['map']}: {p['tile_id']}{p['side']} isn't on whole squares" for p in bad]
        counts = Counter((p['tile_id'], p['side']) for p in placed)
        new, trouble = rows_for(dataset, map_id, dict(counts), placed)
        problems += [f"{entry['map']}: {t}" for t in trouble]
        rows += new
    return sort_rows(dataset, rows), problems


def run(dataset, write=False, path=None):
    """(summary, problems); writes map-layouts.json when asked and there are no problems."""
    from ia_tools.dataset import dumps

    final = json.loads((path or final_path()).read_text(encoding='utf-8'))
    rows, problems = plan(dataset, final)
    wanted = skirmish_maps(dataset)
    own = [r for r in rows if r['map_id'] in wanted]
    summary = {'maps': len({r['map_id'] for r in own}), 'rows': len(own),
               'placements': sum(len(r.get('placements', [])) for r in own)}
    if write and not problems:
        dataset.path('map-layouts').write_text(dumps(rows), encoding='utf-8')
    return summary, problems
