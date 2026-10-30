"""Card types (data 2.0.0): which reward and Imperial class cards are a Group Attachment, proposed from the wiki's card
text and confirmed by the maintainer in ia enter (its Card types page). ia card-types writes them to the data repo.

A Group Attachment is attached to an Imperial deployment group ("Attach this card to a deployment card"); every other
card that isn't an item stays a Feat. Imperial class cards had no type and get one; reward Feats can become Group
Attachments. Hero class and upgrade cards, and reward items, keep their type and aren't shown.

The wiki's pages are cached in staging/wiki/pages/card-<slug>.json (ia card-types --fetch). Entries are saved to
staging/card-types/entries.json:
    {"cards": {"<card id>": {"type": "Group Attachment", "done": true, "note": "..."}}}
ia card-types writes only when every card is done."""
import difflib
import hashlib
import json
import re

from ia_tools import settings
from ia_tools.dataset import dumps
from ia_tools.staging import slugify
from ia_tools.wiki import API_URL
from ia_tools.wiki_missions import BATCH, category_members, query

GEAR = ['Armor', 'Equipment', 'Melee Weapon', 'Melee Weapon Modification', 'Ranged Weapon',
        'Ranged Weapon Modification']
FEAT = 'Feat'
ATTACHMENT = 'Group Attachment'
# The types a card shown here can be given: its collection's cards that aren't items.
COLLECTIONS = {
    'reward-cards': [FEAT, ATTACHMENT],
    'imperial-class-cards': [FEAT, ATTACHMENT],
}

ICON = re.compile(r'\{\{\s*([A-Za-z]+)\s*\}\}')
LINE_FIELD = re.compile(r'^(?:effect|ability)(\d*)$')
# The wiki's categories of class, reward and item cards: their titles are matched to cards whose name the wiki
# spells differently (Smugglers Luck, "Smuggler's Luck").
CATEGORIES = ['Hero Class Card', 'Hero Class Item', 'Hero Class Reward', 'Imperial Class Card', 'Imperial Class Reward',
              'Reward Card', 'Item Reward', 'Tier 1', 'Tier 2', 'Tier 3', 'Armor', 'Equipment']
ATTACH = re.compile(r'\battach(?:ed)?\b|\bthis group\b', re.I)


def candidates(content_type, record, hero):
    """Wiki titles to try for a card, most specific first."""
    name = record['name']
    titles = {
        'reward-cards': [f'{name} (Reward Card)', name, f'{name} (Reward)'],
        'imperial-class-cards': [f'{name} (Imperial Class Card)', name],
    }[content_type]
    return [t for t in dict.fromkeys(titles) if t]


def infobox(wikitext):
    """(template name, {field: value}) of the page's first template, split on its top-level pipes."""
    start = (wikitext or '').find('{{')
    if start < 0:
        return None, {}
    depth, i, parts, current = 0, start, [], []
    while i < len(wikitext):
        pair = wikitext[i:i + 2]
        if pair in ('{{', '[['):
            depth += 1
            current.append(pair)
            i += 2
            continue
        if pair in ('}}', ']]'):
            depth -= 1
            if depth == 0:
                parts.append(''.join(current))
                break
            current.append(pair)
            i += 2
            continue
        if wikitext[i] == '|' and depth == 1:
            parts.append(''.join(current))
            current = []
        else:
            current.append(wikitext[i])
        i += 1
    name, fields = parts[0].lstrip('{').strip() if parts else None, {}
    for part in parts[1:]:
        if '=' in part:
            key, value = part.split('=', 1)
            fields[key.strip().lower()] = value.strip()
    return name, fields


def ability_lines(fields):
    """The card's ability lines, in order, with icons as <A>, <Z>, ... and links and bold marks dropped."""
    numbered = sorted((int(m.group(1) or 0), key) for key in fields if (m := LINE_FIELD.match(key)))
    lines = []
    for _, key in numbered:
        text = ICON.sub(lambda m: f'<{m.group(1).upper()}>', fields[key])
        text = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', text).replace("'''", '').replace("''", '')
        if text.strip():
            lines.append(' '.join(text.split()))
    return lines


def type_of(content_type, record, fields):
    """The type proposed for a card: Group Attachment where the wiki's type is Attachment, or (an Imperial reward card)
    its text attaches it to a group; Feat otherwise."""
    if fields.get('type', '').lower() == 'attachment':
        return ATTACHMENT
    if content_type == 'reward-cards' and record.get('for') == 'Imperial player' and ATTACH.search(' '.join(fields.values())):
        return ATTACHMENT
    return FEAT


