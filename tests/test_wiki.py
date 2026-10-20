import json

import pytest

from ia_tools import wiki
from tests.conftest import legacy_id


@pytest.mark.parametrize('text, name, link, copies, notes', [
    ('[[Pummel]] (x2)', 'Pummel', 'Pummel', 2, []),
    ('[[Reinforcements]] (2x)', 'Reinforcements', 'Reinforcements', 2, []),
    ('[[Riot Trooper (Campaign)]] (x2)', 'Riot Trooper (Campaign)', 'Riot Trooper (Campaign)', 2, []),
    ('[[Rogue Smuggler]] (Skirmish Upgrade) (Han Solo)', 'Rogue Smuggler', 'Rogue Smuggler', None,
     ['Skirmish Upgrade', 'Han Solo']),
    ('[[Take Cover (Command Card)|Take Cover]] (x2)', 'Take Cover', 'Take Cover (Command Card)', 2, []),
    ('[[Strain]] tokens (x35)', 'Strain tokens', 'Strain', 35, []),
    ('[[MISSION TOKENS|Mission tokens]] (20)', 'Mission tokens', 'MISSION TOKENS', 20, []),
    ('[[Entrance Token|1 Entrance token]]', 'Entrance token', 'Entrance Token', 1, []),
    ('4 Door Tokens with Plastic Stands', 'Door Tokens with Plastic Stands', None, 4, []),
    ('[[File:Others Image.png|border|right|604x604px]][[Dice]] (x11)', 'Dice', 'Dice', 11, []),
    ('[https://cards.boardwars.eu/albums/Skirmish-Maps/Moisture%20Farm.jpg Moisture Farm map]', 'Moisture Farm map',
     'https://cards.boardwars.eu/albums/Skirmish-Maps/Moisture%20Farm.jpg', None, []),
])
def test_component(text, name, link, copies, notes):
    assert wiki.component(text) == {'name': name, 'link': link, 'copies': copies, 'notes': notes}


PAGE = """
== Included Components ==
=== Miniatures ===
==== Imperial ====
* Riot Trooper (x4)
 Condition Cards
* [[Weakened]] (x4)
== [[MISSIONS|Missions]] ==
 Side Mission Cards (14 Side Mission Cards)
* [[Brushfire]]
=== Skirmish Maps ===
* Coruscant Landfill
** [[Lair of the Dianoga]]
"""


def test_parse_contents():
    found = {c['name']: c for c in wiki.parse_contents(PAGE)}
    assert found['Riot Trooper']['headings'] == ['Included Components', 'Miniatures', 'Imperial']
    # A plain-text label stands in for a heading beside the second one.
    assert found['Weakened']['headings'] == ['Included Components', 'Condition Cards']
    assert found['Brushfire']['headings'] == ['Missions', 'Side Mission Cards (14 Side Mission Cards)']
    assert found['Lair of the Dianoga']['parent'] == 'Coruscant Landfill'
    assert found['Coruscant Landfill']['parent'] is None


MAIN = """
===Core Set  ===
<span class="" style="font-size:14px;">(Announced Aug 15th, 2014 / Released December 15th, 2014)</span>
*SWI01 [[Core Set|Star Wars: Imperial Assault Core Set]]
**[[Luke Skywalker Ally Pack]]
=== Wave 8 ===
<span class="" style="font-size:14px;">(Announced August 5th, 2016 / Release December 29th, 2016)</span>
* SWI33 [[Luke Skywalker Jedi Knight Ally Pack|Luke Skywalker, Jedi Knight Ally Pack]]
* SWI37 [https://ffg-forum-archive.entropicdreams.com/topic/291264-product-swi37/ Never print]
"""


def test_parse_products():
    products = wiki.parse_products(MAIN)
    assert [(p['code'], p['title'], p['included_in']) for p in products] == [
        ('SWI01', 'Core Set', None), (None, 'Luke Skywalker Ally Pack', 'Core Set'),
        ('SWI33', 'Luke Skywalker Jedi Knight Ally Pack', None)]
    assert (products[2]['wave'], products[2]['announced'], products[2]['released']) == (
        'Wave 8', 'August 5th, 2016', 'December 29th, 2016')


