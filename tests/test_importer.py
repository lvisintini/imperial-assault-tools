import hashlib
import json

import pytest
from PIL import Image

from ia_tools import importer
from ia_tools.staging import Staging
from tests.conftest import png_bytes, legacy_id


def stage(tmp_path, items, entries):
    """A staging folder with generated originals for the given item keys."""
    staging = Staging('test-product', tmp_path / 'staging')
    (staging.dir / 'originals').mkdir(parents=True)
    manifest_items = []
    for key, size in items.items():
        content = png_bytes(size, color=(len(key), 100, 100, 255))
        (staging.dir / 'originals' / f'{key}.png').write_bytes(content)
        manifest_items.append({'key': key, 'name': key, 'path': [], 'url': '', 'file': f'originals/{key}.png',
                               'sha512': hashlib.sha512(content).hexdigest(), 'bytes': len(content),
                               'width': size[0], 'height': size[1], 'format': 'PNG',
                               'guess': {'content_type': None, 'hints': {}}, 'matches': []})
    staging.manifest_path.write_text(json.dumps({'product': 'Test Product', 'existing_product': [], 'items': manifest_items}))
    staging.save_entries(entries)
    return staging


CARD, HERO, BOX = (600, 930), (1490, 1186), (300, 300)


def backs(dataset, content_type):
    """Data 2.0.0: {'back_id': the back of the type's first card}; {} for 1.x data, whose cards have none."""
    return {'back_id': dataset.records(content_type)[0]['back_id']} if dataset.has_backs(content_type) else {}


def full_entries(dataset):
    deployment = dataset.records('deployment-cards')[0]
    entries = {
        'product': {'action': 'new', 'item': 'box', 'record': {'name': 'Test Product', 'type': 'Expansion', 'wave': None}},
        'items': {
            'box': {'action': 'skip'},
            'cmd': {'action': 'new', 'content_type': 'command-cards', 'record': {
                'name': 'Brand New Command', 'iaspec': 'brandnewcommand', 'cost': 1, 'limit': 2}
                | backs(dataset, 'command-cards')},
            'dep': {'action': 'link', 'content_type': 'deployment-cards', 'id': deployment['id']},
            'hero': {'action': 'new', 'content_type': 'heroes', 'field': 'healthy', 'record': {'name': 'Test Hero'}},
            'hero-w': {'action': 'attach', 'to': 'hero', 'field': 'wounded'},
            'feat': {'action': 'new', 'content_type': 'hero-class-cards', 'record': {
                'name': 'Test Feat', 'hero_id': '@hero', 'xp': None, 'type': 'Feat', 'traits': None}},
            'agenda': {'action': 'new', 'content_type': 'agenda-cards', 'record': {
                'name': 'Test Agenda', 'agenda_id': '@x1', 'influence': 1, 'mission': False}
                | backs(dataset, 'agenda-cards')},
            'rules': {'action': 'known-skip'},
        },
        'extra': {'x1': {'content_type': 'agenda-decks', 'record': {'name': 'Test Deck'}}},
    }
    if dataset.has_backs('hero-class-cards'):  # 2.0.0: the new hero's back is staged too, and its card points at it
        entries['items']['back'] = {'action': 'new', 'content_type': 'card-backs', 'record': {'name': 'Rebel Hero: Test Hero'}}
        entries['items']['feat']['record']['back_id'] = '@back'
    return entries


