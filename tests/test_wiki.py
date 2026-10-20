import pytest

from ia_tools import wiki


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
    ('Ahsoka Tano Ally Pack', 39),
    ('Dice', None),
])
def test_source_for(real_dataset, label, source_id):
    from ia_tools.match import NameIndex

    assert wiki.source_for(NameIndex(real_dataset, ['sources']), label) == source_id
