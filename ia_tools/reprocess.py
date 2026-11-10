"""Re-make an imported product's images in place with the current image pipeline (ia reprocess).

For products imported before a pipeline change (alignment, rounded corners). The records stay as they are: the import
log says which records were written and where their images went, and entries.json which staged original each image
came from. Only files the import wrote are touched, and only for types the pipeline now changes (product images keep
theirs), so no TinyPNG compressions are spent on images that would come out the same."""
import json
import uuid

from ia_tools import align, images, importer
from ia_tools.dataset import INDEX_TYPES, UUID_NAMESPACE


class ReprocessProblems(Exception):
    def __init__(self, problems):
        super().__init__('\n'.join(problems))
        self.problems = problems


def changed_by_pipeline(content_type, back_content_type, image_field):
    return bool(align.templates_for(content_type, image_field, back_content_type)
                or images.radius_for(content_type, back_content_type, 'large'))


def _current_records(dataset):
    """{id: (content type, record)} over the data's types with ids, from data 2.0.0 on (UUIDs); {} before."""
    if not dataset.uses_uuids('sources'):
        return {}
    found = {}
    for content_type in dataset.content_types(exclude=INDEX_TYPES):
        for record in dataset.records(content_type):
            if 'id' in record:
                found[record['id']] = (content_type, record)
    return found


def jobs(staging, dataset):
    """[(content type, back content type, image field, staged item key, image path)] for every image the import wrote."""
    log_path = staging.dir / 'import-log.json'
    if not log_path.exists():
        raise ReprocessProblems([f'{staging.slug} has no import log: import it first'])
    log = json.loads(log_path.read_text(encoding='utf-8'))
    entries = staging.entries()
    attached = {}
    for key, entry in entries.get('items', {}).items():
        if entry.get('action') == 'attach':
            attached.setdefault(entry['to'], {})[entry['field']] = key
    current = _current_records(dataset)
    found = []
    for logged in log['records']:
        key, content_type, record = logged['key'], logged['content_type'], logged['record']
        # An import logged before data 2.0.0 names 1.x types and ids: the record is found again by the UUID 2.0.0
        # derived from them, under its type now (1.x's side-mission-cards were split in three).
        if isinstance(record.get('id'), int) and current:
            hit = current.get(str(uuid.uuid5(UUID_NAMESPACE, f"{content_type}:{record['id']}")))
            if hit is None:
                raise ReprocessProblems([f"{content_type} {record.get('name')}: not found in the data (by its 1.x id)"])
            content_type, record = hit
        fields = importer.image_fields(dataset, content_type)
        if not fields:
            continue
        if key == 'product':
            originals = {fields[0]: (entries.get('product') or {}).get('item')}
        else:
            originals = {entries['items'].get(key, {}).get('field') or fields[0]: key} | attached.get(key, {})
        back = dataset.back_type(record) if content_type == 'card-backs' else None
        for field, item_key in originals.items():
            if item_key and record.get(field):
                found.append((content_type, back, field, item_key, record[field]))
    return found, log


def plan(staging, dataset, reencode=False):
    """(jobs, log): the images to re-make; with reencode, every image the import wrote (product images too), so they
    all go through the current encoder (TinyPNG, when TINIFY_KEY is set) even where the pipeline wouldn't change them."""
    found, log = jobs(staging, dataset)
    todo = found if reencode else [job for job in found if changed_by_pipeline(*job[:3])]
    items = staging.items()
    problems = [f'{key}: staged original is missing' for *_, key, _ in todo if key not in items]
    problems += [f'{path}: not in the data repo (was the import committed elsewhere?)' for *_, path in todo
                 if not all(dataset.image_path(size, path).exists() for size in ('large', 'small'))]
    if problems:
        raise ReprocessProblems(problems)
    return todo, log


def apply(todo, log, staging, dataset, progress=lambda job: None):
    """Re-make the images; returns {staged item: alignment} and records it in the import log."""
    items, alignments = staging.items(), {}
    for job in todo:
        content_type, back, field, item_key, path = job
        progress(job)
        out = images.process(staging.dir / items[item_key]['file'], content_type, back, field)
        for size in ('large', 'small'):
            dataset.image_path(size, path).write_bytes(out[size])
        alignments[item_key] = out['alignment']
    log['alignment'] = log.get('alignment', {}) | alignments
    (staging.dir / 'import-log.json').write_text(json.dumps(log, indent=2), encoding='utf-8')
    return alignments
