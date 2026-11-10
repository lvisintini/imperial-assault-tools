import json
import threading
from http.server import ThreadingHTTPServer

import pytest
from PIL import Image, ImageDraw

from ia_tools import settings, tile_connections as tc
from ia_tools.enter import server
from tests.test_enter import call


@pytest.fixture
def dataset(dataset_copy, tmp_path, monkeypatch):
    if not dataset_copy.path('map-tile-matches').exists():
        pytest.skip('The checkout predates the map tiles of data 2.0.0')
    monkeypatch.setattr(settings, 'STAGING', tmp_path / 'staging')
    return dataset_copy


def test_a_number_is_one_key():
    assert tc.check(0) == [] and tc.check(9) == []
    assert tc.check(10) and tc.check(-1) and tc.check('3') and tc.check(True) and tc.check(2.5)


def test_tabs_are_counted_on_the_outline():
    """A generated 2 x 1 side at 64 px per square (never a dataset image): tab margins of 16 px on both axes, a tab
    beside the left square's top edge and one beside the right edge."""
    image = Image.new('L', (2 * 64 + 32, 64 + 32), 0)
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 16 + 128 - 1, 16 + 64 - 1), fill=255)
    draw.rectangle((16 + 24, 0, 16 + 40, 16), fill=255)            # top, left square
    draw.rectangle((16 + 128, 16 + 24, 16 + 128 + 15, 16 + 40), fill=255)  # right
    assert tc.outline_tabs(image, 2, 1, 64) == 2


def test_connections_go_after_height():
    record = {'id': 'x', 'name': 'Core Set 01', 'squares': 4, 'width': 2, 'height': 2, 'side_a': 'a', 'side_b': 'b'}
    assert list(tc.with_connections(record, 3)) == ['id', 'name', 'squares', 'width', 'height', 'connections',
                                                    'side_a', 'side_b']
    assert tc.with_connections(tc.with_connections(record, 3), 4)['connections'] == 4


def test_run_writes_once_every_tile_is_entered_and_confirmed(dataset):
    tiles = dataset.records('map-tiles')
    for n, tile in enumerate(tiles[:-1]):
        tc.set_tile(tile['id'], n % 5 + 1)
    summary, problems = tc.run(dataset)
    assert summary['left'] == 1 and len(problems) == 1 and 'no number yet' in problems[0]

    tc.set_tile(tiles[-1]['id'], 2)
    summary, problems = tc.run(dataset)
    assert problems == ['the numbers are not confirmed yet (the page\'s last step)']

    tc.set_confirmed(True)
    assert tc.run(dataset, check_only=True)[1] == []
    assert json.loads(dataset.path('map-tiles').read_text(encoding='utf-8')) == tiles  # --check writes nothing
    summary, problems = tc.run(dataset)
    assert problems == [] and summary == {'tiles': len(tiles), 'entered': len(tiles), 'left': 0, 'confirmed': True}
    written = json.loads(dataset.path('map-tiles').read_text(encoding='utf-8'))
    assert [r['connections'] for r in written] == [n % 5 + 1 for n in range(len(tiles) - 1)] + [2]
    without = lambda rows: [{k: v for k, v in r.items() if k != 'connections'} for r in rows]
    assert without(written) == without(tiles)  # only connections changes (the data may have them already)

    tc.set_tile(tiles[0]['id'], 4)  # a later change takes the confirmation back
    assert tc.load()['confirmed'] is False


def test_server_saves_entries(dataset):
    server.Handler.dataset = dataset
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    try:
        tile = dataset.records('map-tiles')[0]
        assert json.loads(call('PUT', f'{base}/api/tile-connections/{tile["id"]}', {'connections': 3})[2])['saved']
        assert json.loads(call('PUT', f'{base}/api/tile-connections/confirmed', True)[2])['confirmed'] is True
        panel = json.loads(call('GET', f'{base}/api/tile-connections')[2])
        assert panel['entries'] == {'tiles': {tile['id']: {'connections': 3}}, 'confirmed': True}
        assert [t['id'] for t in panel['tiles']] == [t['id'] for t in dataset.records('map-tiles')]
        assert panel['outline'][tile['id']] is None  # the copy has no images
        call('PUT', f'{base}/api/tile-connections/{tile["id"]}', {'connections': None})
        assert tc.load() == {'tiles': {}, 'confirmed': False}
        with pytest.raises(Exception, match='400'):
            call('PUT', f'{base}/api/tile-connections/{tile["id"]}', {'connections': 12})
        assert call('GET', f'{base}/tile-connections')[1].startswith('text/html')
    finally:
        httpd.shutdown()
