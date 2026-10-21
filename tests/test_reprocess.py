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
