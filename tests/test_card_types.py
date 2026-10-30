import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from ia_tools import card_types, settings
from ia_tools.enter import server
from tests.test_enter import call


def test_infobox_splits_top_level_fields_only():
    template, fields = card_types.infobox(
        "{{HeroClassCardInfobox\n|hero = [[Jyn Odan|Jyn]]\n|effect1 = 1 {{S}}: Exhaust this card.\n|cost = 2}}\n"
        "[[Category:Hero Class Card]]")
    assert template == 'HeroClassCardInfobox'
    assert fields == {'hero': '[[Jyn Odan|Jyn]]', 'effect1': '1 {{S}}: Exhaust this card.', 'cost': '2'}
    assert card_types.infobox('No template here') == (None, {})


def test_ability_lines_keep_their_order_and_icons():
    fields = {'effect2': "'''Order:''' {{A}} Choose a [[figure]].", 'effect1': '{{Z}}: +1 {{D}}', 'cost': '1',
              'ability10': 'Last', 'effect3': ' '}
    assert card_types.ability_lines(fields) == ['<Z>: +1 <D>', 'Order: <A> Choose a figure.', 'Last']


def test_type_proposals():
    assert card_types.type_of('imperial-class-cards', {}, {'type': 'Attachment'}) == 'Group Attachment'
    assert card_types.type_of('imperial-class-cards', {}, {}) == 'Feat'
    assert card_types.type_of('reward-cards', {'type': 'Feat', 'for': 'Rebel players'}, {}) == 'Feat'
    imperial = {'type': 'Feat', 'for': 'Imperial player'}
    assert card_types.type_of('reward-cards', imperial, {}) == 'Feat'
    assert card_types.type_of('reward-cards', imperial,
                              {'ability1': 'Attach this card to a deployment card.'}) == 'Group Attachment'
    # A Rebel card's text can say "attach" without being attached to a group.
    assert card_types.type_of('reward-cards', {'type': 'Feat', 'for': 'Rebel players'},
                              {'ability1': 'Attach a weapon.'}) == 'Feat'


def test_type_goes_in_place_or_after_xp():
    assert card_types.with_type({'id': 1, 'type': 'Feat', 'image': 'x'}, 'Group Attachment') == \
        {'id': 1, 'type': 'Group Attachment', 'image': 'x'}
    record = card_types.with_type({'id': 1, 'xp': 2, 'image': 'x'}, 'Feat')
    assert list(record) == ['id', 'xp', 'type', 'image']
    # Written again: replaced in place, not repeated.
    assert card_types.with_type(record, 'Group Attachment')['type'] == 'Group Attachment'


@pytest.fixture
def dataset(dataset_copy, tmp_path, monkeypatch):
    if not dataset_copy.path('imperial-class-cards').exists():
        pytest.skip('The checkout has no Imperial class cards')
    monkeypatch.setattr(settings, 'STAGING', tmp_path / 'staging')
    return dataset_copy


def test_run_writes_once_every_card_is_done(dataset):
    found = card_types.proposals(dataset, pages={})
    entries = {'cards': {card_id: {'type': p['type'], 'done': True}
                         for card_id, p in found.items()}}
    last = next(iter(entries['cards']))
    entries['cards'][last]['done'] = False
    card_types.save(entries)
    summary, problems = card_types.run(dataset)
    assert problems == ['1 cards are not done yet'] and summary['left'] == 1

    entries['cards'][last]['done'] = True
    card_types.save(entries)
    summary, problems = card_types.run(dataset)
    assert problems == [] and summary['done'] == summary['cards'] == len(found)
    written = json.loads(dataset.path('imperial-class-cards').read_text(encoding='utf-8'))
    assert all(r['type'] in card_types.COLLECTIONS['imperial-class-cards'] for r in written)
    rewards = json.loads(dataset.path('reward-cards').read_text(encoding='utf-8'))
    assert [r['type'] for r in rewards if r['type'] in card_types.GEAR] == \
        [r['type'] for r in dataset.records('reward-cards') if r['type'] in card_types.GEAR]  # items keep their type


def test_server_saves_entries(dataset):
    server.Handler.dataset = dataset
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    try:
        card = dataset.records('imperial-class-cards')[0]
        entry = {'type': 'Armor', 'done': False}
        saved = json.loads(call('PUT', f'{base}/api/card-types/{card["id"]}', entry)[2])
        assert saved == {'saved': True, 'problems': ["Type 'Armor' isn't one of imperial-class-cards's"]}
        panel = json.loads(call('GET', f'{base}/api/card-types')[2])
        assert panel['entries'] == {card['id']: entry} and panel['problems'][card['id']] == saved['problems']
        assert len(panel['cards']) == sum(1 for t in card_types.COLLECTIONS for r in dataset.records(t)
                                          if r.get('type') not in card_types.GEAR)
        assert call('GET', f'{base}/card-types')[1].startswith('text/html')
    finally:
        httpd.shutdown()


def test_a_cache_file_per_title():
    from pathlib import Path
    names = {card_types.cache_path(Path('x'), t).name for t in ['Into The Fray', 'Into the Fray', "Smuggler's Luck",
                                                                  'Smugglers Luck']}
    assert len(names) == 4