@pytest.mark.parametrize('label, source_id', [
    ('Core Set', 0),
    ('IG-88 Villain Pack', 5),
    ('Luke Skywalker, Jedi Knight Ally Pack', 31),
    ('Luke Skywalker Jedi Knight Ally Pack', 31),
    ('Ahsoka Tano Ally Pack', 39),
    ('Dice', None),
])
def test_source_for(real_dataset, label, source_id):
    from ia_tools.match import NameIndex

    assert wiki.source_for(NameIndex(real_dataset, ['sources']), label) == legacy_id(real_dataset, 'sources', source_id)


@pytest.mark.parametrize('text, date', [
    ('Aug 15th, 2014', '2014-08-15'),
    ('August 20th 2015', '2015-08-20'),
    ('June 2nd, 2016', '2016-06-02'),
    ('April 13th, 2018', '2018-04-13'),
    ('TBA', None),
    (None, None),
])
def test_parse_date(text, date):
    assert wiki.parse_date(text) == date


BIG_BOX = {'code': 'SWI10', 'title': 'Twin Shadows', 'page': 'Twin Shadows', 'revid': 7, 'wave': 'Wave 2',
           'announced': 'Mar 18th, 2015', 'released': 'August 20th 2015', 'included_in': None, 'source_id': 1}
BIG_BOX_PAGE = '{{Infobox\n| type = Big Box\n| wave = 2\n| release_date = 2015-08-20\n| sku = SWI10\n}}'


def test_source_values():
    assert wiki.source_values(BIG_BOX, BIG_BOX_PAGE) == ({
        'product_code': 'SWI10', 'announced_date': '2015-03-18', 'release_date': '2015-08-20', 'wave': 2,
        'type': 'Expansion'}, [])
    core = BIG_BOX | {'code': 'SWI01', 'wave': 'Core Set', 'released': 'Someday'}
    values, notes = wiki.source_values(core, '| release_date = 2014-12-15')
    assert (values['wave'], values['type'], values['release_date']) == (0, 'Core Game', None)
    assert notes == ["unreadable released date 'Someday'", 'the product page says released 2014-12-15']


def test_propose_sources(tmp_path, dataset_copy):
    if 'product_code' not in dataset_copy.schema('sources')['properties']:
        pytest.skip('the data checkout has no sources.product_code yet')
    twin_shadows_id = legacy_id(dataset_copy, 'sources', 1)
    twin_shadows = next(s for s in dataset_copy.records('sources') if s['id'] == twin_shadows_id)
    twin_shadows.update(product_code=None, announced_date=None, release_date=None, wave=None)  # as before data 1.5.0
    (tmp_path / 'wiki' / 'pages').mkdir(parents=True)
    big_box = BIG_BOX | {'source_id': twin_shadows_id}
    dice = big_box | {'code': 'SWI02', 'title': 'Dice', 'source_id': None}
    (tmp_path / 'wiki' / 'products.json').write_text(json.dumps({'products': [big_box, dice]}), encoding='utf-8')
    (tmp_path / 'wiki' / 'pages' / 'twin-shadows.json').write_text(
        json.dumps({'parse': {'title': 'Twin Shadows', 'wikitext': BIG_BOX_PAGE}}), encoding='utf-8')

    assert wiki.propose_sources(dataset_copy, 'wiki-sources', root=tmp_path) == ['e1']
    [proposal] = json.loads((tmp_path / 'wiki-sources' / 'manifest.json').read_text(encoding='utf-8'))['edits']
    assert (proposal['id'], proposal['note']) == (twin_shadows_id, 'From the wiki: Twin Shadows (revision 7)')
    assert proposal['changes']['product_code'] == 'SWI10' and proposal['changes']['wave'] == 2
    assert 'type' not in proposal['changes']  # already Expansion
    assert wiki.propose_sources(dataset_copy, 'wiki-sources', root=tmp_path) == []  # already proposed
