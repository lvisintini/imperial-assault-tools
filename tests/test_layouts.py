import json

from ia_tools import layouts
from ia_tools.staging import Staging


def test_rows_sort_by_mission_product_map_name_then_tiles_newest_product_first(dataset_copy):
    dataset = dataset_copy
    codes = layouts.product_codes(dataset)
    by_name = {s['name']: s['id'] for s in dataset.records('sources')}
    assert codes[by_name['Imperial Assault']] == ('SWI01', 0)
    assert codes[by_name['Luke Skywalker']] == ('SWI01', 1)  # no code: right after the Core Set
    rows = layouts.sort_rows(dataset, dataset.records('map-layouts'))
    assert sorted(map(json.dumps, rows)) == sorted(map(json.dumps, dataset.records('map-layouts')))
    names = {m['id']: m['name'] for m in dataset.records('maps')}
    order = list(dict.fromkeys(names[r['map_id']] for r in rows))
    assert order.index('Moisture Farm') > order.index('Aftermath')  # a Luke pack map after the Core Set's
    assert order.index('Imperial Command Hub') < order.index('Echo Base')  # SWI17 before SWI19, though released later
    tiles = {t['id']: t for t in dataset.records('map-tiles')}
    own = [(tiles[r['tile_id']]['name'], r['side']) for r in rows if names[r['map_id']] == 'Into a Corner']
    assert own[0][0].startswith('Heart of the Empire') and own[-1][0].startswith('Core Set') and own == sorted(
        own, key=lambda t: (not t[0].startswith('Heart'), t))


def tile_ids(dataset, n=2):
    return [t['id'] for t in dataset.records('map-tiles')[:n]]


def test_rows_move_the_frame_to_0_0_and_sort_placements_by_section_then_y_then_x(dataset_copy):
    one, two = tile_ids(dataset_copy)
    placed = [{'tile_id': one, 'side': 'A', 'section': 'Cave', 'x': 12, 'y': 7, 'rotation': 90},
              {'tile_id': one, 'side': 'A', 'section': None, 'x': 15, 'y': 9, 'rotation': 0},
              {'tile_id': one, 'side': 'A', 'section': None, 'x': 11, 'y': 9, 'rotation': 180},
              {'tile_id': two, 'side': 'B', 'section': None, 'x': 10, 'y': 8, 'rotation': 270}]
    rows, problems = layouts.rows_for(dataset_copy, 'm', {(one, 'A'): 2, (two, 'B'): 1}, placed, ['Cave'])
    assert problems == []
    assert [list(r) for r in rows] == [['map_id', 'tile_id', 'side', 'count', 'placements']] * 2
    assert rows[0]['placements'] == [{'section': None, 'x': 1, 'y': 2, 'rotation': 180},
                                     {'section': None, 'x': 5, 'y': 2, 'rotation': 0},
                                     {'section': 'Cave', 'x': 2, 'y': 0, 'rotation': 90}]
    assert rows[1]['placements'] == [{'section': None, 'x': 0, 'y': 1, 'rotation': 270}]


def test_a_recycled_tile_is_placed_more_often_than_its_copies_but_never_more_on_one_image(dataset_copy):
    (one,) = tile_ids(dataset_copy, 1)
    at = {'tile_id': one, 'side': 'A', 'rotation': 0, 'y': 0}
    recycled = [at | {'section': None, 'x': 0}, at | {'section': 'Cave', 'x': 0}, at | {'section': 'Cave', 'x': 2}]
    name = dataset_copy.records('map-tiles')[0]['name']
    assert layouts.rows_for(dataset_copy, 'm', {(one, 'A'): 2}, recycled, ['Cave'])[1] == []
    assert layouts.rows_for(dataset_copy, 'm', {(one, 'A'): 1}, recycled, ['Cave'])[1] == [
        f'{name}A: 1 copies, but Cave places it 2 times']
    assert layouts.rows_for(dataset_copy, 'm', {(one, 'A'): 4}, recycled, ['Cave'])[1] == [
        f'{name}A: 4 copies, but placed 3 times']
    problems = layouts.rows_for(dataset_copy, 'm', {}, recycled[:1] + [at | {'section': 'Attic', 'x': 0}])[1]
    assert problems == ["a placement in 'Attic', which isn't one of the map's sections",
                        f'{name}A: placed but not in the layout']


def test_staged_products_leave_out_other_manifests(tmp_path):
    (tmp_path / 'map-tiles').mkdir()
    (tmp_path / 'map-tiles' / 'manifest.json').write_text('{"tiles": []}', encoding='utf-8')
    (tmp_path / 'a-product').mkdir()
    (tmp_path / 'a-product' / 'manifest.json').write_text('{"product": "A", "items": []}', encoding='utf-8')
    assert [s.slug for s in Staging.all(tmp_path)] == ['a-product']
