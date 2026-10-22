"""What the data-entry app needs, independent of HTTP: form specs from the data repo's schemas, suggested entries for
each staged image, and validation of one entry at a time."""

import jsonschema

from ia_tools import importer
from ia_tools.dataset import BACK_ID, BACK_KEYS, FOREIGN_KEYS, INDEX_TYPES
from ia_tools.iaspec import iaspec_for
from ia_tools.match import normalise, parse_deployment_name

def entry_types(dataset):
    """Types a staged image can become, in the checkout's data: not the indexes and join tables, which are never
    entered by hand, nor sources, which is the product panel."""
    return dataset.content_types(exclude=INDEX_TYPES + ['sources'])


# Types entered without an image of their own (miniatures: data 2.0.0).
EXTRA_TYPES = ['agenda-decks', 'imperial-classes', 'miniatures']
# Data 2.0.0: cards that agree on this field share a back (other types: all their cards share one), for suggesting a
# new card's back_id.
SAME_BACK = {'deployment-cards': 'affiliation', 'upgrade-cards': 'tier'} | {
    child: fk for (child, fk) in FOREIGN_KEYS if child in BACK_KEYS}
# The album hint naming a back's parent ("Rebel Hero: <hero>").
PARENT_HINTS = {'heroes': 'hero', 'imperial-classes': 'class', 'agenda-decks': 'deck'}


def field_spec(content_type, name, prop, required):
    spec = {'name': name, 'description': prop.get('description', ''), 'required': name in required, 'nullable': False}
    if 'oneOf' in prop:
        options = [o for o in prop['oneOf'] if o.get('type') != 'null']
        spec['nullable'] = len(options) < len(prop['oneOf'])
        prop = options[0]
    if (content_type, name) in FOREIGN_KEYS:
        return spec | {'kind': 'fk', 'parent': FOREIGN_KEYS[content_type, name]}
    if name == BACK_ID:
        return spec | {'kind': 'fk', 'parent': 'card-backs'}
    if 'enum' in prop:
        return spec | {'kind': 'select', 'options': prop['enum']}
    kind = prop.get('type')
    if kind == 'array':
        options = prop.get('items', {}).get('enum')
        return spec | ({'kind': 'multi', 'options': options} if options else {'kind': 'list'})
    if kind == 'integer':
        return spec | {'kind': 'integer', 'minimum': prop.get('minimum')}
    if kind == 'boolean':
        return spec | {'kind': 'boolean'}
    return spec | {'kind': 'text'}


def forms(dataset):
    """content type → {'fields': [...], 'images': [...]} for every type the app can create."""
    result = {}
    for content_type in entry_types(dataset) + ['sources']:
        schema = dataset.schema(content_type)
        images = importer.image_fields(dataset, content_type)
        result[content_type] = {
            'fields': [field_spec(content_type, name, prop, schema.get('required', []))
                       for name, prop in schema['properties'].items() if name != 'id' and name not in images],
            'images': images,
        }
    return result


def record_label(record):
    """How a picker shows a record: its name (and subtitle), or for card backs, which have none, deck and variant."""
    if 'name' not in record:
        return ': '.join(str(v) for v in (record.get('deck'), record.get('variant')) if v)
    return record['name'] + (f" ({record['description']})" if record.get('description') else '')


def records_index(dataset):
    """content type → [{'id', 'name'}] for link and foreign-key pickers. Missions (data 2.0.0's index, a foreign key
    of epilogue cards) are named by their mission cards."""
    index = {
        t: [{'id': r['id'], 'name': record_label(r)} for r in dataset.records(t)]
        for t in entry_types(dataset) + ['sources'] if dataset.has_ids(t)
    }
    if dataset.path('missions').exists():
        cards = {(t, r['id']): r for t in {m['content_type'] for m in dataset.records('missions')}
                 for r in dataset.records(t)}
        index['missions'] = [{'id': m['id'], 'name': f"{cards[m['content_type'], m['content_id']]['name']} "
                                                     f"({m['content_type'].removesuffix('-cards')})"}
                             for m in dataset.records('missions')]
    return index


def existing_back(dataset, back_type):
    """A sample existing card back for a back type (Dataset.back_type): deck name to reuse, variant style to follow."""
    backs = dataset.records('card-backs')
    if backs and 'content_type' in backs[0]:  # 1.x
        return next((b for b in backs if b['content_type'] == back_type), None)
    for content_type in [t for t, key in BACK_KEYS.items() if key == back_type] or [back_type]:
        card = next(iter(dataset.records(content_type)), None) if dataset.path(content_type).exists() else None
        if card:
            return next((b for b in backs if b['id'] == card[BACK_ID]), None)
    return None


