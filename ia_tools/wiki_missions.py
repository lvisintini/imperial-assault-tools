"""ia wiki --missions: each campaign mission's hero and rewards, from its page on the Imperial Assault wiki.

Mission pages carry an infobox, written either one field per line or all on one line:

    {{Mission Infobox | category = Red | hero = [[Fenn Signis]] | reward = [[Veteran Prowess]] | ...}}
    {{Agenda_Card_Infobox|agenda_set = [[Pursuit of the Enemy]]|reward = [[Bounty]]|...}}

`hero` is who a red side mission is for; `reward` is what winning it gives: a card ("[[Han Solo|Han Solo
(Scoundrel)]]"), "Credits", or a choice from a category ("Any 1 [[:Category:Spectre|Spectre]] ally"), several
separated by commas. Some missions also give the other side something: `imperial_reward` (side missions) and
`threat_reward` (threat missions). Every hero's own page names their mission too (`{{Infobox_hero|mission = ...}}`),
which fills in red missions whose infobox has no `hero`.

ia wiki --missions fetches the page of every mission record in the dataset (story, threat and side mission cards, and
agenda cards that are missions) and of every hero, matches heroes and rewards to records, and writes
staging/wiki/missions.json, keyed by record id (ids survive data 2.0.0's renames; "<content type>:<id>" in 1.x data):

    {"<id>": {"content_type", "name", "page", "revid", "hero": {"text", "id"} | None,
              "reward": {field: raw text} | None,
              "rewards": [{"content_type", "content_id", "name", "credits", "choice", "field"}], "problems": [...]}}

A reward the dataset can't place is a problem, never a guess; the data repo's migration reads this file."""
import json
import re
from datetime import datetime, timezone

from ia_tools import settings
from ia_tools.match import normalise
from ia_tools.staging import slugify
from ia_tools.wiki import API_URL, LINK

# The dataset's mission collections, before and after data 2.0.0 split and renamed them.
MISSION_TYPES = [
    'story-mission-cards', 'threat-mission-cards', 'side-mission-cards',
    'campaign-story-missions', 'campaign-threat-missions', 'campaign-hero-side-missions',
    'campaign-ally-side-missions', 'campaign-regular-side-missions',
]
# Dataset names that aren't the wiki's (typos in the data, fixed in data 2.0.0), and the wiki's title for them.
TITLES = {
    'Despertate Hour': 'Desperate Hour', 'Vipers Den': "Viper's Den", 'Cloud Citys Secret': "Cloud City's Secret",
    'A Heros Welcome': "A Hero's Welcome", 'Unfninished Business': 'Unfinished Business',
    'Brace For Impact': 'Brace for Impact', 'Strength Of Command': 'Strength of Command',
    'Anchorhead Affair': 'The Anchorhead Affair',
}
# Where a name is also a command card or a hero, the wiki adds the page's kind.
DISAMBIGUATIONS = (' (Side Mission)', ' (Story Mission)', ' (Agenda Mission)', ' (Mission)')
MISSION_INFOBOX = re.compile(r'\{\{\s*(?:Mission[ _]Infobox|Agenda[ _]Card[ _]Infobox)', re.I)
HERO_INFOBOX = re.compile(r'\{\{\s*Infobox[ _]hero', re.I)
# Infobox fields that name a mission's rewards, whoever receives them.
REWARD_FIELDS = ('reward', 'imperial_reward', 'threat_reward')
# Words the wiki adds to a page title to tell pages apart: "Gaarkhan (Hero)", "Imperial Industry (Reward Card)".
QUALIFIER = re.compile(r'\s*\((?:Hero|Reward Card|Campaign|Ally|Villain|Deployment Card)\)\s*$', re.I)
ANY_OF = re.compile(r'^any\s+1\s+\[\[:Category:([^\]|]+)(?:\|[^\]]*)?\]\]', re.I)
BATCH = 50
# Reward names data 1.x spells differently from the card (fixed in data 2.0.0): the wiki's name → the old one.
REWARD_ALIASES = {'adrenalimplant': 'adrenalinimplant'}


