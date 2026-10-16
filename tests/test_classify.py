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


@pytest.mark.parametrize('a, b', [
    ("Jabba's Realm", 'Jabbas-Realm'),
    ('The Bespin Gambit', 'Bespin Gambit'),
    ('Ahsoka Tano', 'ahsoka  tano'),
    ('434 "Deathhammer"', '434 Deathhammer'),
])
def test_normalise(a, b):
    assert normalise(a) == normalise(b)
