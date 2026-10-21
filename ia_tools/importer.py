"""ia import: turn a product's entries.json into records, images and source-contents rows in the data repo.

Everything is checked first (schemas, ids, foreign keys, image paths, iaspecs unique and built by the rule); nothing is
written unless the whole product passes. Existing files are never overwritten."""
import json
from dataclasses import dataclass, field

import jsonschema

from ia_tools import edits, images, settings
from ia_tools.iaspec import iaspec_for
from ia_tools.dataset import FOREIGN_KEYS, MISSION_TYPES
from ia_tools.staging import slugify

# Types source-contents links to products (child cards come with their parent; see docs/data-model.md). Mission
# cards are linked through their missions row in data 2.0.0.
LINKED_TYPES = {
    'agenda-decks', 'command-cards', 'companion-cards', 'condition-cards', 'deployment-cards', 'form-cards', 'heroes',
    'imperial-classes', 'reward-cards', 'maps', 'supply-cards', 'upgrade-cards', *MISSION_TYPES,
}
IASPEC_TYPES = ('deployment-cards', 'command-cards', 'companion-cards')


class ImportProblems(Exception):
    def __init__(self, problems):
        super().__init__('\n'.join(problems))
        self.problems = problems


@dataclass
class Pending:
    key: str                    # item or extra key
    content_type: str
    record: dict
    images: dict = field(default_factory=dict)  # field → item key of the original
    file_overrides: dict = field(default_factory=dict)  # field → slug chosen in the app
    source_id: int | None = None  # the item's own product, when it isn't the folder's


def image_fields(dataset, content_type):
    pattern = dataset.schema('definitions')['definitions']['image-file-path']['pattern']
    return [name for name, prop in dataset.schema(content_type)['properties'].items() if prop.get('pattern') == pattern]


def image_slug(content_type, record, image_field, parent_name=None):
    name = record.get('name')
    if content_type == 'deployment-cards':
        parts = [name, record.get('description')]
        if record.get('elite') and not record.get('unique'):
            parts.append('elite')
        if len(record.get('modes', [])) == 1:
            parts.append(record['modes'][0])
    elif content_type in ('hero-class-cards', 'imperial-class-cards', 'agenda-cards'):
        parts = [parent_name, name]
    elif content_type == 'heroes':
        parts = [name, image_field]
    elif content_type == 'card-backs':
        parts = [record.get('deck'), record.get('variant')]
    else:
        parts = [name]
    return slugify(' '.join(str(p) for p in parts if p))


def missing_nullables(schema, record):
    """Required fields that may be null and are missing from a staged record, as null: what the entry form fills in
    for blank ones, for entries staged before the schema gained the field (sources.product_code)."""
    return {name: None for name in schema.get('required', [])
            if name not in record and any(o.get('type') == 'null' for o in schema['properties'][name].get('oneOf', []))}