def records(dataset):
    """[(content type, record)] for every card classified here: the collections' cards that aren't items."""
    return [(content_type, r) for content_type in COLLECTIONS for r in dataset.records(content_type)
            if r.get('type') in (None, FEAT, ATTACHMENT)]


def accepts(page, hero):
    """Whether a wiki page is the card's: it has an infobox, and a hero class card's names the card's hero."""
    template, fields = infobox(page.get('wikitext'))
    if not template or 'infobox' not in template.lower().replace(' ', '').replace('_', ''):
        return False
    named = fields.get('hero')
    return not (named and hero and re.sub(r'\W', '', named).lower() != re.sub(r'\W', '', hero).lower())


def fetch(client, dataset, refresh=False, log=print):
    """{card id: page} for the cards whose page the wiki has: each card's candidate titles are tried in order, BATCH
    titles a request. Pages are cached in staging/wiki/pages/card-<slug>.json (a missing page too); with no client,
    only the cache is read."""
    heroes = {h['id']: h['name'] for h in dataset.records('heroes')}
    wanted = {r['id']: (candidates(t, r, heroes.get(r.get('hero_id'))), heroes.get(r.get('hero_id')))
              for t, r in records(dataset)}
    names = {r['id']: r['name'] for _, r in records(dataset)}
    out = settings.STAGING / 'wiki' / 'pages'
    out.mkdir(parents=True, exist_ok=True)
    pages = fetch_titles(client, out, wanted, refresh, log)
    missing = {card_id: wanted[card_id] for card_id in wanted if card_id not in pages}
    if missing:
        titles = category_titles(client, refresh)
        alike = {}
        for card_id, (tried, hero) in missing.items():
            found = [t for t in titles if loose(t) == loose(names[card_id]) and t not in tried]
            if found:
                alike[card_id] = (found, hero)
        pages |= fetch_titles(client, out, alike, refresh, log)
    searched = {}
    for card_id, (tried, hero) in wanted.items():
        if card_id not in pages:
            hits = [t for t in search(client, names[card_id], refresh) if alike_names(t, names[card_id])]
            if hits:
                searched[card_id] = (hits, hero)
    pages |= fetch_titles(client, out, searched, refresh, log)
    log(f'{len(pages)} of {len(wanted)} cards have a wiki page')
    return pages


def loose(title):
    """A title or name without its disambiguation, case, spaces and punctuation."""
    return re.sub(r'[^a-z0-9]', '', re.sub(r'\s*\([^)]*\)\s*$', '', title).lower())


def alike_names(title, name):
    return difflib.SequenceMatcher(None, loose(title), loose(name)).ratio() >= 0.85


def search(client, name, refresh=False):
    """The wiki search's first titles for a name, cached in staging/wiki/card-search.json."""
    path = settings.STAGING / 'wiki' / 'card-search.json'
    cache = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if name in cache and not refresh or not client:
        return cache.get(name, [])
    answer = client.get(API_URL, params={'action': 'query', 'list': 'search', 'srsearch': name, 'srlimit': 3,
                                         'format': 'json', 'formatversion': 2}).json()
    cache[name] = [hit['title'] for hit in answer['query']['search']]
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding='utf-8')
    return cache[name]


def spelled(title):
    """A wiki title without its disambiguation, typographic apostrophes made straight."""
    return re.sub(r'\s*\([^)]*\)\s*$', '', title).replace('’', "'")


def category_titles(client, refresh=False):
    """Every page title in CATEGORIES, cached in staging/wiki/card-categories.json."""
    path = settings.STAGING / 'wiki' / 'card-categories.json'
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding='utf-8'))
    if not client:
        return []
    titles = sorted({t for name in CATEGORIES for t in category_members(client, name)})
    path.write_text(json.dumps(titles, indent=2, ensure_ascii=False), encoding='utf-8')
    return titles


def cache_path(out, title):
    """A title's cache file. Titles that differ only in case or punctuation ("Into The Fray", "Into the Fray") would
    share a slug, so the file name has a hash of the title too."""
    return out / f'card-{slugify(title)}-{hashlib.sha1(title.encode()).hexdigest()[:8]}.json'


