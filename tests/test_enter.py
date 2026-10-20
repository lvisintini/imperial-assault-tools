import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from ia_tools import iaspec, settings
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
    back = item('0005', 'card-backs', 'back', back='heroes', hints={'hero': hero['name'].upper()})
    class_back = item('0007', 'card-backs', 'back', back='imperial-classes', hints={'class': 'New Class'})
    unit = item('0006', 'deployment-cards', 'Unit', hints={'affiliation': 'Mercenaries'})
    manifest = {'items': [healthy, wounded, known, feat, back, unit, class_back]}
    entries = {'items': {}, 'extra': {}}

    def suggest(i):
        return api.suggest(i, manifest, real_dataset, entries)

    assert suggest(healthy) == {'action': 'new', 'content_type': 'heroes', 'record': {'name': 'Test Hero'}}
    assert suggest(wounded) == {'action': 'attach', 'to': '0001', 'field': 'wounded'}
    assert suggest(known) == {'action': 'link', 'content_type': 'command-cards', 'id': 5}
    assert suggest(feat)['record']['hero_id'] == hero['id']
    assert suggest(back)['record'] == {'deck': 'Rebel Hero', 'content_type': 'heroes', 'variant': hero['name']}
    assert suggest(class_back)['record']['variant'] == 'New Class'
    assert suggest(unit)['record']['affiliation'] == 'Mercenary'
    assert suggest(unit)['record']['iaspec'] == 'unit'


def test_iaspec_rule_reproduces_the_dataset(real_dataset):
    records = [r for t in ('deployment-cards', 'command-cards', 'companion-cards') for r in real_dataset.records(t)]
    for record in records:
        assert iaspec.iaspec_for(record, [r for r in records if r is not record]) == record['iaspec']


@pytest.mark.parametrize('raw, parsed', [
    ('Elite Death Troopers campaign', ('Death Troopers', 'elite', ['Campaign'])),
    ('Riot Trooper regular skirmish', ('Riot Trooper', 'regular', ['Skirmish'])),
    ('Elite-Royal-Guard_errata', ('Royal Guard', 'elite', [])),
    ('Royal Guard Champion Deployment Card', ('Royal Guard Champion', None, [])),
    ('Loth-cats', ('Loth-cats', None, [])),
])
def test_parse_deployment_name(raw, parsed):
    assert api.parse_deployment_name(raw) == parsed


def test_deployment_suggestions(real_dataset):
    album = ('X', 'Deployment Cards', 'Imperial')
    items = [item('0001', 'deployment-cards', 'Grand Admiral skirmish', album, {'affiliation': 'Imperial'}),
             item('0002', 'deployment-cards', 'Grand Admiral campaign', album, {'affiliation': 'Imperial'}),
             item('0003', 'deployment-cards', 'Elite Space Cats', album, {'affiliation': 'Imperial'}),
             item('0004', 'deployment-cards', 'Space Cats', album, {'affiliation': 'Imperial'}),
             item('0005', 'deployment-cards', 'Hero Person', album, {'affiliation': 'Imperial'}),
             item('0006', 'heroes', 'Hero Person Hero Healthy', ('X', 'Rebel Heroes'), {'hero': 'Hero Person'}),
             item('0007', 'command-cards', 'The Last Word')]
    manifest = {'items': items}

    def record(key, entries=None):
        i = next(i for i in items if i['key'] == key)
        return api.suggest(i, manifest, real_dataset, entries or {'items': {}, 'extra': {}})['record']

    assert record('0001') == {'name': 'Grand Admiral', 'elite': True, 'unique': True, 'modes': ['Skirmish'],
                                   'affiliation': 'Imperial', 'iaspec': 'grandadmiralskirmish'}
    assert record('0002')['iaspec'] == 'grandadmiralcampaign'
    assert {k: record('0003')[k] for k in ('name', 'elite', 'unique', 'iaspec')} == \
        {'name': 'Space Cat', 'elite': True, 'unique': False, 'iaspec': 'elitespacecat'}
    assert {k: record('0004')[k] for k in ('name', 'elite', 'iaspec')} == \
        {'name': 'Space Cat', 'elite': False, 'iaspec': 'spacecat'}
    assert {k: record('0005')[k] for k in ('elite', 'unique', 'modes')} == \
        {'elite': False, 'unique': True, 'modes': ['Skirmish']}
    assert record('0007')['iaspec'] == 'thelastword'  # iaspec keeps a leading "the" (thegrandinquisitor)
    # A saved entry counts too: once the skirmish card is saved, the campaign one still needs its mode.
    saved = {'items': {'0001': {'action': 'new', 'content_type': 'deployment-cards', 'record': record('0001')}}}
    assert record('0002', saved | {'extra': {}})['iaspec'] == 'grandadmiralcampaign'


def test_check_entry(real_dataset):
    good = {'action': 'new', 'content_type': 'agenda-decks', 'record': {'name': 'Deck'}}
    assert api.check_entry(good, real_dataset) == []
    bad = {'action': 'new', 'content_type': 'command-cards', 'record': {'name': 'X', 'cost': 'one'}}
    assert any('cost' in p for p in api.check_entry(bad, real_dataset))
    assert api.check_entry({'action': 'skip'}, real_dataset) == []


def test_normalise_entry_nulls_empty_nullable_lists(real_dataset):
    entry = {'action': 'new', 'content_type': 'reward-cards', 'record': {'name': 'R', 'type': 'Feat', 'traits': []}}
    assert api.check_entry(entry, real_dataset)
    assert api.normalise_entry(entry, real_dataset)['record']['traits'] is None
    assert api.check_entry(entry, real_dataset) == []


def test_normalise_entry_strips_text(real_dataset):
    entry = {'action': 'new', 'content_type': 'command-cards', 'record': {'name': 'Piece By Piece ', 'cost': 1}}
    assert api.normalise_entry(entry, real_dataset)['record'] == {'name': 'Piece By Piece', 'cost': 1}


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