def plan(staging, dataset):
    """Check entries.json and work out every change. Returns the plan; raises ImportProblems with all problems found."""
    problems = []
    entries, items = staging.entries(), staging.items()

    pending = []
    for key, entry in sorted(entries.get('items', {}).items()):
        if entry.get('action') == 'new':
            fields = image_fields(dataset, entry['content_type'])
            first = entry.get('field') or (fields[0] if fields else None)
            p = Pending(key, entry['content_type'], dict(entry['record']), {first: key} if first else {},
                        source_id=entry.get('source_id'))
            if first and entry.get('file'):
                p.file_overrides[first] = entry['file']
            pending.append(p)
    for key, extra in sorted(entries.get('extra', {}).items()):
        pending.append(Pending(key, extra['content_type'], dict(extra['record'])))
    by_key = {p.key: p for p in pending}
    for key, entry in entries.get('items', {}).items():
        if entry.get('action') == 'attach':
            target = by_key.get(entry.get('to'))
            if not target:
                problems.append(f'{key}: attached to {entry.get("to")!r}, which is not a new record')
            else:
                target.images[entry['field']] = key
                if entry.get('file'):
                    target.file_overrides[entry['field']] = entry['file']

    # The product itself. Items can name their own (a folder of gaps from many products has none).
    product = entries.get('product')
    source_id = None
    source_ids = {s['id'] for s in dataset.records('sources')}
    if not product:
        if any(entry.get('action') in ('new', 'link') and entry.get('content_type') in LINKED_TYPES
               and entry.get('source_id') is None for entry in entries.get('items', {}).values()):
            problems.append('No product chosen')
    elif product['action'] == 'existing':
        source_id = product['id']
        if source_id not in source_ids:
            problems.append(f'Product id {source_id} is not in sources.json')
    else:
        p = Pending('product', 'sources', dict(product['record']), {'image': product['item']} if product.get('item') else {})
        pending.insert(0, p)
        by_key['product'] = p
    for key, entry in entries.get('items', {}).items():
        if entry.get('source_id') is not None and entry['source_id'] not in source_ids:
            problems.append(f'{key}: product id {entry["source_id"]} is not in sources.json')

    # Ids: new UUIDs, or (1.x data) the numbers after the existing ones.
    new_ids = {}
    for p in pending:
        if dataset.has_ids(p.content_type):
            p.record['id'] = next(new_ids.setdefault(p.content_type, dataset.new_ids(p.content_type)))
    if source_id is None and 'product' in by_key:
        source_id = by_key['product'].record['id']

    # Foreign keys to staged records.
    for p in pending:
        for (child, fk), parent in FOREIGN_KEYS.items():
            value = p.record.get(fk) if p.content_type == child else None
            if isinstance(value, str) and value.startswith('@'):
                target = by_key.get(value[1:])
                if not target or target.content_type != parent:
                    problems.append(f'{p.key}: {fk} points at {value}, which is not a staged {parent} record')
                else:
                    p.record[fk] = target.record['id']

    # Image paths.
    planned_paths = set()
    for p in pending:
        parent_name = None
        for (child, fk), parent in FOREIGN_KEYS.items():
            if p.content_type == child and p.record.get(fk) is not None:
                parent_name = next((r.get('name') for r in dataset.records(parent) if r['id'] == p.record[fk]), None)
                parent_name = parent_name or next((q.record['name'] for q in pending
                                                   if q.content_type == parent and q.record.get('id') == p.record[fk]), None)
        for image_field in image_fields(dataset, p.content_type):
            if image_field not in p.images:
                problems.append(f'{p.key}: no image for {p.content_type}.{image_field}')
                continue
            slug = p.file_overrides.get(image_field) or image_slug(p.content_type, p.record, image_field, parent_name)
            relative = f'{dataset.stored(p.content_type)}/{slug}.png'
            if relative in planned_paths or any(dataset.image_path(s, relative).exists() for s in ('large', 'small')):
                problems.append(f'{p.key}: image {relative} already exists; choose another file name')
            planned_paths.add(relative)
            p.record[image_field] = relative

    # Schemas, plus the iaspec checks the data repo's tests enforce: unique, and built by the rule.
    iaspecs = {r['iaspec'] for t in IASPEC_TYPES for r in dataset.records(t)}
    iaspec_records = [r for t in IASPEC_TYPES for r in dataset.records(t)]
    iaspec_records += [p.record for p in pending if p.content_type in IASPEC_TYPES]
    for p in pending:
        p.record = missing_nullables(dataset.schema(p.content_type), p.record) | p.record
        p.record = {k: p.record[k] for k in dataset.key_order(p.content_type) if k in p.record} | p.record
        for error in jsonschema.Draft4Validator(dataset.schema(p.content_type)).iter_errors(p.record):
            where = '.'.join(str(x) for x in error.absolute_path) or '(record)'
            problems.append(f'{p.key} ({p.content_type}) {where}: {error.message}')
        if p.content_type in IASPEC_TYPES and p.record.get('iaspec'):
            if p.record['iaspec'] in iaspecs:
                problems.append(f'{p.key}: iaspec {p.record["iaspec"]!r} is already used')
            iaspecs.add(p.record['iaspec'])
            expected = iaspec_for(p.record, [r for r in iaspec_records if r is not p.record])
            if p.record['iaspec'] != expected:
                problems.append(f'{p.key}: iaspec {p.record["iaspec"]!r} doesn\'t follow the rule; expected {expected!r}')

    # source-contents rows: new records and "same as existing" links. In data 2.0.0 a mission card is linked through
    # its missions row (a new card gets one here), and so is an agenda card that is a mission (its deck's product).
    indexed = dataset.path('missions').exists()
    index = {m['content_id']: m['id'] for m in dataset.records('missions')} if indexed else {}
    index_ids, missions = dataset.new_ids('missions') if indexed else None, []

    def row(own_source, content_type, content_id):
        if indexed and content_type in MISSION_TYPES + ['agenda-cards']:
            if content_id not in index:
                missions.append({'id': next(index_ids), 'content_type': content_type, 'content_id': content_id,
                                 'map_id': None})
                index[content_id] = missions[-1]['id']
            content_type, content_id = 'missions', index[content_id]
        return {'source_id': source_id if own_source is None else own_source,
                'content_type': dataset.stored(content_type), 'content_id': content_id}

    rows = [row(p.source_id, p.content_type, p.record['id']) for p in pending if p.content_type in LINKED_TYPES
            or (indexed and p.content_type == 'agenda-cards' and p.record.get('mission'))]
    rows += [row(entry.get('source_id'), entry['content_type'], entry['id'])
             for key, entry in sorted(entries.get('items', {}).items())
             if entry.get('action') == 'link' and entry.get('content_type') in LINKED_TYPES]
    rows = [r for r in rows if r['source_id'] is not None]  # only with problems: no product chosen
    existing = {(r['source_id'], r['content_type'], r['content_id']) for r in dataset.records('source-contents')}
    rows = [r for r in rows if (r['source_id'], r['content_type'], r['content_id']) not in existing]

    # Changes to existing records (ia propose).
    planned_edits, edit_problems = edits.plan(staging, dataset, set(planned_paths))
    problems += edit_problems

    if problems:
        raise ImportProblems(problems)

    handled = [k for k, e in entries.get('items', {}).items() if e.get('action') in ('new', 'attach', 'link')]
    if (entries.get('product') or {}).get('item'):
        handled.append(entries['product']['item'])
    return {
        'pending': pending, 'rows': rows, 'missions': missions, 'items': items, 'edits': planned_edits,
        'seen_hashes': sorted({items[k]['sha512'] for k in handled if k in items}),
        'skipped_hashes': sorted({items[k]['sha512'] for k, e in entries.get('items', {}).items()
                                  if e.get('action') == 'known-skip' and k in items}),
    }