def suggest_back(content_type, record, item, manifest, dataset):
    """Data 2.0.0: the back a new card most likely has. The one its existing siblings share (SAME_BACK), or else the
    one back staged for its type (for a new hero or class, the one with the same album hint)."""
    field = SAME_BACK.get(content_type)
    if field is None or record.get(field) is not None:
        same = {r[BACK_ID] for r in dataset.records(content_type) if field is None or r.get(field) == record.get(field)}
        if len(same) == 1:
            return same.pop()
    back_type = BACK_KEYS.get(content_type, content_type)
    hint = PARENT_HINTS.get(back_type)
    own = normalise(item['guess'].get('hints', {}).get(hint) or '') if hint else ''
    staged = [i for i in manifest['items'] if i['guess'].get('content_type') == 'card-backs'
              and i['guess'].get('back_content_type') == back_type
              and (not hint or normalise(i['guess'].get('hints', {}).get(hint) or '') == own)]
    return f"@{staged[0]['key']}" if len(staged) == 1 else None


def deployment_fields(item, manifest):
    """name, elite, unique and modes for a staged deployment card, from its image name and the rest of its album."""
    name, grade, modes = parse_deployment_name(item['name'])
    siblings = [parse_deployment_name(i['name']) for i in manifest['items']
                if i['path'] == item['path'] and i['key'] != item['key']]
    graded = bool(grade) or any(g and normalise(n) == normalise(name) for n, g, _ in siblings)
    if graded and name.endswith('s'):
        name = name[:-1]  # boardwars pluralises units that come in regular and elite ("Elite Snowtroopers")
    heroes = {normalise(i['guess'].get('hints', {}).get('hero', '')) for i in manifest['items']
              if i['guess']['content_type'] == 'heroes'}
    fields = {'name': name}
    if normalise(name) in heroes:
        fields |= {'elite': False, 'unique': True, 'modes': ['Skirmish']}  # a hero's skirmish card
    elif graded:
        fields |= {'elite': grade == 'elite', 'unique': False}
    elif modes:
        fields |= {'elite': True, 'unique': True}  # a named figure printed twice, for campaign and skirmish
    if modes:
        fields['modes'] = modes
    return fields


def staged_iaspec_records(item, manifest, dataset, entries):
    """Every record an iaspec must not clash with: the dataset's, the saved entries' and the other suggestions'."""
    records = [r for t in importer.IASPEC_TYPES for r in dataset.records(t)]
    for key, entry in entries.get('items', {}).items():
        if key != item['key'] and entry.get('action') == 'new' and entry.get('content_type') in importer.IASPEC_TYPES:
            records.append(entry.get('record', {}))
    for other in manifest['items']:
        if other['key'] != item['key'] and other['key'] not in entries.get('items', {}) and not other['matches']:
            if other['guess']['content_type'] == 'deployment-cards':
                records.append(deployment_fields(other, manifest) | affiliation_hint(other, dataset))
            elif other['guess']['content_type'] in importer.IASPEC_TYPES:
                records.append({'name': other['name']})
    return records


def affiliation_hint(item, dataset):
    hint = item['guess'].get('hints', {}).get('affiliation')
    if not hint:
        return {}
    options = dataset.schema('definitions')['definitions']['affiliation']['enum']
    return {'affiliation': next((a for a in options if hint.lower().startswith(a.lower()[:5])), None)}


