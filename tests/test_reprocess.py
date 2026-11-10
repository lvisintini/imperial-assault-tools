import pytest

from ia_tools import images, importer, reprocess
from tests.test_importer import BOX, CARD, HERO, full_entries, stage


def imported(tmp_path, dataset):
    entries = full_entries(dataset)
    staging = stage(tmp_path, {'box': BOX, 'cmd': CARD, 'dep': CARD, 'hero': HERO, 'hero-w': HERO, 'feat': CARD,
                               'agenda': CARD, 'rules': CARD} | ({'back': CARD} if 'back' in entries['items'] else {}),
                    entries)
    importer.apply(importer.plan(staging, dataset), staging, dataset)
    return staging


def test_reprocess_remakes_every_image_but_the_product_one(tmp_path, dataset_copy, hash_files):
    staging = imported(tmp_path, dataset_copy)
    todo, log = reprocess.plan(staging, dataset_copy)
    paths = {path: (field, key) for _, _, field, key, path in todo}
    hero = dataset_copy.records('heroes')[-1]
    assert paths[hero['healthy']] == ('healthy', 'hero') and paths[hero['wounded']] == ('wounded', 'hero-w')
    assert dataset_copy.records('sources')[-1]['image'] not in paths  # no template, no corners: nothing would change
    # command card, hero healthy + wounded, hero class card, agenda card, and (2.0.0) the hero's back, as a hero's
    backs = [job for job in todo if job[0] == 'card-backs']
    assert len(todo) == 5 + len(backs) and [back for _, back, *_ in backs] == (
        ['heroes'] if dataset_copy.has_backs('hero-class-cards') else [])

    command = dataset_copy.records('command-cards')[-1]['image']
    dataset_copy.image_path('large', command).write_bytes(b'stale')
    alignments = reprocess.apply(todo, log, staging, dataset_copy)
    assert set(alignments) == {key for *_, key, _ in todo}
    expected = images.process(staging.dir / staging.items()['cmd']['file'], 'command-cards')
    assert dataset_copy.image_path('large', command).read_bytes() == expected['large']
    assert 'cmd' in (staging.dir / 'import-log.json').read_text()


def test_reprocess_only_touches_files_the_import_wrote(tmp_path, dataset_copy, hash_files):
    staging = imported(tmp_path, dataset_copy)
    dataset_copy.image_path('small', dataset_copy.records('command-cards')[-1]['image']).unlink()
    with pytest.raises(reprocess.ReprocessProblems) as raised:
        reprocess.plan(staging, dataset_copy)
    assert 'not in the data repo' in raised.value.problems[0]


def test_reprocess_needs_an_import_log(tmp_path, dataset_copy):
    staging = stage(tmp_path, {'cmd': CARD}, {'product': None, 'items': {}, 'extra': {}})
    with pytest.raises(reprocess.ReprocessProblems):
        reprocess.plan(staging, dataset_copy)


def test_reencode_takes_the_product_image_too(tmp_path, dataset_copy, hash_files):
    staging = imported(tmp_path, dataset_copy)
    plain, _ = reprocess.plan(staging, dataset_copy)
    every, _ = reprocess.plan(staging, dataset_copy, reencode=True)
    product = dataset_copy.records('sources')[-1]['image']
    assert product not in {path for *_, path in plain}
    assert {path for *_, path in every} == {path for *_, path in plain} | {product}


def test_a_1x_import_log_finds_its_records_by_their_derived_uuids(tmp_path, dataset_copy, hash_files):
    """An import logged before data 2.0.0 names 1.x types and numeric ids; the 2.0.0 records are found by the UUID
    the migration derived from them."""
    import json
    import uuid

    from ia_tools.dataset import UUID_NAMESPACE

    if not dataset_copy.uses_uuids('sources'):
        pytest.skip('1.x checkout')
    staging = imported(tmp_path, dataset_copy)
    log_path = staging.dir / 'import-log.json'
    log = json.loads(log_path.read_text(encoding='utf-8'))
    command = next(r for r in log['records'] if r['content_type'] == 'command-cards')
    real = command['record']['id']
    # Pretend the command card was logged by a 1.x import as number 9999: give the data's record the UUID that derives.
    derived = str(uuid.uuid5(UUID_NAMESPACE, 'command-cards:9999'))
    rows = dataset_copy.records('command-cards')
    next(r for r in rows if r['id'] == real)['id'] = derived
    command['record'] = dict(command['record'], id=9999)
    log_path.write_text(json.dumps(log), encoding='utf-8')
    todo, _ = reprocess.plan(staging, dataset_copy)
    assert any(job[0] == 'command-cards' and job[3] == 'cmd' for job in todo)
    command['record']['id'] = 9998  # no record derives from this one
    log_path.write_text(json.dumps(log), encoding='utf-8')
    with pytest.raises(reprocess.ReprocessProblems, match='not found'):
        reprocess.plan(staging, dataset_copy)
