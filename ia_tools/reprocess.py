"""Re-make an imported product's images in place with the current image pipeline (ia reprocess).

For products imported before a pipeline change (alignment, rounded corners). The records stay as they are: the import
log says which records were written and where their images went, and entries.json which staged original each image
came from. Only files the import wrote are touched, and only for types the pipeline now changes (product images keep
theirs), so no TinyPNG compressions are spent on images that would come out the same."""
import json

from ia_tools import align, images, importer


class ReprocessProblems(Exception):
    def __init__(self, problems):
        super().__init__('\n'.join(problems))
        self.problems = problems


def changed_by_pipeline(content_type, back_content_type, image_field):
    return bool(align.templates_for(content_type, image_field, back_content_type)
                or images.radius_for(content_type, back_content_type, 'large'))


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
    found = []
    for logged in log['records']:
        key, content_type, record = logged['key'], logged['content_type'], logged['record']
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


def plan(staging, dataset):
    found, log = jobs(staging, dataset)
    todo = [job for job in found if changed_by_pipeline(*job[:3])]
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