def infobox(wikitext, template=MISSION_INFOBOX):
    """The infobox's fields, {name: raw value}, or None if the page has none."""
    match = template.search(wikitext or '')
    if not match:
        return None
    depth, i, start = 0, match.start(), match.end()
    while i < len(wikitext):  # the infobox's own closing braces, past the [[links]] and {{templates}} inside it
        pair = wikitext[i:i + 2]
        if pair in ('{{', '[['):
            depth, i = depth + 1, i + 2
        elif pair in ('}}', ']]'):
            depth, i = depth - 1, i + 2
            if depth == 0:
                break
        else:
            i += 1
    body, fields, depth, part = wikitext[start:i - 2], {}, 0, ''
    for j, char in enumerate(body + '|'):
        pair = body[j:j + 2]
        if pair in ('{{', '[['):
            depth += 1
        elif pair in ('}}', ']]'):
            depth -= 1
        if char == '|' and depth == 0:
            key, sep, value = part.partition('=')
            if sep:
                fields[key.strip().lower()] = value.strip()
            part = ''
        else:
            part += char
    return fields


class RewardIndex:
    """Reward cards, deployment cards and heroes by name, for matching the wiki's links."""

    def __init__(self, dataset):
        self.rewards, self.deployments, self.heroes = {}, {}, {}
        for record in dataset.records('reward-cards'):
            self.rewards.setdefault(normalise(record['name']), []).append(record)
        for record in dataset.records('deployment-cards'):
            if 'Campaign' in record['modes']:  # missions are campaign play; a skirmish-only version never applies
                self.deployments.setdefault(normalise(record['name']), []).append(record)
                if record.get('description'):
                    self.deployments.setdefault(normalise(record['name'] + record['description']), []).append(record)
        for record in dataset.records('heroes'):
            self.heroes.setdefault(normalise(record['name']), []).append(record)

    def card(self, text):
        """[(content_type, record)] a link's text names: one entry, or several when it's ambiguous, or none."""
        name = QUALIFIER.sub('', text)
        key = normalise(name)
        rewards = self.rewards.get(key) or self.rewards.get(REWARD_ALIASES.get(key), [])
        found = [('reward-cards', r) for r in rewards]
        subtitled = re.match(r'^(.*?)\s*\((.+)\)$', name)  # "Han Solo (Scoundrel)", "Darth Vader (Lord of the Sith)"
        keys = [normalise(subtitled[1] + subtitled[2])] if subtitled else [normalise(name)]
        for key in keys:
            found += [('deployment-cards', r) for r in self.deployments.get(key, [])]
        regular = [(t, r) for t, r in found if t == 'deployment-cards' and not r['elite']]
        if len(found) == 2 and len(regular) == 1 and {r['name'] for _, r in found} == {regular[0][1]['name']}:
            return regular  # a group ally is its regular card; earned again, it's the elite one (a rule, not data)
        return found

    def hero(self, value):
        links = LINK.findall(value or '')
        if not links:
            return None
        text = QUALIFIER.sub('', links[0][1] or links[0][0])
        found = self.heroes.get(normalise(text), [])
        return {'text': text, 'id': found[0]['id'] if len(found) == 1 else None}


def rewards(value, index, categories):
    """The reward field → (rows, problems). categories maps a category name to its member page titles."""
    rows, problems = [], []
    for part in split_rewards(value):
        if re.fullmatch(r'(\d+\s+)?credits', part.strip(), re.I):
            rows.append({'content_type': None, 'content_id': None, 'name': 'Credits', 'credits': True, 'choice': False})
            continue
        any_of = ANY_OF.match(part.strip())
        if any_of:
            members = categories.get(any_of[1].strip())
            if members is None:
                problems.append(f'unknown category {any_of[1]!r}')
                continue
            for title in members:
                found = index.card(title)
                if len(found) == 1:
                    rows.append(row(*found[0], choice=True))
                else:
                    problems.append(f'{any_of[1]} member {title!r}: {describe(found)}')
            continue
        links = LINK.findall(part)
        if not links:
            problems.append(f'no link in {part.strip()!r}')
            continue
        target, label = links[0]
        # The label first: it's the one with the subtitle ("[[Luke Skywalker|Luke Skywalker (Hero of the Rebellion)]]").
        found = index.card(label) if label else []
        found = found if len(found) == 1 else index.card(target) or found
        if len(found) == 1:
            rows.append(row(*found[0], choice=False))
        else:
            problems.append(f'{(label or target)!r}: {describe(found)}')
    return rows, problems


