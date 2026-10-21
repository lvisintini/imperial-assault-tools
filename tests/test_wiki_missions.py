import json

import pytest

from ia_tools import wiki_missions
from ia_tools.wiki_missions import infobox, rewards, split_rewards, RewardIndex


def test_infobox_one_field_per_line():
    text = """[[File:Brushfire Mission.jpg|left|thumb|1061x1061px]]{{Mission Infobox
| title    = Brushfire
| hero     = [[Fenn Signis]]
| reward   = [[Veteran Prowess]]
}}
[[Category:Red Side Mission]]"""
    assert infobox(text) == {'title': 'Brushfire', 'hero': '[[Fenn Signis]]', 'reward': '[[Veteran Prowess]]'}


def test_infobox_on_one_line_with_links_and_templates_inside():
    text = ("{{Agenda_Card_Infobox|agenda_set = [[Pursuit of the Enemy]]|reward = [[Imperial Industry (Reward Card)|"
            "Imperial Industry]]|note = {{small|x|y}}|card = Fireinthesky.png}} [[Category:Agenda]]")
    assert infobox(text) == {'agenda_set': '[[Pursuit of the Enemy]]',
                             'reward': '[[Imperial Industry (Reward Card)|Imperial Industry]]',
                             'note': '{{small|x|y}}', 'card': 'Fireinthesky.png'}


def test_infobox_of_another_template_or_none():
    assert infobox('{{Infobox_unit|name = Fenn}}') is None
    assert infobox(None) is None
    hero = '{{Infobox_hero|name = Ko-Tun|mission = Extraction|reward = Alliance Efficiency}}'
    assert infobox(hero, wiki_missions.HERO_INFOBOX)['mission'] == 'Extraction'


def test_split_rewards_ignores_commas_in_links():
    assert split_rewards('Any 1 [[:Category:Spectre|Spectre]] ally, [[A, B|AB]]') == [
        'Any 1 [[:Category:Spectre|Spectre]] ally', ' [[A, B|AB]]']
    assert split_rewards('None') == []
    assert split_rewards(None) == []


@pytest.fixture(scope='module')
def index(real_dataset):
    return RewardIndex(real_dataset)


def names(rows):
    return [(r['content_type'], r['name'], r['credits'], r['choice']) for r in rows]


def test_rewards_match_cards_by_subtitle_and_qualifier(index):
    rows, problems = rewards('[[Han Solo|Han Solo (Scoundrel)]]', index, {})
    assert names(rows) == [('deployment-cards', 'Han Solo (Scoundrel)', False, False)] and not problems
    rows, problems = rewards('[[Luke Skywalker|Luke Skywalker (Hero of the Rebellion)]]', index, {})
    assert names(rows) == [('deployment-cards', 'Luke Skywalker (Hero of the Rebellion)', False, False)]
    rows, _ = rewards('[[Imperial Industry (Reward Card)|Imperial Industry]]', index, {})
    assert names(rows) == [('reward-cards', 'Imperial Industry', False, False)]


def test_rewards_credits_choice_and_problems(index):
    rows, problems = rewards('Credits', index, {})
    assert rows == [{'content_type': None, 'content_id': None, 'name': 'Credits', 'credits': True, 'choice': False}]
    rows, problems = rewards('Any 1 [[:Category:Spectre|Spectre]] ally, [[Rough Rider]]', index,
                             {'Spectre': ['Hera Syndulla', 'Kanan Jarrus (Campaign)']})
    assert names(rows) == [('deployment-cards', 'Hera Syndulla (Spectre-2)', False, True),
                           ('deployment-cards', 'Kanan Jarrus (Spectre-1)', False, True),
                           ('reward-cards', 'Rough Rider', False, False)]
    rows, problems = rewards('[[Nothing Like This]], Any 1 [[:Category:Nope|Nope]] ally', index, {})
    assert rows == [] and problems == ["'Nothing Like This': not in the dataset", "unknown category 'Nope'"]


def test_rewards_group_ally_is_its_regular_card(index):
    rows, problems = rewards('[[Rebel Saboteur]]', index, {})
    assert len(rows) == 1 and not problems
    assert index.card('Rebel Saboteur')[0][1]['elite'] is False


def test_rewards_wiki_spelling_of_a_renamed_reward(index):
    rows, problems = rewards('[[Adrenal Implant]]', index, {})
    assert len(rows) == 1 and not problems


class FakeClient:
    """Answers the MediaWiki API from a dict of pages; every other title is missing."""

    def __init__(self, pages, categories=None):
        self.pages, self.categories, self.queries = pages, categories or {}, 0

    def get(self, url, params=None):
        self.queries += 1
        if params.get('list') == 'categorymembers':
            members = self.categories.get(params['cmtitle'].removeprefix('Category:'), [])
            answer = {'query': {'categorymembers': [{'ns': 0, 'title': t} for t in members]}}
        else:
            titles = params['titles'].split('|')
            answer = {'query': {'pages': [
                {'title': t, 'revisions': [{'revid': 1, 'slots': {'main': {'content': self.pages[t]}}}]}
                if t in self.pages else {'title': t, 'missing': True} for t in titles]}}
        return type('Response', (), {'json': lambda self_: answer})()


def test_run_caches_heroes_rewards_and_problems(dataset_copy, tmp_path):
    missions = wiki_missions.mission_records(dataset_copy)
    key = {r['name']: wiki_missions.cache_key(dataset_copy, t, r) for t, r in missions}
    hero = next(h for h in dataset_copy.records('heroes') if h['name'] == 'Fenn Signis')
    client = FakeClient({
        'Brushfire': '{{Mission Infobox|reward = [[Veteran Prowess]]}}',  # no hero: Fenn's page names the mission
        'Fenn Signis (Hero)': '{{Infobox_hero|name = Fenn Signis|mission = [[Brushfire]]}}',
        'A Simple Task': '{{Mission_Infobox|reward = Credits|imperial_reward = [[Nothing]]}}',
    })
    cache = wiki_missions.run(client, dataset_copy, root=tmp_path, log=lambda *_: None)
    brushfire, task = cache['missions'][key['Brushfire']], cache['missions'][key['A Simple Task']]
    assert brushfire['hero'] == {'text': 'Fenn Signis', 'id': hero['id']} and brushfire['problems'] == []
    assert [r['name'] for r in brushfire['rewards']] == ['Veteran Prowess']
    assert [(r['name'], r['field']) for r in task['rewards']] == [('Credits', 'reward')]
    assert task['problems'] == ["imperial_reward: 'Nothing': not in the dataset"]
    assert len(cache['missions']) == len(missions)
    written = json.loads((tmp_path / 'wiki' / 'missions.json').read_text())
    assert written['missions'][key['Brushfire']]['page'] == 'Brushfire'
    queries = client.queries
    wiki_missions.run(client, dataset_copy, root=tmp_path, log=lambda *_: None)
    assert client.queries == queries  # the second run reads the cached pages
