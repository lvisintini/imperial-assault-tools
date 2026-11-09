import json

import numpy as np
from PIL import Image

from ia_tools import skirmish_maps


def fake_tiles(dataset):
    """Generated opaque side images (never the dataset's) for every tile, width x height squares, no tabs."""
    for tile in dataset.records('map-tiles'):
        for field, colour in (('side_a', (200, 0, 0, 255)), ('side_b', (0, 0, 200, 255))):
            for size in ('large', 'small'):
                path = dataset.root / 'images' / size / tile[field]
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new('RGBA', (tile['width'] * 64, tile['height'] * 64), colour).save(path)


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
    fake_tiles(dataset_copy)
    summary, problems = skirmish_maps.run(dataset_copy, write=True, path=path, log=lambda *_: None)
    assert problems == [] and summary['maps'] == len(final) and summary['images'] == len(final)
    rows = json.loads(dataset_copy.path('map-layouts').read_text(encoding='utf-8'))
    assert [r for r in rows if r['map_id'] not in {m['map_id'] for m in final}] == before  # the others untouched
    own = [r for r in rows if r['map_id'] == final[0]['map_id']]
    assert sum(r['count'] for r in own) == len(final[0]['placements'])
    assert all(len(r['placements']) == r['count'] for r in own)
    spots = [p for r in own for p in r['placements']]
    assert min(p['x'] for p in spots) == 0 and {p['y'] for p in spots} == {0}
    assert {(p['section'], p['rotation']) for p in spots} == {(None, 270)}
    image = next(m['image'] for m in dataset_copy.records('maps') if m['id'] == final[0]['map_id'])
    for size in ('large', 'small'):
        with Image.open(dataset_copy.root / 'images' / size / image) as drawn:
            assert drawn.height == max(p['y'] for p in spots) * 64 + 32 + 64 * max(
                t['width'] for t in dataset_copy.records('map-tiles')
                if t['id'] in {r['tile_id'] for r in own})  # turned: a tile's width is its height


def test_a_map_is_drawn_from_its_rows_on_the_squares_frame(dataset_copy):
    tile = dataset_copy.records('map-tiles')[0]
    side = np.zeros((64, 160, 4), dtype=np.uint8)  # 2 x 1 squares, tabs across
    side[:, 16:144] = (10, 20, 30, 255)
    side[20:40, :16] = (99, 99, 99, 255)  # a tab on its left
    for size in ('large', 'small'):
        path = dataset_copy.root / 'images' / size / tile['side_a']
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(side).save(path)
    rows = [{'map_id': 'm', 'tile_id': tile['id'], 'side': 'A', 'count': 2,
             'placements': [{'section': None, 'x': 0, 'y': 0, 'rotation': 0},
                            {'section': None, 'x': 2, 'y': 1, 'rotation': 90}]}]
    image = np.array(skirmish_maps.draw(dataset_copy, rows))
    # Squares 0-2 across and 0-2 down (the second turned: 1 x 2 at 2, 1), and 16 px all round.
    assert image.shape == (3 * 64 + 32, 3 * 64 + 32, 4)
    assert tuple(image[16 + 32, 16 + 32]) == (10, 20, 30, 255) and tuple(image[16 + 32, 8]) == (99, 99, 99, 255)
    assert image[16 + 96, 16 + 160, 3] == 255 and image[16 + 96, 16 + 32, 3] == 0


def test_every_skirmish_map_needs_placements(dataset_copy, tmp_path):
    final = final_for(dataset_copy)
    path = tmp_path / 'final.json'
    path.write_text(json.dumps(final[1:]), encoding='utf-8')
    before = dataset_copy.path('map-layouts').read_text(encoding='utf-8')
    _, problems = skirmish_maps.run(dataset_copy, write=True, path=path)
    assert problems == [f"{final[0]['map']}: no placements"]
    assert dataset_copy.path('map-layouts').read_text(encoding='utf-8') == before
