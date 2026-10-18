import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from ia_tools import settings
from ia_tools.enter import api, server
from tests.test_importer import CARD, HERO, stage


def fields_by_name(forms, content_type):
    return {f['name']: f for f in forms[content_type]['fields']}


def test_forms_follow_the_schemas(real_dataset):
    forms = api.forms(real_dataset)
    deployment = fields_by_name(forms, 'deployment-cards')
    assert 'id' not in deployment and 'image' not in deployment
    assert deployment['affiliation']['kind'] == 'select' and 'Rebel' in deployment['affiliation']['options']
    assert deployment['traits']['kind'] == 'multi'
    assert (deployment['health']['kind'], deployment['health']['nullable']) == ('integer', True)
    assert deployment['elite']['kind'] == 'boolean'
    assert fields_by_name(forms, 'hero-class-cards')['hero_id'] | {'kind': 'fk', 'parent': 'heroes'} == \
        fields_by_name(forms, 'hero-class-cards')['hero_id']
    assert forms['heroes']['images'] == ['healthy', 'wounded']


def item(key, content_type, name, path=(), hints=None, matches=(), back=None):
    return {'key': key, 'name': name, 'path': list(path), 'matches': list(matches),
            'guess': {'content_type': content_type, 'back_content_type': back, 'hints': hints or {}}}


def test_suggestions(real_dataset):
    hero = real_dataset.records('heroes')[0]
    healthy = item('0001', 'heroes', 'Test Hero Healthy', path=('X', 'Rebel Heroes', 'Test Hero'))
    wounded = item('0002', 'heroes', 'Test Hero Wounded', path=('X', 'Rebel Heroes', 'Test Hero'))
    known = item('0003', 'command-cards', 'Known', matches=[{'content_type': 'command-cards', 'id': 5, 'name': 'Known'}])
    feat = item('0004', 'hero-class-cards', 'Feat', hints={'hero': hero['name']})
    back = item('0005', 'card-backs', 'back', back='heroes')
    unit = item('0006', 'deployment-cards', 'Unit', hints={'affiliation': 'Mercenaries'})
    manifest = {'items': [healthy, wounded, known, feat, back, unit]}
    entries = {'items': {}, 'extra': {}}

    def suggest(i):
        return api.suggest(i, manifest, real_dataset, entries)

    assert suggest(healthy) == {'action': 'new', 'content_type': 'heroes', 'record': {'name': 'Test Hero'}}
    assert suggest(wounded) == {'action': 'attach', 'to': '0001', 'field': 'wounded'}
    assert suggest(known) == {'action': 'link', 'content_type': 'command-cards', 'id': 5}
    assert suggest(feat)['record']['hero_id'] == hero['id']
    assert suggest(back)['record']['deck'] == 'Rebel Hero'
    assert suggest(unit)['record']['affiliation'] == 'Mercenary'
    assert suggest(unit)['record']['iaspec'] == 'unit'


def test_check_entry(real_dataset):
    good = {'action': 'new', 'content_type': 'agenda-decks', 'record': {'name': 'Deck'}}
    assert api.check_entry(good, real_dataset) == []
    bad = {'action': 'new', 'content_type': 'command-cards', 'record': {'name': 'X', 'cost': 'one'}}
    assert any('cost' in p for p in api.check_entry(bad, real_dataset))
    assert api.check_entry({'action': 'skip'}, real_dataset) == []


@pytest.fixture
def running_server(tmp_path, dataset_copy, monkeypatch):
    staging = stage(tmp_path, {'0000': CARD, '0001': HERO}, {'product': None, 'items': {}, 'extra': {}})
    monkeypatch.setattr(settings, 'STAGING', staging.dir.parent)
    server.Handler.dataset = dataset_copy
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_port}', staging
    httpd.shutdown()


def call(method, url, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request) as response:
        return response.status, response.headers.get('Content-Type'), response.read()


def test_server_round_trip(running_server):
    base, staging = running_server
    status, _, body = call('GET', f'{base}/api/products')
    assert json.loads(body) == [{'slug': 'test-product', 'product': 'Test Product', 'items': 2, 'decided': 0}]

    product = json.loads(call('GET', f'{base}/api/products/test-product')[2])
    assert set(product) >= {'manifest', 'entries', 'suggestions', 'forms', 'records', 'references'}

    entry = {'action': 'new', 'content_type': 'command-cards', 'record': {'name': 'X', 'cost': 'one'}}
    saved = json.loads(call('PUT', f'{base}/api/products/test-product/items/0000', entry)[2])
    assert saved['saved'] and saved['problems']  # saved as a draft even with problems
    assert staging.entries()['items']['0000'] == entry

    status, content_type, png = call('GET', f'{base}/preview/test-product/0000?type=command-cards')
    assert content_type == 'image/png' and png.startswith(b'\x89PNG')
    assert call('GET', f'{base}/originals/test-product/originals/0000.png')[2].startswith(b'\x89PNG')

    check = json.loads(call('POST', f'{base}/api/products/test-product/check')[2])
    assert check['ok'] is False and any('No product chosen' in p for p in check['problems'])

    assert call('GET', f'{base}/')[1].startswith('text/html')


def test_server_refuses_paths_outside_its_folders(running_server):
    base, _ = running_server
    with pytest.raises(urllib.error.HTTPError) as raised:
        call('GET', f'{base}/originals/test-product/..%2F..%2Fseen.txt')
    assert raised.value.code in (403, 404)
