"""Guess what a gallery image is from its album path. These are suggestions: the data-entry app lets the user correct
them. The rules follow the 2017–18 crawler's (crawler/spiders/swia.py)."""
import re
from dataclasses import dataclass, field

# First album inside a product → content type and the hint its sub-album gives.
SECTIONS = [
    ('agenda', 'agenda-cards', 'deck'),
    ('command', 'command-cards', None),
    ('deployment', 'deployment-cards', 'affiliation'),
    ('deplyoyment', 'deployment-cards', 'affiliation'),  # boardwars' Hondo Ohnaka pack
    ('imperial class', 'imperial-class-cards', 'class'),
    ('rebel hero', 'hero-class-cards', 'hero'),
    ('rebel upgrade', 'upgrade-cards', 'tier'),
    ('reward', 'reward-cards', None),
    ('side mission', 'campaign-regular-side-missions', 'color'),  # by color below
    ('suppl', 'supply-cards', None),
    ('story', 'campaign-story-missions', None),
    ('companion', 'companion-cards', None),
    ('condition', 'condition-cards', None),
    ('form', 'form-cards', None),
    ('skirmish map', 'maps', None),
]


SIDE_MISSION_COLORS = {'red': 'campaign-hero-side-missions', 'green': 'campaign-ally-side-missions'}


# boardwars keeps every skirmish map in one album that doesn't say which product it comes from. These are the maps it
# added after the 2017–18 batches; the products' wiki pages name them (imperial-assault-data#29).
SKIRMISH_MAP_PRODUCTS = {
    '30th Floor Plazza': 'Heart of the Empire',  # sic
    'Coruscant Back Alleys': 'Maul',
    'Coruscant Senate Office': 'Emperor Palpatine',
    'Devaron Garrison': 'Sabine Wren and Zeb Orrelios',
    'Imperial Tower': 'Thrawn',
    'Lothal Battlefront': 'Ezra Bridger and Kanan Jarrus',
    'Lothal Spaceport': 'Hondo Ohnaka',
    'Lothal Wastes': 'Tyrants of Lothal',
    'Uscru Entertainment District': 'Ahsoka Tano',
}


@dataclass
class Guess:
    product: str | None         # boardwars' product name, e.g. 'Tyrants of Lothal'
    content_type: str | None    # None when no rule matched
    back_of: str | None = None  # set when the image is a card back: the content type it's the back of
    hints: dict = field(default_factory=dict)


def product_of(path):
    """(product name, index where the product's own albums start)."""
    if path[:1] == ('Core Box',):
        return 'Core Box', 1
    if path[:1] == ('Expansion Boxes',) and len(path) > 1:
        return path[1], 2
    if path[:1] == ('Villain and Ally Packs',) and len(path) > 2:
        return path[2], 3
    return None, len(path)


def classify(image):
    path = image.path
    if path[:1] == ('Skirmish Maps',):
        return Guess(product=None, content_type='maps')

    product, start = product_of(path)
    if product is None:
        return Guess(product=None, content_type=None)
    hints = {}
    if path[0] == 'Villain and Ally Packs':
        hints['wave'] = path[1]
    rest = path[start:]
    if not rest:
        return Guess(product=product, content_type='sources', hints=hints)

    content_type, sub = None, rest[1] if len(rest) > 1 else None
    for prefix, section_type, hint in SECTIONS:
        if rest[0].lower().startswith(prefix):
            content_type = section_type
            if hint and sub:
                hints[hint] = int(re.findall(r'\d+', sub)[-1]) if hint == 'tier' and re.search(r'\d', sub) else sub
            break

    name = image.name.lower()
    if content_type == 'hero-class-cards' and (name.endswith('healthy') or name.endswith('wounded')):
        content_type = 'heroes'
    if content_type == 'campaign-regular-side-missions':
        if sub and 'threat' in sub.lower():
            content_type = 'campaign-threat-missions'
        else:  # red missions are a hero's, green ones earn an ally
            color = (hints.get('color') or '').lower()
            content_type = SIDE_MISSION_COLORS.get(next((c for c in SIDE_MISSION_COLORS if c in color), None),
                                                   content_type)
        hints.pop('color', None)
    if content_type == 'deployment-cards' and name.startswith('clawdite form'):
        content_type = 'form-cards'  # boardwars keeps the shapeshifter's forms with the deployment cards
    if name == 'back' or name.startswith('back ') or name.endswith((' card back', ' form back')):  # "Neutral Card Back"
        return Guess(product=product, content_type='card-backs', back_of=content_type, hints=hints)
    return Guess(product=product, content_type=content_type, hints=hints)
