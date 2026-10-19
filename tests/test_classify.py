import pytest

from ia_tools.boardwars import ImageRef
from ia_tools.classify import classify
from ia_tools.match import normalise


def guess(*path, name='Card'):
    return classify(ImageRef(path=tuple(path), name=name, url='https://example.invalid/x.jpg'))


@pytest.mark.parametrize('path, name, product, content_type, hints', [
    (('Core Box', 'Command Cards'), 'Burst Fire', 'Core Box', 'command-cards', {}),
    (('Expansion Boxes', 'Tyrants of Lothal'), 'Tyrants of Lothal', 'Tyrants of Lothal', 'sources', {}),
    (('Expansion Boxes', 'Tyrants of Lothal', 'Deployment Cards', 'Imperial'), 'Thrawn', 'Tyrants of Lothal',
     'deployment-cards', {'affiliation': 'Imperial'}),
    (('Expansion Boxes', 'Tyrants of Lothal', 'Rebel Upgrades', 'Tier 2'), 'Rifle', 'Tyrants of Lothal',
     'upgrade-cards', {'tier': 2}),
    (('Expansion Boxes', 'Tyrants of Lothal', 'Rebel Heroes', 'Ko-Tun Feralo'), 'Ko-Tun Feralo Wounded',
     'Tyrants of Lothal', 'heroes', {'hero': 'Ko-Tun Feralo'}),
    (('Expansion Boxes', 'Tyrants of Lothal', 'Rebel Heroes', 'Ko-Tun Feralo'), 'Rally', 'Tyrants of Lothal',
     'hero-class-cards', {'hero': 'Ko-Tun Feralo'}),
    (('Expansion Boxes', 'Return to Hoth', 'Side Missions', 'Threat Missions'), 'Escape', 'Return to Hoth',
     'threat-mission-cards', {}),
    (('Expansion Boxes', 'Return to Hoth', 'Side Missions', 'Red'), 'Canyon Run', 'Return to Hoth',
     'side-mission-cards', {'color': 'Red'}),
    (('Villain and Ally Packs', 'Wave-11', 'Thrawn', 'Agenda Deck'), 'Card', 'Thrawn', 'agenda-cards',
     {'wave': 'Wave-11'}),
    (('Villain and Ally Packs', 'Wave 11', 'Hondo Ohnaka', 'Deplyoyment Cards'), 'Lie in Ambush', 'Hondo Ohnaka',
     'deployment-cards', {'wave': 'Wave 11'}),  # boardwars' typo
    (('Skirmish Maps',), 'Geonosis Foundry', None, 'skirmish-maps', {}),
    (('Somewhere Else',), 'Thing', None, None, {}),
])
def test_classify(path, name, product, content_type, hints):
    result = guess(*path, name=name)
    assert (result.product, result.content_type, result.hints) == (product, content_type, hints)


def test_backs_say_what_they_are_the_back_of():
    result = guess('Expansion Boxes', 'Tyrants of Lothal', 'Imperial Class Decks', 'Overwhelming Force', name='back')
    assert (result.content_type, result.back_of, result.hints) == ('card-backs', 'imperial-class-cards',
                                                                   {'class': 'Overwhelming Force'})


@pytest.mark.parametrize('name, content_type, back_of', [
    ('Clawdite Form Scout', 'form-cards', None),
    ('Clawdite Form Back', 'card-backs', 'form-cards'),
    ('Neutral Card Back', 'card-backs', 'deployment-cards'),
])
def test_forms_and_backs_in_deployment_albums(name, content_type, back_of):
    result = guess('Expansion Boxes', 'Heart of the Empire', 'Deployment Cards', 'Mercenary', name=name)
    assert (result.content_type, result.back_of) == (content_type, back_of)


@pytest.mark.parametrize('a, b', [
    ("Jabba's Realm", 'Jabbas-Realm'),
    ('The Bespin Gambit', 'Bespin Gambit'),
    ('Ahsoka Tano', 'ahsoka  tano'),
    ('434 "Deathhammer"', '434 Deathhammer'),
])
def test_normalise(a, b):
    assert normalise(a) == normalise(b)


@pytest.mark.parametrize('content_type, gallery_name, dataset_name', [
    ('deployment-cards', 'Regular Stormtroopers', 'Stormtrooper'),
    ('deployment-cards', 'Elite Royal Guards', 'Royal Guard'),
    ('deployment-cards', 'Elite Hired Guns', 'Hired Gun'),
    ('condition-cards', 'Bleeding Condition', 'Bleeding'),
    ('heroes', 'Biv Bodhrik Hero Healthy', 'Biv Bodhrik'),
    ('heroes', 'Diala Hero Wounded', 'Diala Passil'),
    ('sources', 'Core Box', 'Imperial Assault'),
    ('sources', 'Ahsoka Tano', 'Ahsoka'),
    ('command-cards', 'Arcing Shot command card', 'Arcing Shot'),
    ('companion-cards', 'Cam Droid Companion', 'Cam Droid'),
    ('form-cards', 'Clawdite Form Scout', 'Scout'),
    ('supply-cards', 'Emergency Medpack', 'Emergency Medpac'),
])
def test_gallery_names_find_dataset_records(real_dataset, content_type, gallery_name, dataset_name):
    from ia_tools.match import NameIndex

    found = NameIndex(real_dataset, [content_type]).find(content_type, gallery_name)
    assert dataset_name in [r['name'] for r in found]


@pytest.mark.parametrize('gallery_name, affiliation, ids', [
    ('Stormtrooper', 'Imperial', [114]),            # unmarked is the regular card, not the elite one
    ('Riot Trooper elite skirmish', 'Imperial', [156]),  # (#155, campaign, is wrongly Mercenary: data#31)
    ('Agent Blaise skirmish', 'Imperial', [4]),
    ('Temporary Alliance', 'Imperial', [119]),      # the album's affiliation tells the two apart
    ('Temporary Alliance', 'Mercenary', [118]),
    ('Luke Skywalker Jedi Knight', 'Rebel', [79]),  # subtitle in the name
    ('Elite Wookie Warrior', None, [141]),          # boardwars misspelling
    ('Regular Wookie Warriors', None, [140]),       # ... and plural
    ('Echo Base Troopers', 'Rebel', [33]),
    ('Elite-Royal-Guard_errata', 'Imperial', [104]),
    ('Luke Skywalker', 'Rebel', [78, 79]),          # ambiguous: the user picks
])
def test_deployment_names_find_the_right_card(real_dataset, gallery_name, affiliation, ids):
    from ia_tools.match import NameIndex

    found = NameIndex(real_dataset, ['deployment-cards']).find('deployment-cards', gallery_name,
                                                               {'affiliation': affiliation} if affiliation else {})
    assert sorted(r['id'] for r in found) == ids