def split_rewards(value):
    """Comma-separated parts, ignoring commas inside [[links]]."""
    parts, depth, part = [], 0, ''
    for i, char in enumerate(value or ''):
        pair = value[i:i + 2]
        if pair == '[[':
            depth += 1
        elif pair == ']]':
            depth -= 1
        if char == ',' and depth == 0:
            parts.append(part)
            part = ''
        else:
            part += char
    return [p for p in parts + [part] if p.strip() and p.strip().lower() != 'none']


def row(content_type, record, choice):
    name = record['name'] + (f" ({record['description']})" if record.get('description') else '')
    return {'content_type': content_type, 'content_id': record['id'], 'name': name, 'credits': False,
            'choice': choice}


def describe(found):
    if not found:
        return 'not in the dataset'
    return 'ambiguous: ' + ', '.join(f"{t} {r['name']}{' elite' if r.get('elite') else ''}" for t, r in found)


def mission_records(dataset):
    """(content_type, record) for every mission in the dataset, whichever generation of names it uses."""
    types = [t for t in MISSION_TYPES if dataset.path(t).exists() and dataset.stored(t) == t]
    found = [(t, r) for t in types for r in dataset.records(t)]
    return found + [('agenda-cards', r) for r in dataset.records('agenda-cards') if r.get('mission')]


def cache_key(dataset, content_type, record):
    """UUIDs (data 2.0.0) are unique across collections; 1.x's numbers repeat in each, so they get their type."""
    return record['id'] if dataset.uses_uuids(content_type) else f"{content_type}:{record['id']}"


def query(client, titles):
    """{requested title: {"title", "wikitext", "revid"} or None} for up to BATCH titles, following redirects."""
    answer = client.get(API_URL, params={
        'action': 'query', 'prop': 'revisions', 'rvprop': 'content|ids', 'rvslots': 'main', 'redirects': 1,
        'format': 'json', 'formatversion': 2, 'titles': '|'.join(titles)}).json()['query']
    renamed = {n['from']: n['to'] for n in answer.get('normalized', []) + answer.get('redirects', [])}
    pages = {p['title']: p for p in answer['pages'] if 'revisions' in p}
    found = {}
    for title in titles:
        final = title
        while final in renamed:
            final = renamed[final]
        page = pages.get(final)
        found[title] = page and {'title': page['title'], 'revid': page['revisions'][0]['revid'],
                                 'wikitext': page['revisions'][0]['slots']['main']['content']}
    return found


def category_members(client, name):
    answer = client.get(API_URL, params={'action': 'query', 'list': 'categorymembers', 'cmtitle': f'Category:{name}',
                                         'cmlimit': 500, 'format': 'json', 'formatversion': 2}).json()
    return [m['title'] for m in answer['query']['categorymembers'] if m['ns'] == 0]


