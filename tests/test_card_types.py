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


@pytest.mark.parametrize('lines,timing', [
    (['Apply +1 Speed to your hero.'], ['Passive']),
    (['2 <S>: Exhaust this card during your activation to push a figure.'], ['Exhaust']),
    (['<A>: Exhaust this card to recover 1 <D>.'], ['Action', 'Exhaust']),
    (['<Z>: Pierce 2', 'While attacking, apply +1 <D>.'], ['Passive', 'Surge']),
    (['Deplete this card to recover 3 <D>.'], ['Deplete']),
    (['Discard this card after you attack.'], ['Single-use']),
    (['During setup, deploy 1 additional figure.'], ['Setup']),
    (['During the Rebel upgrade stage, you may buy 1 additional item.'], ['Campaign']),
])
def test_timing_is_read_from_each_line(lines, timing):
    assert card_types.timing_of(lines)[0] == timing


def test_timing_flags_what_needs_a_closer_look():
    assert card_types.timing_of([]) == ([], ['No card text on the wiki'])
    assert card_types.timing_of(['Use when you rest.'])[1] == ['A "Use when…" line: Passive, or something else?']


def test_type_proposals():
    assert card_types.type_of('upgrade-cards', {'type': 'Armor'}, 'Infobox item', {}, []) == ('Armor', [])
    assert card_types.type_of('hero-class-cards', {'type': 'Feat'}, 'HeroClassCardInfobox', {}, [])[0] == 'Hero Feat'
    assert card_types.type_of('imperial-class-cards', {}, 'Imperial_Class_Card_Infobox', {'type': 'Attachment'},
                              [])[0] == 'Group Attachment'
    assert card_types.type_of('imperial-class-cards', {}, 'Imperial_Class_Card_Infobox', {}, [])[0] == 'Imperial Feat'
    reward = {'type': 'Feat', 'for': 'Rebel players'}
    assert card_types.type_of('reward-cards', reward, 'HeroClassCardInfobox', {}, [])[0] == 'Hero Feat'
    assert card_types.type_of('reward-cards', reward, 'Reward Card Infobox', {}, [])[0] == 'Party Feat'
    imperial = {'type': 'Feat', 'for': 'Imperial player'}
    assert card_types.type_of('reward-cards', imperial, 'Imperial_Class_Card_Infobox', {}, [])[0] == 'Imperial Feat'
    assert card_types.type_of('reward-cards', imperial, 'Imperial_Class_Card_Infobox',
                              {'ability1': 'Attach this card to a deployment card.'}, [])[0] == 'Group Attachment'


def test_fields_go_after_type_or_after_xp():
    assert list(card_types.with_fields({'id': 1, 'type': 'Feat', 'image': 'x'}, 'Hero Feat', ['Passive'])) == \
        ['id', 'type', 'timing', 'image']
    record = card_types.with_fields({'id': 1, 'xp': 2, 'image': 'x'}, 'Imperial Feat', ['Exhaust'])
    assert list(record) == ['id', 'xp', 'type', 'timing', 'image'] and record['timing'] == ['Exhaust']
    # Written again: replaced in place, not repeated.
    assert card_types.with_fields(record, 'Group Attachment', ['Passive'])['type'] == 'Group Attachment'


@pytest.fixture
def dataset(dataset_copy, tmp_path, monkeypatch):
    if not dataset_copy.path('imperial-class-cards').exists():
        pytest.skip('The checkout has no Imperial class cards')
    monkeypatch.setattr(settings, 'STAGING', tmp_path / 'staging')
    return dataset_copy


def test_run_writes_once_every_card_is_done(dataset):
    found = card_types.proposals(dataset, pages={})
    entries = {'cards': {card_id: {'type': p['type'], 'timing': p['timing'], 'done': True}
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
    assert all(r['type'] in card_types.COLLECTIONS['imperial-class-cards'] and r['timing'] for r in written)
    heroes = json.loads(dataset.path('hero-class-cards').read_text(encoding='utf-8'))
    assert not any(r['type'] == card_types.OLD_FEAT for r in heroes)


def test_server_saves_entries(dataset):
    server.Handler.dataset = dataset
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    try:
        card = dataset.records('imperial-class-cards')[0]
        entry = {'type': 'Hero Feat', 'timing': [], 'done': False}
        saved = json.loads(call('PUT', f'{base}/api/card-types/{card["id"]}', entry)[2])
        assert saved == {'saved': True, 'problems': ["Type 'Hero Feat' isn't one of imperial-class-cards's",
                                                     'No timing']}
        panel = json.loads(call('GET', f'{base}/api/card-types')[2])
        assert panel['entries'] == {card['id']: entry} and panel['problems'][card['id']] == saved['problems']
        assert len(panel['cards']) == sum(len(dataset.records(t)) for t in card_types.COLLECTIONS)
        assert call('GET', f'{base}/card-types')[1].startswith('text/html')
    finally:
        httpd.shutdown()


def test_setup_includes_the_first_round_and_after_setup():
    assert card_types.timing_of(['At the start of the first round, reveal the trigger.'])[0] == ['Setup']
    assert card_types.timing_of(['After setup of each mission, remove 1 crate.'])[0] == ['Setup']


def test_a_cache_file_per_title():
    from pathlib import Path
    names = {card_types.cache_path(Path('x'), t).name for t in ['Into The Fray', 'Into the Fray', "Smuggler's Luck",
                                                                  'Smugglers Luck']}
    assert len(names) == 4
