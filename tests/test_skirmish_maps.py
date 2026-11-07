import json

from ia_tools import skirmish_maps


def final_for(dataset):
    """A final.json for every skirmish and raid map, placing each of its tile sides' copies in a row, turned once."""
    wanted = skirmish_maps.skirmish_maps(dataset)
    final = {}
    for row in dataset.records('map-layouts'):
        if row['map_id'] in wanted:
            entry = final.setdefault(row['map_id'], {'map': wanted[row['map_id']], 'map_id': row['map_id'],
                                                     'placements': []})
            for _ in range(row['count']):
                n = len(entry['placements'])
                entry['placements'].append({'tile_id': row['tile_id'], 'side': row['side'], 'turn': 1,
                                            'x': 20 + 4 * n, 'y': 9})
    return list(final.values())


def test_turns_are_counter_clockwise_and_rotations_clockwise():
    assert [skirmish_maps.rotation_of(k) for k in range(4)] == [0, 270, 180, 90]


def test_rows_count_each_sides_placements_from_0_0(dataset_copy, tmp_path):
    final = final_for(dataset_copy)
    path = tmp_path / 'final.json'
    path.write_text(json.dumps(final), encoding='utf-8')
    before = [r for r in dataset_copy.records('map-layouts') if r['map_id'] not in {m['map_id'] for m in final}]
    summary, problems = skirmish_maps.run(dataset_copy, write=True, path=path)
    assert problems == [] and summary['maps'] == len(final)
    rows = json.loads(dataset_copy.path('map-layouts').read_text(encoding='utf-8'))
    assert [r for r in rows if r['map_id'] not in {m['map_id'] for m in final}] == before  # the others untouched
    own = [r for r in rows if r['map_id'] == final[0]['map_id']]
    assert sum(r['count'] for r in own) == len(final[0]['placements'])
    assert all(len(r['placements']) == r['count'] for r in own)
    spots = [p for r in own for p in r['placements']]
    assert min(p['x'] for p in spots) == 0 and {p['y'] for p in spots} == {0}
    assert {(p['section'], p['rotation']) for p in spots} == {(None, 270)}


def test_every_skirmish_map_needs_placements(dataset_copy, tmp_path):
    final = final_for(dataset_copy)
    path = tmp_path / 'final.json'
    path.write_text(json.dumps(final[1:]), encoding='utf-8')
    before = dataset_copy.path('map-layouts').read_text(encoding='utf-8')
    _, problems = skirmish_maps.run(dataset_copy, write=True, path=path)
    assert problems == [f"{final[0]['map']}: no placements"]
    assert dataset_copy.path('map-layouts').read_text(encoding='utf-8') == before