def test_full_import(tmp_path, dataset_copy, hash_files):
    entries = full_entries(dataset_copy)
    staging = stage(tmp_path, {'box': BOX, 'cmd': CARD, 'dep': CARD, 'hero': HERO, 'hero-w': HERO, 'feat': CARD,
                               'agenda': CARD, 'rules': CARD} | ({'back': CARD} if 'back' in entries['items'] else {}),
                    entries)
    before = {t: len(dataset_copy.records(t)) for t in ('sources', 'command-cards', 'heroes', 'source-contents')}
    ids_before = {t: {r['id'] for r in dataset_copy.records(t)} for t in ('sources', 'command-cards', 'heroes', 'agenda-decks')}

    plan = importer.plan(staging, dataset_copy)
    assert importer.summary(plan)['new_records'] == {
        'sources': 1, 'command-cards': 1, 'heroes': 1, 'hero-class-cards': 1, 'agenda-cards': 1, 'agenda-decks': 1} | (
        {'card-backs': 1} if 'back' in entries['items'] else {})
    importer.apply(plan, staging, dataset_copy)

    new_ids = {t: dataset_copy.records(t)[-1]['id'] for t in ids_before}
    for content_type, before_import in ids_before.items():  # fresh UUIDs, or (1.x data) the next number
        assert new_ids[content_type] not in before_import
        assert dataset_copy.uses_uuids(content_type) or new_ids[content_type] == max(before_import) + 1

    source = dataset_copy.records('sources')[-1]
    staged = {'id': new_ids['sources'], 'name': 'Test Product', 'type': 'Expansion', 'wave': None,
              'image': 'sources/test-product.png'}
    # Fields the schema gained after the product was staged are null (product_code and the dates).
    assert source == importer.missing_nullables(dataset_copy.schema('sources'), staged) | staged
    hero = dataset_copy.records('heroes')[-1]
    assert hero['healthy'] == 'heroes/test-hero-healthy.png' and hero['wounded'] == 'heroes/test-hero-wounded.png'
    feat = dataset_copy.records('hero-class-cards')[-1]
    assert feat['hero_id'] == hero['id'] and feat['image'] == 'hero-class-cards/test-hero-test-feat.png'
    agenda = dataset_copy.records('agenda-cards')[-1]
    assert agenda['agenda_id'] == new_ids['agenda-decks'] and agenda['image'] == 'agenda-cards/test-deck-test-agenda.png'
    if 'back' in entries['items']:  # sized as its card's, a hero class card back
        back = dataset_copy.records('card-backs')[-1]
        assert feat['back_id'] == back['id'] and back['image'] == 'card-backs/rebel-hero-test-hero.png'
        with Image.open(dataset_copy.image_path('large', back['image'])) as im:
            assert im.size == (424, 657)

    # source-contents: new top-level records plus the linked deployment card; child cards come with their parent.
    rows = dataset_copy.records('source-contents')[before['source-contents']:]
    assert {(r['content_type'], r['content_id']) for r in rows} == {
        ('command-cards', new_ids['command-cards']), ('heroes', hero['id']), ('agenda-decks', new_ids['agenda-decks']),
        ('deployment-cards', dataset_copy.records('deployment-cards')[0]['id'])}
    assert all(r['source_id'] == source['id'] for r in rows)

    # Files are written in the data repo's format and the images exist at the right sizes.
    for content_type in ('sources', 'heroes', 'source-contents'):
        on_disk = json.loads(dataset_copy.path(content_type).read_text())
        assert on_disk == dataset_copy.records(content_type)
    with Image.open(dataset_copy.image_path('small', hero['wounded'])) as im:
        assert im.size == (650, 515)

    seen, skipped = hash_files
    items = staging.items()
    assert items['hero-w']['sha512'] in seen.read_text().split()
    assert seen.read_text().startswith('aaa\n')
    assert skipped.read_text().split() == [items['rules']['sha512']]


def test_problems_are_all_reported_and_nothing_is_written(tmp_path, dataset_copy, hash_files):
    entries = full_entries(dataset_copy)
    entries['items']['cmd']['record']['iaspec'] = dataset_copy.records('command-cards')[0]['iaspec']
    entries['items']['feat']['record']['hero_id'] = '@nope'
    del entries['items']['hero-w']
    staging = stage(tmp_path, {'box': BOX, 'cmd': CARD, 'hero': HERO, 'feat': CARD, 'agenda': CARD}, entries)
    sources_before = dataset_copy.path('sources').read_text()

    with pytest.raises(importer.ImportProblems) as raised:
        importer.plan(staging, dataset_copy)
    problems = '\n'.join(raised.value.problems)
    assert 'iaspec' in problems and '@nope' in problems and 'heroes.wounded' in problems
    assert dataset_copy.path('sources').read_text() == sources_before


def test_an_iaspec_that_breaks_the_rule_is_a_problem(tmp_path, dataset_copy, hash_files):
    entries = full_entries(dataset_copy)
    entries['items']['up'] = {'action': 'new', 'content_type': 'deployment-cards', 'record': {
        'name': 'Brand New Upgrade', 'elite': True, 'unique': False, 'iaspec': 'brandnewupgrade'}}
    staging = stage(tmp_path, {'box': BOX, 'cmd': CARD, 'hero': HERO, 'hero-w': HERO, 'feat': CARD, 'agenda': CARD,
                               'up': CARD}, entries)

    with pytest.raises(importer.ImportProblems) as raised:
        importer.plan(staging, dataset_copy)
    assert "up: iaspec 'brandnewupgrade' doesn't follow the rule; expected 'elitebrandnewupgrade'" in raised.value.problems


def test_existing_image_paths_are_never_overwritten(tmp_path, dataset_copy, hash_files):
    entries = full_entries(dataset_copy)
    staging = stage(tmp_path, {'box': BOX, 'cmd': CARD, 'hero': HERO, 'hero-w': HERO, 'feat': CARD, 'agenda': CARD},
                    entries)
    taken = dataset_copy.image_path('large', 'command-cards/brand-new-command.png')
    taken.parent.mkdir(parents=True, exist_ok=True)
    taken.write_bytes(b'existing')
    with pytest.raises(importer.ImportProblems, match='already exists'):
        importer.plan(staging, dataset_copy)


