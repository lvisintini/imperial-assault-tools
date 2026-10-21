"""Changes to existing records (a rename, a fixed field), proposed with ia propose and decided in ia enter.

A staging folder's manifest.json lists the proposals:
    "edits": [{"key": "e1", "content_type": "sources", "id": 5, "changes": {"name": "IG-88"}, "note": "..."}]
and entries.json the user's decisions:
    "edits": {"e1": {"action": "apply", "changes": {"name": "IG-88"}, "rename_images": true}}   # or {"action": "skip"}

The user can change the values before applying them. With rename_images, image files follow the record's new name
(the importer's slug rules), so "IG88" → "IG-88" moves sources/ig88.png to sources/ig-88.png."""
import json

import jsonschema

from ia_tools import importer
from ia_tools.dataset import FOREIGN_KEYS
from ia_tools.staging import Staging


def propose(dataset, folder, content_type, record_id, changes, note=None, root=None):
    """Add a proposal to staging/<folder>/ (created if needed). Returns its key."""
    if not dataset.has_ids(content_type):
        raise ValueError(f'{content_type} records have no id to point at')
    record = find(dataset, content_type, record_id)
    if record is None:
        raise ValueError(f'No {content_type} record with id {record_id}')
    unknown = set(changes) - set(dataset.schema(content_type)['properties'])
    if unknown:
        raise ValueError(f'{content_type} has no field {", ".join(sorted(unknown))}')
    staging = Staging(folder, root)
    staging.dir.mkdir(parents=True, exist_ok=True)
    manifest = staging.manifest() if staging.manifest_path.exists() else {
        'product': None, 'urls': [], 'existing_product': [], 'items': []}
    proposals = manifest.setdefault('edits', [])
    n = 1
    while any(e['key'] == f'e{n}' for e in proposals):
        n += 1
    proposals.append({'key': f'e{n}', 'content_type': content_type, 'id': record_id, 'changes': changes, 'note': note})
    staging.manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return f'e{n}'


def find(dataset, content_type, record_id):
    return next((r for r in dataset.records(content_type) if r.get('id') == record_id), None)


def parent_name(dataset, content_type, record):
    for (child, fk), parent in FOREIGN_KEYS.items():
        if content_type == child:
            return next((r['name'] for r in dataset.records(parent) if r['id'] == record.get(fk)), None)
    return None


def preview(dataset, proposal, decision, taken=()):
    """What applying a decision would do: (the record afterwards, {field: (old path, new path)}, problems). taken: image
    paths other changes in the same import already claim."""
    record = find(dataset, proposal['content_type'], proposal['id'])
    if record is None:
        return None, {}, [f"{proposal['key']}: no {proposal['content_type']} record with id {proposal['id']}"]
    content_type = proposal['content_type']
    after = record | decision.get('changes', proposal['changes'])
    problems = []
    moves = {}
    if decision.get('rename_images'):
        for field in importer.image_fields(dataset, content_type):
            if not record.get(field):
                continue
            slug = importer.image_slug(content_type, after, field, parent_name(dataset, content_type, after))
            new = f'{dataset.stored(content_type)}/{slug}.png'
            if new == record[field]:
                continue
            if new in taken or any(dataset.image_path(size, new).exists() for size in ('large', 'small')):
                problems.append(f"{proposal['key']}: image {new} already exists")
            moves[field] = (record[field], new)
            after[field] = new
    old_name, new_name = record.get('name'), after.get('name')
    if old_name != new_name and any(b['variant'] == old_name for b in dataset.records('card-backs')):
        # Some backs match on a record's name, or (story and threat missions) its product's name: docs/data-model.md.
        problems.append(f"{proposal['key']}: a card back's variant is {old_name!r}; rename it in card-backs.json too")
    for error in jsonschema.Draft4Validator(dataset.schema(content_type)).iter_errors(after):
        where = '.'.join(str(x) for x in error.absolute_path) or '(record)'
        problems.append(f"{proposal['key']} ({content_type} #{proposal['id']}) {where}: {error.message}")
    return after, moves, problems


def plan(staging, dataset, taken):
    """Every edit the user chose to apply: [(proposal, record afterwards, image moves)] and the problems found."""
    decisions = staging.entries().get('edits', {})
    planned, problems = [], []
    for proposal in staging.manifest().get('edits', []):
        decision = decisions.get(proposal['key'])
        if not decision or decision.get('action') != 'apply':
            continue
        after, moves, found = preview(dataset, proposal, decision, taken)
        problems += found
        taken |= {new for _, new in moves.values()}
        if after is not None:
            planned.append((proposal, after, moves))
    return planned, problems


def apply(planned, dataset):
    """Write the edits: records in place (keeping their field order) and image files moved."""
    for proposal, after, moves in planned:
        record = find(dataset, proposal['content_type'], proposal['id'])
        for field, value in after.items():
            record[field] = value
        for old, new in moves.values():
            for size in ('large', 'small'):
                target = dataset.image_path(size, new)
                target.parent.mkdir(parents=True, exist_ok=True)
                dataset.image_path(size, old).rename(target)
    return {p['content_type'] for p, _, _ in planned}