def fetch_pages(client, out, prefix, wanted, accept, refresh, log):
    """{key: page} for wanted = {key: [titles to try, in order]}: the first title whose page accept()s. Pages are cached
    in out/pages/<prefix>-<slug>.json (a missing page too, so it isn't asked for again)."""
    pages = {}
    for attempt in range(max(map(len, wanted.values()), default=0)):
        to_fetch = []
        for key, titles in wanted.items():
            if key in pages or attempt >= len(titles):
                continue
            path = out / 'pages' / f'{prefix}-{slugify(titles[attempt])}.json'
            if path.exists() and not refresh:
                page = json.loads(path.read_text(encoding='utf-8'))
                if accept(page):
                    pages[key] = page
            else:
                to_fetch.append((key, titles[attempt], path))
        for i in range(0, len(to_fetch), BATCH):
            batch = to_fetch[i:i + BATCH]
            answers = query(client, [title for _, title, _ in batch])
            for key, title, path in batch:
                page = answers[title] or {'title': None, 'wikitext': None, 'revid': None}
                path.write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding='utf-8')
                if accept(page):
                    pages[key] = page
            log(f'fetched {len(batch)} {prefix} pages')
    return pages


def hero_missions(client, dataset, out, refresh, log):
    """{normalised mission name: hero record}, from each hero's page."""
    wanted = {h['id']: [f"{h['name']} (Hero)", h['name']] for h in dataset.records('heroes')}
    pages = fetch_pages(client, out, 'hero', wanted, lambda p: infobox(p['wikitext'], HERO_INFOBOX) is not None,
                        refresh, log)
    heroes = {h['id']: h for h in dataset.records('heroes')}
    found = {}
    for hero_id, page in pages.items():
        field = infobox(page['wikitext'], HERO_INFOBOX).get('mission', '')
        mission = LINK.sub(lambda m: m.group(2) or m.group(1), field)
        if mission.strip():
            found[normalise(mission)] = heroes[hero_id]
    return found


def run(client, dataset, root=None, refresh=False, log=print):
    out = (root or settings.STAGING) / 'wiki'
    (out / 'pages').mkdir(parents=True, exist_ok=True)
    missions = mission_records(dataset)
    # Each name's titles to try, in order: the name (or its fixed spelling), then the disambiguated forms.
    wanted = {r['name']: [TITLES.get(r['name'], r['name'])] + [TITLES.get(r['name'], r['name']) + d
                                                              for d in DISAMBIGUATIONS] for _, r in missions}
    pages = fetch_pages(client, out, 'mission', wanted, lambda p: infobox(p['wikitext']) is not None, refresh, log)
    by_mission = hero_missions(client, dataset, out, refresh, log)

    index, categories, result = RewardIndex(dataset), {}, {}
    for content_type, record in missions:
        page = pages.get(record['name'])
        fields = infobox(page['wikitext']) if page else None
        entry = {'content_type': content_type, 'name': record['name'], 'page': page and page['title'],
                 'revid': page and page['revid'], 'hero': None, 'reward': None, 'rewards': [], 'problems': []}
        result[cache_key(dataset, content_type, record)] = entry
        if fields is None:
            entry['problems'].append('no wiki page with a mission infobox')
            continue
        entry['hero'] = index.hero(fields.get('hero'))
        title = TITLES.get(record['name'], record['name'])
        hero = by_mission.get(normalise(page['title'])) or by_mission.get(normalise(title))
        if hero and entry['hero'] is None:
            entry['hero'] = {'text': hero['name'], 'id': hero['id']}
        elif hero and entry['hero']['id'] != hero['id']:
            entry['problems'].append(
                f"the mission names hero {entry['hero']['text']!r}, but {hero['name']}'s page names it")
        if entry['hero'] and entry['hero']['id'] is None:
            entry['problems'].append(f"hero {entry['hero']['text']!r} not in the dataset")
        entry['reward'] = {f: fields[f] for f in REWARD_FIELDS if fields.get(f)} or None
        for field, value in (entry['reward'] or {}).items():
            for category in ANY_OF.findall(value):
                if category not in categories:
                    categories[category] = category_members(client, category)
            rows, problems = rewards(value, index, categories)
            entry['rewards'] += [r | {'field': field} for r in rows]
            entry['problems'] += [f'{field}: {p}' for p in problems]
        if entry['reward'] is None:
            entry['problems'].append('the page gives no reward')
    cache = {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'api': API_URL,
             'categories': categories, 'missions': result}
    (out / 'missions.json').write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding='utf-8')
    return cache
