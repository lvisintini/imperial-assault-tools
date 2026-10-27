import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from ia_tools import layouts, settings
from ia_tools.enter import server
from ia_tools.staging import Staging
from tests.test_enter import call


@pytest.fixture
def dataset(dataset_copy, tmp_path, monkeypatch):
    if not dataset_copy.path('map-tiles').exists():
        pytest.skip('The checkout has no map tiles (data 2.0.0)')
    monkeypatch.setattr(settings, 'STAGING', tmp_path / 'staging')
    return dataset_copy


def skirmish_map(dataset):
    return next(m for m in layouts.maps(dataset) if not m['rows'])


def single_tile(dataset):
    return next(t for t in layouts.tiles(dataset) if t['copies'] == 1)


def test_the_maps_entered_are_the_skirmish_and_raid_maps(dataset):
    entered = {m['id'] for m in layouts.maps(dataset)}
    missions = {m['map_id']: m['content_type'] for m in dataset.records('missions') if m['map_id']}
    with_rows = {r['map_id'] for r in dataset.records('map-layouts')}
    assert entered == {m['id'] for m in dataset.records('maps')
                       if missions.get(m['id']) in layouts.ENTRY_TYPES or m['id'] not in with_rows}
    assert all(m['missions'] and m['products'] for m in layouts.maps(dataset))


def test_tiles_have_their_products_codes_and_copies(dataset):
    tiles = layouts.tiles(dataset)
    assert len(tiles) == len(dataset.records('map-tiles'))
    assert all(t['product'] in layouts.CODES for t in tiles)
    assert sum(t['copies'] for t in tiles) == sum(r['quantity'] for r in dataset.records('source-contents')
                                                  if r['content_type'] == 'map-tiles')
    core = next(t for t in tiles if t['name'] == 'Core Set 01')
    assert (core['product'], core['code'], core['number']) == ('Imperial Assault', '', 1)


def test_check_map(dataset):
    tile = single_tile(dataset)
    row = {'tile_id': tile['id'], 'side': 'A', 'count': 1}
    assert layouts.check_map({'tiles': [row], 'done': True}, dataset) == []
    problems = layouts.check_map({'tiles': [
        {'tile_id': 'nope', 'side': 'A', 'count': 1},
        {'tile_id': tile['id'], 'side': 'C', 'count': 1},
        {'tile_id': tile['id'], 'side': 'A', 'count': 0},
        row, row,
    ]}, dataset)
    assert len(problems) == 5
    assert "Unknown tile 'nope'" in problems and f"{tile['name']}A is listed twice" in problems
    assert any("isn't A or B" in p for p in problems) and any('whole number' in p for p in problems)
    assert f"{tile['name']}: 3 used, but the products have 1" in problems  # sides C, A and A: one copy
    assert layouts.check_map({'tiles': [], 'done': True}, dataset) == ['Marked done with no tiles']


def test_run_writes_the_maps_marked_done(dataset):
    first, second = layouts.maps(dataset)[:2]
    tile = single_tile(dataset)
    before = list(dataset.records('map-layouts'))
    layouts.save({'maps': {
        first['id']: {'tiles': [{'tile_id': tile['id'], 'side': 'B', 'count': 1}], 'done': True, 'note': ''},
        second['id']: {'tiles': [{'tile_id': tile['id'], 'side': 'A', 'count': 1}], 'done': False, 'note': ''},
    }})
    summary, problems = layouts.run(dataset, check=True)
    assert problems == [] and (summary['done'], summary['rows']) == (1, 1)
    assert json.loads(dataset.path('map-layouts').read_text(encoding='utf-8')) == before  # --check writes nothing

    layouts.run(dataset)
    written = json.loads(dataset.path('map-layouts').read_text(encoding='utf-8'))
    assert written == before + [{'map_id': first['id'], 'tile_id': tile['id'], 'side': 'B', 'count': 1}]

    # Run again after a correction: the map's rows are replaced, not added to.
    entries = layouts.load()
    entries['maps'][first['id']]['tiles'][0]['side'] = 'A'
    layouts.save(entries)
    dataset._data.pop('map-layouts')
    assert layouts.run(dataset)[0]['replacing'] == 1
    written = json.loads(dataset.path('map-layouts').read_text(encoding='utf-8'))
    assert written == before + [{'map_id': first['id'], 'tile_id': tile['id'], 'side': 'A', 'count': 1}]


def test_run_writes_nothing_with_problems(dataset):
    before = dataset.path('map-layouts').read_text(encoding='utf-8')
    campaign = next(r['map_id'] for r in dataset.records('map-layouts'))
    layouts.save({'maps': {skirmish_map(dataset)['id']: {'tiles': [], 'done': True},
                           campaign: {'tiles': [], 'done': False}}})
    _, problems = layouts.run(dataset)
    assert len(problems) == 2 and any('not a map entered here' in p for p in problems)
    assert dataset.path('map-layouts').read_text(encoding='utf-8') == before


def test_server_saves_layouts(dataset):
    server.Handler.dataset = dataset
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    try:
        map_id, tile = skirmish_map(dataset)['id'], single_tile(dataset)
        entry = {'tiles': [{'tile_id': tile['id'], 'side': 'A', 'count': 2}], 'done': False, 'note': ''}
        saved = json.loads(call('PUT', f'{base}/api/layouts/{map_id}', entry)[2])
        assert saved == {'saved': True, 'problems': [f"{tile['name']}: 2 used, but the products have 1"]}
        assert layouts.load() == {'maps': {map_id: entry}}

        panel = json.loads(call('GET', f'{base}/api/layouts')[2])
        assert panel['entries'] == {map_id: entry} and panel['problems'][map_id] == saved['problems']
        assert {'maps', 'tiles', 'products', 'codes'} <= set(panel)
        assert call('GET', f'{base}/layouts')[1].startswith('text/html')
    finally:
        httpd.shutdown()


def test_staged_products_leave_out_other_manifests(tmp_path):
    (tmp_path / 'map-tiles').mkdir()
    (tmp_path / 'map-tiles' / 'manifest.json').write_text('{"tiles": []}', encoding='utf-8')
    (tmp_path / 'a-product').mkdir()
    (tmp_path / 'a-product' / 'manifest.json').write_text('{"product": "A", "items": []}', encoding='utf-8')
    assert [s.slug for s in Staging.all(tmp_path)] == ['a-product']