def suggest(item, manifest, dataset, entries):
    """A starting entry for a staged image, from the scrape's guess and the dataset."""
    guess = item['guess']
    content_type = guess['content_type']
    hints = guess.get('hints', {})
    name_lower = item['name'].lower()

    source = own_source(item, manifest)
    if len(item['matches']) == 1:  # several: the app lists them and the user picks, rather than a guess
        match = item['matches'][0]
        return {'action': 'link', 'content_type': match['content_type'], 'id': match['id']} | source
    if content_type == 'sources':
        return {'action': 'skip', 'note': 'product image: use it in the product panel'}
    if content_type == 'heroes' and name_lower.endswith('wounded'):
        partner = next((i for i in manifest['items'] if i['path'] == item['path']
                        and i['name'].lower().endswith('healthy')), None)
        if partner:
            return {'action': 'attach', 'to': partner['key'], 'field': 'wounded'}

    record = {}
    if content_type and content_type not in ('card-backs',):
        record['name'] = item['name']
    if content_type == 'heroes':
        record['name'] = item['name'].rsplit(' ', 1)[0] if name_lower.endswith(('healthy', 'wounded')) else item['name']
    if content_type == 'deployment-cards':
        record |= deployment_fields(item, manifest) | affiliation_hint(item, dataset)
    if content_type == 'upgrade-cards' and 'tier' in hints:
        record['tier'] = hints['tier']
    if content_type in importer.IASPEC_TYPES:
        record['iaspec'] = iaspec_for(record, staged_iaspec_records(item, manifest, dataset, entries))
    if content_type == 'card-backs':
        back_type = guess.get('back_content_type')
        sample = existing_back(dataset, back_type) if back_type else None
        hint = hints.get({'heroes': 'hero', 'imperial-classes': 'class'}.get(back_type))
        if hint:  # these backs are named after the hero or class
            parent = next((r for r in dataset.records(back_type) if normalise(r['name']) == normalise(hint)), None)
            hint = parent['name'] if parent else hint
        if 'name' in dataset.schema('card-backs')['properties']:  # 2.0.0: "Rebel Hero: <hero>"
            deck = sample['name'].split(': ')[0] if sample else ''
            record = {'name': f'{deck}: {hint}' if deck and hint else deck or hint or ''}
        else:
            record = {'deck': sample['deck'] if sample else '', 'content_type': back_type, 'variant': hint}
    for (child, fk), parent in FOREIGN_KEYS.items():
        hint = PARENT_HINTS.get(parent)  # album hints
        if content_type == child and hint and hints.get(hint):
            record[fk] = find_parent(parent, hints[hint], dataset, entries, manifest)
    if content_type and dataset.has_backs(content_type):
        back = suggest_back(content_type, record, item, manifest, dataset)
        if back:
            record[BACK_ID] = back
    return {'action': 'new', 'content_type': content_type, 'record': record} | source


def own_source(item, manifest):
    """{'source_id': ...} when the scrape placed the image in an existing product other than the folder's."""
    source = item.get('source')
    if not source or any(p['id'] == source['id'] for p in manifest.get('existing_product', [])):
        return {}
    return {'source_id': source['id']}


def find_parent(parent_type, name, dataset, entries, manifest):
    """Existing parent id, or '@key' of a staged one, by name."""
    key = normalise(name)
    for record in dataset.records(parent_type):
        if normalise(record['name']) == key:
            return record['id']
    staged = list(entries.get('items', {}).items()) + list(entries.get('extra', {}).items())
    for entry_key, entry in staged:
        if entry.get('content_type') == parent_type and normalise(entry.get('record', {}).get('name', '')) == key:
            return f'@{entry_key}'
    return None


def normalise_entry(entry, dataset):
    """Text loses leading and trailing spaces ("Piece By Piece "); empty lists in nullable list fields become null,
    since those lists need at least one item (e.g. traits)."""
    if entry.get('action') != 'new' or entry.get('content_type') not in entry_types(dataset) + ['sources']:
        return entry
    properties = dataset.schema(entry['content_type']).get('properties', {})
    record = entry.get('record', {})
    for name, value in record.items():
        options = properties.get(name, {}).get('oneOf', [])
        if isinstance(value, str):
            record[name] = value.strip()
        elif value == [] and any(o.get('type') == 'null' for o in options):
            record[name] = None
    return entry


def check_entry(entry, dataset):
    """Problems with one entry's record, judged against its schema (ids, images and staged keys filled in)."""
    if entry.get('action') != 'new':
        return []
    content_type = entry.get('content_type')
    if content_type not in entry_types(dataset) + ['sources']:
        return [f'Unknown content type {content_type!r}']
    record = dict(entry.get('record', {}))
    if dataset.has_ids(content_type):
        record['id'] = dataset.placeholder_id(content_type)
    for image_field in importer.image_fields(dataset, content_type):
        record[image_field] = f'{content_type}/placeholder.png'
    for (child, fk), parent in FOREIGN_KEYS.items():
        if content_type == child and isinstance(record.get(fk), str) and record[fk].startswith('@'):
            record[fk] = dataset.placeholder_id(parent)
    if isinstance(record.get(BACK_ID), str) and record[BACK_ID].startswith('@'):
        record[BACK_ID] = dataset.placeholder_id('card-backs')
    problems = []
    for error in jsonschema.Draft4Validator(dataset.schema(content_type)).iter_errors(record):
        where = '.'.join(str(x) for x in error.absolute_path) or 'record'
        problems.append(f'{where}: {error.message}')
    return problems
