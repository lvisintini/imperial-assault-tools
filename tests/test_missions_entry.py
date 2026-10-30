import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from ia_tools import mission_entries, settings
from ia_tools.enter import server
from tests.test_enter import call


@pytest.fixture
def dataset(dataset_copy, tmp_path, monkeypatch):
    if not dataset_copy.path('skirmish-mission-cards').exists():
        pytest.skip('The checkout has no skirmish mission cards (data 2.0.0)')
    monkeypatch.setattr(settings, 'STAGING', tmp_path / 'staging')
    # Start from no scenarios and no story rewards, as before they were entered.
    cards = [c | {'scenario': None} for c in dataset_copy.records('skirmish-mission-cards')]
    dataset_copy.path('skirmish-mission-cards').write_text(json.dumps(cards, indent=2), encoding='utf-8')
    story = {m['id'] for m in dataset_copy.records('missions') if m['content_type'] == mission_entries.STORY}
    rows = [r for r in dataset_copy.records('mission-rewards') if r['mission_id'] not in story]
    dataset_copy.path('mission-rewards').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    dataset_copy._data.clear()
    return dataset_copy


def a_reward(dataset, content_type='reward-cards'):
    return next(r for r in mission_entries.rewards(dataset).values() if r['content_type'] == content_type)


def row(reward, choice=False):
    return {'content_type': reward['content_type'], 'content_id': reward['id'], 'credits': False, 'choice': choice}


CREDITS = {'content_type': None, 'content_id': None, 'credits': True, 'choice': False}


def everything_entered(dataset, rewards=lambda mission: []):
    return {'scenarios': {c['id']: 'A' for c in mission_entries.skirmish_cards(dataset)},
            'rewards': {m['id']: {'rows': rewards(m), 'done': True, 'note': ''}
                        for m in mission_entries.story_missions(dataset)}}


def test_the_cards_and_missions_entered(dataset):
    cards = mission_entries.skirmish_cards(dataset)
    assert len(cards) == len(dataset.records('skirmish-mission-cards')) and all(c['map'] and c['products'] for c in cards)
    story = mission_entries.story_missions(dataset)
    assert len(story) == len(dataset.records(mission_entries.STORY)) and all(m['rows'] == 0 for m in story)
    rewards = mission_entries.rewards(dataset)
    assert {r['content_type'] for r in rewards.values()} == set(mission_entries.REWARD_TYPES)
    skirmish_only = {c['id'] for c in dataset.records('deployment-cards') if 'Campaign' not in c['modes']}
    assert not skirmish_only & {r['id'] for r in rewards.values()}


def test_check_rewards(dataset):
    known = mission_entries.rewards(dataset)
    reward = a_reward(dataset)
    assert mission_entries.check_rewards({'rows': [row(reward), CREDITS], 'done': True}, known) == []
    assert mission_entries.check_rewards({'rows': [], 'done': True}, known) == []  # a mission that gives nothing
    problems = mission_entries.check_rewards({'rows': [
        row(reward), row(reward, choice=True), {'content_type': 'reward-cards', 'content_id': 'nope', 'credits': False},
        CREDITS | {'content_type': 'reward-cards'},
    ]}, known)
    assert problems == [f"{reward['name']} is listed twice", "Unknown reward 'reward-cards:nope'",
                        'A credits row names a card', 'A choice needs at least 2 alternatives']


def test_nothing_is_written_until_everything_is_entered(dataset):
    before = dataset.path('mission-rewards').read_text(encoding='utf-8')
    entries = everything_entered(dataset)
    entries['scenarios'].popitem()
    entries['rewards'][mission_entries.story_missions(dataset)[0]['id']]['done'] = False
    mission_entries.save(entries)
    summary, problems = mission_entries.run(dataset)
    assert len(problems) == 1 and '1 skirmish cards have no scenario yet' in problems[0]  # story missions are optional
    assert dataset.path('mission-rewards').read_text(encoding='utf-8') == before


def test_run_writes_scenarios_and_replaces_story_rewards(dataset):
    first = mission_entries.story_missions(dataset)[0]
    reward, ally = a_reward(dataset), a_reward(dataset, 'deployment-cards')
    before = list(dataset.records('mission-rewards'))
    entries = everything_entered(dataset, lambda m: [row(reward), CREDITS] if m['id'] == first['id'] else [])
    entries['scenarios'][dataset.records('skirmish-mission-cards')[0]['id']] = 'B'
    mission_entries.save(entries)
    summary, problems = mission_entries.run(dataset, check=True)
    assert problems == [] and summary['rows'] == 2 and summary['without rewards'] == summary['story'] - 1
    assert summary['scenario'] == {'A': summary['skirmish'] - 1, 'B': 1}
    assert json.loads(dataset.path('mission-rewards').read_text(encoding='utf-8')) == before  # --check writes nothing

    mission_entries.run(dataset)
    cards = json.loads(dataset.path('skirmish-mission-cards').read_text(encoding='utf-8'))
    assert [c['scenario'] for c in cards[:2]] == ['B', 'A']
    written = json.loads(dataset.path('mission-rewards').read_text(encoding='utf-8'))
    assert written == before + [{'mission_id': first['id'], 'content_type': 'reward-cards', 'content_id': reward['id'],
                                 'credits': False, 'choice': False},
                                {'mission_id': first['id'], 'content_type': None, 'content_id': None, 'credits': True,
                                 'choice': False}]

    # Run again after a correction: the mission's rows are replaced, not added to.
    entries['rewards'][first['id']]['rows'] = [row(ally, choice=True), row(reward, choice=True)]
    mission_entries.save(entries)
    dataset._data.clear()
    mission_entries.run(dataset)
    written = json.loads(dataset.path('mission-rewards').read_text(encoding='utf-8'))
    assert [(r['content_id'], r['choice']) for r in written[len(before):]] == [(ally['id'], True), (reward['id'], True)]


def test_server_saves_entries(dataset):
    server.Handler.dataset = dataset
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_port}'
    try:
        card = mission_entries.skirmish_cards(dataset)[0]
        assert json.loads(call('PUT', f'{base}/api/missions/scenarios/{card["id"]}', 'B')[2]) == {'saved': True}
        mission = mission_entries.story_missions(dataset)[0]
        entry = {'rows': [row(a_reward(dataset), choice=True)], 'done': False, 'note': ''}
        saved = json.loads(call('PUT', f'{base}/api/missions/rewards/{mission["id"]}', entry)[2])
        assert saved == {'saved': True, 'problems': ['A choice needs at least 2 alternatives']}
        call('PUT', f'{base}/api/missions/scenarios/{card["id"]}', None)  # cleared
        assert mission_entries.load() == {'scenarios': {}, 'rewards': {mission['id']: entry}}

        panel = json.loads(call('GET', f'{base}/api/missions')[2])
        assert panel['entries'] == {mission['id']: entry} and panel['problems'][mission['id']] == saved['problems']
        assert {'skirmish', 'story', 'rewards', 'scenarios'} <= set(panel)
        assert call('GET', f'{base}/missions')[1].startswith('text/html')
    finally:
        httpd.shutdown()