@pytest.mark.parametrize('content_type, record, field, parent, slug', [
    ('deployment-cards', {'name': 'AT-ST', 'description': None, 'elite': True, 'unique': False,
                          'modes': ['Campaign', 'Skirmish']}, 'image', None, 'at-st-elite'),
    ('deployment-cards', {'name': 'Agent Blaise', 'description': 'ISB Interrogator', 'elite': True, 'unique': True,
                          'modes': ['Skirmish']}, 'image', None, 'agent-blaise-isb-interrogator-skirmish'),
    ('hero-class-cards', {'name': 'All-Out Attack'}, 'image', 'Shyla Varad', 'shyla-varad-all-out-attack'),
    ('upgrade-cards', {'name': '434 "Deathhammer"'}, 'image', None, '434-deathhammer'),
    ('upgrade-cards', {'name': "Admiral's Uniform"}, 'image', None, 'admirals-uniform'),
    ('heroes', {'name': 'Biv Bodhrik'}, 'wounded', None, 'biv-bodhrik-wounded'),
    ('card-backs', {'deck': 'Rebel Hero', 'variant': 'Biv Bodhrik'}, 'image', None, 'rebel-hero-biv-bodhrik'),
])
def test_image_slugs_follow_the_existing_names(content_type, record, field, parent, slug):
    assert importer.image_slug(content_type, record, field, parent) == slug


def test_existing_image_names_follow_the_slug_rules(real_dataset):
    """Most existing deployment card file names come out the same with today's rules."""
    records = real_dataset.records('deployment-cards')
    same = sum(importer.image_slug('deployment-cards', r, 'image') + '.png' == r['image'].split('/', 1)[1] for r in records)
    assert same / len(records) > 0.9


def test_hash_lists_ignore_comments(tmp_path):
    from ia_tools.audit import load_hashes

    path = tmp_path / 'hashes.txt'
    path.write_text('# a comment about abc\nabc\n\n# another\ndef\n')
    assert load_hashes(path) == {'abc', 'def'}


def test_items_can_name_their_own_product(tmp_path, dataset_copy, hash_files):
    """A folder of gaps from many products has no product of its own: each item names one."""
    reward, deployment = (dataset_copy.records(t)[0] for t in ('reward-cards', 'deployment-cards'))
    hoth, bespin, jabba = (legacy_id(dataset_copy, 'sources', n) for n in (2, 3, 4))
    entries = {'product': None, 'extra': {}, 'items': {
        'cmd': {'action': 'new', 'content_type': 'command-cards', 'source_id': hoth, 'record': {
            'name': 'Brand New Command', 'iaspec': 'brandnewcommand', 'cost': 1, 'limit': 2}
            | backs(dataset_copy, 'command-cards')},
        'rew': {'action': 'link', 'content_type': 'reward-cards', 'id': reward['id'], 'source_id': bespin},
        'side': {'action': 'skip', 'source_id': jabba},
    }}
    staging = stage(tmp_path, {'cmd': CARD, 'rew': CARD, 'side': CARD}, entries)
    plan = importer.plan(staging, dataset_copy)
    assert {(r['source_id'], r['content_type']) for r in plan['rows']} == {(hoth, 'command-cards'), (bespin, 'reward-cards')}

    entries['items']['side'] = {'action': 'link', 'content_type': 'deployment-cards', 'id': deployment['id']}
    entries['items']['rew']['source_id'] = 999
    staging.save_entries(entries)
    with pytest.raises(importer.ImportProblems) as raised:
        importer.plan(staging, dataset_copy)
    assert set(raised.value.problems) == {'No product chosen', 'rew: product id 999 is not in sources.json'}


def test_missions_link_through_their_index_row(tmp_path, dataset_copy, hash_files):
    """Data 2.0.0: a new mission card gets a missions row, and the product links to the row, not the card. So does an
    existing mission linked to another product."""
    if not dataset_copy.path('missions').exists():
        pytest.skip('1.x data has no missions index')
    existing = dataset_copy.records('missions')[0]
    bespin = legacy_id(dataset_copy, 'sources', 3)  # the first mission (Disaster) is Return to Hoth's
    entries = {'product': {'action': 'existing', 'id': bespin}, 'extra': {}, 'items': {
        'new': {'action': 'new', 'content_type': 'campaign-regular-side-mission-cards',
                'record': {'name': 'A Brand New Mission'} | backs(dataset_copy, 'campaign-regular-side-mission-cards')},
        'old': {'action': 'link', 'content_type': existing['content_type'], 'id': existing['content_id']},
    }}
    plan = importer.plan(stage(tmp_path, {'new': CARD, 'old': CARD}, entries), dataset_copy)
    new = next(p.record for p in plan['pending'] if p.key == 'new')
    [row] = plan['missions']
    assert row | {'id': None} == {'id': None, 'content_type': 'campaign-regular-side-mission-cards',
                                  'content_id': new['id'], 'map_id': None}
    assert {(r['content_type'], r['content_id']) for r in plan['rows']} == {
        ('missions', row['id']), ('missions', existing['id'])}