def summary(plan_):
    counts = {}
    for p in plan_['pending']:
        counts[p.content_type] = counts.get(p.content_type, 0) + 1
    return {'new_records': counts, 'source_contents_rows': len(plan_['rows']),
            'missions_rows': len(plan_.get('missions', [])), 'edits': len(plan_.get('edits', []))}


def apply(plan_, staging, dataset):
    items, upscaled, alignments = plan_["items"], {}, {}
    for p in plan_['pending']:
        for image_field, item_key in p.images.items():
            back_type = p.record.get('content_type') if p.content_type == 'card-backs' else None
            out = images.process(staging.dir / items[item_key]['file'], p.content_type, back_type, image_field)
            for size in ('large', 'small'):
                path = dataset.image_path(size, p.record[image_field])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(out[size])
            upscaled[p.key] = out['upscaled']
            alignments[item_key] = out['alignment']
        dataset.records(p.content_type).append(p.record)
    dataset.records('source-contents').extend(plan_['rows'])
    if plan_.get('missions'):
        dataset.records('missions').extend(plan_['missions'])
    edited = edits.apply(plan_['edits'], dataset)
    for content_type in ({p.content_type for p in plan_['pending']} | ({'source-contents'} if plan_['rows'] else set())
                         | ({'missions'} if plan_.get('missions') else set()) | edited):
        dataset.save(content_type)

    for path, hashes in ((settings.SEEN_HASHES, plan_['seen_hashes']), (settings.SKIPPED_HASHES, plan_['skipped_hashes'])):
        known = set(path.read_text().split()) if path.exists() else set()
        new = [h for h in hashes if h not in known]
        if new:
            text = path.read_text() if path.exists() else ''
            path.write_text(text + ('' if not text or text.endswith('\n') else '\n') + '\n'.join(new) + '\n')

    log = {'summary': summary(plan_), 'upscaled': [k for k, up in upscaled.items() if up],
           # staged item → the template it was aligned to; None: left unaligned (check it by eye).
           'alignment': alignments,
           'records': [{'key': p.key, 'content_type': p.content_type, 'record': p.record} for p in plan_['pending']],
           'source_contents': plan_['rows'],
           'edits': [{'key': p['key'], 'content_type': p['content_type'], 'id': p['id'], 'record': after,
                      'images': {f: list(m) for f, m in moves.items()}} for p, after, moves in plan_['edits']]}
    (staging.dir / 'import-log.json').write_text(json.dumps(log, indent=2), encoding='utf-8')
    return log
