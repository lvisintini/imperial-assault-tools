import pytest

from ia_tools import edits, importer
from ia_tools.staging import Staging
from tests.conftest import legacy_id


def staging_with(tmp_path, dataset, content_type, record_id, changes, decision):
    key = edits.propose(dataset, 'edits', content_type, record_id, changes, note='test', root=tmp_path)
    staging = Staging('edits', tmp_path)
    if decision is not None:
        staging.save_entries({'product': None, 'items': {}, 'extra': {}, 'edits': {key: decision}})
    return staging


def touch_images(dataset, relative):
    for size in ('large', 'small'):
        path = dataset.image_path(size, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(size.encode())


def test_a_rename_moves_the_images(tmp_path, dataset_copy, hash_files):
    source = next(s for s in dataset_copy.records('sources') if s['id'] == legacy_id(dataset_copy, 'sources', 5))
    touch_images(dataset_copy, source['image'])
    staging = staging_with(tmp_path, dataset_copy, 'sources', legacy_id(dataset_copy, 'sources', 5), {'name': 'IG88'},
                           {'action': 'apply', 'changes': {'name': 'IG88'}, 'rename_images': True})

    plan = importer.plan(staging, dataset_copy)
    assert importer.summary(plan)['edits'] == 1
    old = source['image']
    importer.apply(plan, staging, dataset_copy)

    on_disk = next(s for s in dataset_copy.records('sources') if s['id'] == legacy_id(dataset_copy, 'sources', 5))
    assert on_disk['name'] == 'IG88' and on_disk['image'] == 'sources/ig88.png'
    assert dataset_copy.path('sources').read_text().count('"IG88"') == 1
    assert dataset_copy.image_path('small', 'sources/ig88.png').read_bytes() == b'small'
    assert not dataset_copy.image_path('large', old).exists()


def test_values_can_change_and_images_can_stay(tmp_path, dataset_copy, hash_files):
    ahsoka = legacy_id(dataset_copy, 'sources', 39)
    staging = staging_with(tmp_path, dataset_copy, 'sources', ahsoka, {'name': 'Ahsoka Tano'},
                           {'action': 'apply', 'changes': {'name': 'Ahsoka Tano (Ally Pack)'}, 'rename_images': False})
    (proposal, after, moves), = importer.plan(staging, dataset_copy)['edits']
    assert after['name'] == 'Ahsoka Tano (Ally Pack)' and moves == {}


def test_skipped_and_undecided_edits_change_nothing(tmp_path, dataset_copy, hash_files):
    ig88 = legacy_id(dataset_copy, 'sources', 5)
    undecided = staging_with(tmp_path, dataset_copy, 'sources', ig88, {'name': 'X'}, None)
    assert importer.plan(undecided, dataset_copy)['edits'] == []
    assert importer.plan(staging_with(tmp_path / 'b', dataset_copy, 'sources', ig88, {'name': 'X'}, {'action': 'skip'}),
                         dataset_copy)['edits'] == []


def test_edit_problems(tmp_path, dataset_copy, hash_files):
    hero = dataset_copy.records('heroes')[0]
    touch_images(dataset_copy, 'sources/imperial-assault.png')
    cases = [
        ('sources', legacy_id(dataset_copy, 'sources', 5), {'name': 'Imperial Assault'}),  # its image name is taken
        ('sources', legacy_id(dataset_copy, 'sources', 5), {'wave': 'one'}),                # breaks the schema
    ]
    if not dataset_copy.has_backs('hero-class-cards'):  # 1.x: a card back's variant is the hero's name
        cases.append(('heroes', hero['id'], {'name': 'Someone'}))
    for n, (content_type, record_id, changes) in enumerate(cases):
        staging = staging_with(tmp_path / str(n), dataset_copy, content_type, record_id, changes,
                               {'action': 'apply', 'changes': changes, 'rename_images': True})
        with pytest.raises(importer.ImportProblems):
            importer.plan(staging, dataset_copy)


def test_proposals_are_checked(tmp_path, real_dataset):
    with pytest.raises(ValueError):
        edits.propose(real_dataset, 'edits', 'sources', 9999, {'name': 'X'}, root=tmp_path)
    with pytest.raises(ValueError):
        edits.propose(real_dataset, 'edits', 'sources', legacy_id(real_dataset, 'sources', 5), {'nickname': 'X'},
                      root=tmp_path)
    with pytest.raises(ValueError):
        edits.propose(real_dataset, 'edits', 'card-backs', 0, {'deck': 'X'}, root=tmp_path)
