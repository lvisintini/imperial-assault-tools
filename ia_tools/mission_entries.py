"""The mission data the maintainer enters by hand in ia enter (its Missions page), and ia missions, which writes it to
the data repo (data 2.0.0): each skirmish mission card's scenario (A or B, as printed) and the story missions'
rewards. The wiki has neither: its story mission pages give no reward, and its skirmish pages no scenario.

staging/mission-entries/entries.json:
    {"scenarios": {"<skirmish card id>": "A"},
     "rewards": {"<mission id>": {"rows": [{"content_type": "reward-cards", "content_id": "<id>", "credits": false,
                                            "choice": false}],
                                  "done": true, "note": "..."}}}

ia missions writes only when every skirmish card has a scenario and every story mission is marked done (a story
mission done with no rows gives no card or credits). A story mission's rows replace the ones it had; other missions'
rows stay as they are."""
import json
from collections import Counter

from ia_tools import settings
from ia_tools.dataset import dumps
from ia_tools.layouts import products_of

SCENARIOS = ('A', 'B')
SKIRMISH = 'skirmish-mission-cards'
STORY = 'campaign-story-mission-cards'
# What a mission can reward: reward cards, and the Campaign deployment cards (an ally or a villain).
REWARD_TYPES = ('reward-cards', 'deployment-cards')


def entries_path():
    return settings.STAGING / 'mission-entries' / 'entries.json'


def load():
    path = entries_path()
    entries = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return {'scenarios': entries.get('scenarios', {}), 'rewards': entries.get('rewards', {})}


def save(entries):
    path = entries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')


def skirmish_cards(dataset):
    """[{"id", "name", "image", "scenario", "map", "products"}] in the file's order, scenario being the data's."""
    missions = {m['content_id']: m for m in dataset.records('missions') if m['content_type'] == SKIRMISH}
    maps = {m['id']: m['name'] for m in dataset.records('maps')}
    products = products_of(dataset, 'missions')
    return [{'id': c['id'], 'name': c['name'], 'image': c['image'], 'scenario': c['scenario'],
             'map': maps.get(missions[c['id']]['map_id']), 'products': products.get(missions[c['id']]['id'], [])}
            for c in dataset.records(SKIRMISH)]


def story_missions(dataset):
    """[{"id", "name", "image", "products", "rows"}]: the story missions' index rows, in the cards' file order, rows
    being how many mission-rewards rows the data has for each."""
    index = {m['content_id']: m['id'] for m in dataset.records('missions') if m['content_type'] == STORY}
    products = products_of(dataset, 'missions')
    rows = Counter(r['mission_id'] for r in dataset.records('mission-rewards'))
    return [{'id': index[c['id']], 'name': c['name'], 'image': c['image'], 'products': products.get(index[c['id']], []),
             'rows': rows[index[c['id']]]} for c in dataset.records(STORY)]


def rewards(dataset):
    """{"<content type>:<id>": {"content_type", "id", "name", "detail", "image"}}: what a story mission can reward."""
    found = {}
    for card in dataset.records('reward-cards'):
        found[f"reward-cards:{card['id']}"] = {'content_type': 'reward-cards', 'id': card['id'], 'name': card['name'],
                                               'detail': f"{card['class']} · {card['for']}", 'image': card['image']}
    for card in dataset.records('deployment-cards'):
        if 'Campaign' in card['modes']:
            detail = ' · '.join(filter(None, [card['description'], 'Elite' if card['elite'] else 'Regular',
                                              card['affiliation']]))
            found[f"deployment-cards:{card['id']}"] = {'content_type': 'deployment-cards', 'id': card['id'],
                                                       'name': card['name'], 'detail': detail, 'image': card['image']}
    return found


def panel(dataset):
    """What the Missions page shows."""
    entries = load()
    known = rewards(dataset)
    return {'skirmish': skirmish_cards(dataset), 'story': story_missions(dataset), 'rewards': known,
            'scenarios': entries['scenarios'], 'entries': entries['rewards'],
            'problems': {mission_id: check_rewards(entry, known) for mission_id, entry in entries['rewards'].items()}}


def check_rewards(entry, known):
    """Problems with one story mission's entry."""
    problems, seen = [], set()
    rows = entry.get('rows', [])
    for row in rows:
        if row.get('credits'):
            if row.get('content_type') or row.get('content_id'):
                problems.append('A credits row names a card')
            key = 'credits'
        else:
            key = f"{row.get('content_type')}:{row.get('content_id')}"
            if key not in known:
                problems.append(f'Unknown reward {key!r}')
                continue
        if key in seen:
            problems.append(f"{known[key]['name'] if key in known else 'Credits'} is listed twice")
        seen.add(key)
    if sum(1 for r in rows if r.get('choice')) == 1:
        problems.append('A choice needs at least 2 alternatives')
    return problems


def plan(dataset, entries=None):
    """(skirmish cards, mission-rewards rows, summary, problems): the two files after writing the entries."""
    entries = entries or load()
    cards = [dict(c) for c in dataset.records(SKIRMISH)]
    missions = {m['id']: m for m in story_missions(dataset)}
    known = rewards(dataset)
    problems = [f'{card_id}: not a skirmish mission card' for card_id in entries['scenarios']
                if card_id not in {c['id'] for c in cards}]
    problems += [f"{card_id}: scenario {value!r} isn't A or B" for card_id, value in entries['scenarios'].items()
                 if value not in SCENARIOS]
    problems += [f'{mission_id}: not a story mission' for mission_id in entries['rewards'] if mission_id not in missions]
    for card in cards:
        card['scenario'] = entries['scenarios'].get(card['id'], card['scenario'])
    left = [c['name'] for c in cards if c['scenario'] is None]
    if left:
        problems.append(f"{len(left)} skirmish cards have no scenario yet: {', '.join(left[:5])}"
                        f"{', …' if len(left) > 5 else ''}")
    done = [m for m in missions if entries['rewards'].get(m, {}).get('done')]
    if len(done) < len(missions):
        problems.append(f'{len(missions) - len(done)} story missions are not done yet')
    for mission_id in done:
        problems += [f"{missions[mission_id]['name']}: {p}" for p in check_rewards(entries['rewards'][mission_id], known)]
    replaced = set(done)
    rows = [r for r in dataset.records('mission-rewards') if r['mission_id'] not in replaced]
    for mission_id in done:
        rows += [{'mission_id': mission_id, 'content_type': None if r.get('credits') else r['content_type'],
                  'content_id': None if r.get('credits') else r['content_id'], 'credits': bool(r.get('credits')),
                  'choice': bool(r.get('choice'))} for r in entries['rewards'][mission_id]['rows']]
    summary = {'skirmish': len(cards), 'scenarios': len(cards) - len(left),
               'scenario': dict(Counter(c['scenario'] for c in cards if c['scenario'])),
               'story': len(missions), 'done': len(done),
               'rows': sum(len(entries['rewards'][m]['rows']) for m in done),
               'without rewards': sum(1 for m in done if not entries['rewards'][m]['rows'])}
    return cards, rows, summary, problems


def run(dataset, check=False):
    """(summary, problems); writes skirmish-mission-cards.json and mission-rewards.json unless checking or there are
    problems."""
    cards, rows, summary, problems = plan(dataset)
    if not problems and not check:
        dataset.path(SKIRMISH).write_text(dumps(cards), encoding='utf-8')
        dataset.path('mission-rewards').write_text(dumps(rows), encoding='utf-8')
    return summary, problems