def fetch_titles(client, out, wanted, refresh, log):
    """{card id: page} for wanted = {card id: ([titles], hero)}: the first title whose page accepts() the card."""
    pages = {}
    for attempt in range(max((len(titles) for titles, _ in wanted.values()), default=0)):
        to_fetch = []
        for card_id, (titles, hero) in wanted.items():
            if card_id in pages or attempt >= len(titles):
                continue
            path = cache_path(out, titles[attempt])
            if path.exists() and not refresh:
                page = json.loads(path.read_text(encoding='utf-8'))
                if accepts(page, hero):
                    pages[card_id] = page
            elif client:
                to_fetch.append((card_id, titles[attempt], path))
        for i in range(0, len(to_fetch), BATCH):
            batch = to_fetch[i:i + BATCH]
            answers = query(client, list(dict.fromkeys(title for _, title, _ in batch)))
            for card_id, title, path in batch:
                page = answers[title] or {'title': None, 'wikitext': None, 'revid': None}
                path.write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding='utf-8')
                if accepts(page, wanted[card_id][1]):
                    pages[card_id] = page
            log(f'fetched {len(batch)} card pages (attempt {attempt + 1})')
    return pages


def cached_pages(dataset):
    """{card id: page} from the cache alone (no requests)."""
    return fetch(None, dataset, log=lambda *_: None)


def proposals(dataset, pages=None):
    """{card id: {"type", "flags", "title", "lines"}}."""
    pages = cached_pages(dataset) if pages is None else pages
    found = {}
    for content_type, record in records(dataset):
        page = pages.get(record['id'])
        _, fields = infobox(page['wikitext']) if page else (None, {})
        lines = ability_lines(fields)
        name_flags = [f"The wiki spells it {spelled(page['title'])!r}"] if page and \
            spelled(page['title']) != record['name'] else []
        text_flags = [] if lines else ['No card text on the wiki']
        found[record['id']] = {'type': type_of(content_type, record, fields), 'flags': name_flags + text_flags,
                               'title': page and page['title'], 'lines': lines}
    return found


def entries_path():
    return settings.STAGING / 'card-types' / 'entries.json'


def load():
    path = entries_path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'cards': {}}


def save(entries):
    path = entries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')


def panel(dataset):
    """What the Card types page shows."""
    entries = load()['cards']
    found = proposals(dataset)
    heroes = {h['id']: h['name'] for h in dataset.records('heroes')}
    classes = {c['id']: c['name'] for c in dataset.records('imperial-classes')}
    cards = []
    for content_type, record in records(dataset):
        owner = heroes.get(record.get('hero_id')) or classes.get(record.get('class_id')) or record.get('for')
        cards.append({'id': record['id'], 'content_type': content_type, 'name': record['name'], 'image': record['image'],
                      'owner': owner, 'current': record.get('type'), 'proposal': found[record['id']]})
    return {'cards': cards, 'collections': COLLECTIONS, 'entries': entries,
            'problems': {card_id: check(entry, content_type_of(dataset, card_id)) for card_id, entry in entries.items()}}


def content_type_of(dataset, card_id):
    return next((t for t, r in records(dataset) if r['id'] == card_id), None)


def check(entry, content_type):
    """Problems with one card's entry."""
    if content_type is None:
        return ['Not a card classified here']
    if entry.get('type') not in COLLECTIONS[content_type]:
        return [f"Type {entry.get('type')!r} isn't one of {content_type}'s"]
    return []


def with_type(record, type_):
    """The record with its type set: in place where it has one, after xp (Imperial class cards) otherwise."""
    if 'type' in record:
        return record | {'type': type_}
    out = {}
    for key, value in record.items():
        out[key] = value
        if key == 'xp':
            out['type'] = type_
    return out if 'type' in out else out | {'type': type_}


def plan(dataset, entries=None):
    """({content type: records}, summary, problems): the files after writing the entries."""
    entries = (entries or load())['cards']
    known = {r['id']: t for t, r in records(dataset)}
    problems = [f'{card_id}: not a card classified here' for card_id in entries if card_id not in known]
    files, left = {}, 0
    for content_type in COLLECTIONS:
        files[content_type] = []
        for record in dataset.records(content_type):
            entry = entries.get(record['id'])
            if record['id'] not in known:  # an item: its type stays
                files[content_type].append(record)
                continue
            if not (entry and entry.get('done')):
                left += 1
                files[content_type].append(record)
                continue
            problems += [f"{content_type} {record['name']}: {p}" for p in check(entry, content_type)]
            files[content_type].append(with_type(record, entry['type']))
    if left:
        problems.append(f'{left} cards are not done yet')
    summary = {'cards': len(known), 'done': len(known) - left, 'left': left}
    return files, summary, problems


def run(dataset, check_only=False):
    """(summary, problems); writes the files unless checking or there are problems."""
    files, summary, problems = plan(dataset)
    if not problems and not check_only:
        for content_type, rows in files.items():
            dataset.path(content_type).write_text(dumps(rows), encoding='utf-8')
    return summary, problems
