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
    ('side mission', 'side-mission-cards', 'color'),
    ('suppl', 'supply-cards', None),
    ('story', 'story-mission-cards', None),
    ('companion', 'companion-cards', None),
    ('condition', 'condition-cards', None),
    ('form', 'form-cards', None),
    ('skirmish map', 'skirmish-maps', None),
]


# card-backs are keyed on the parent for child cards (see the data repo's docs/data-model.md).
BACK_KEYS = {
    'hero-class-cards': 'heroes',
    'imperial-class-cards': 'imperial-classes',
    'agenda-cards': 'agenda-decks',
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
        return Guess(product=None, content_type='skirmish-maps')

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
    if content_type == 'side-mission-cards' and sub and 'threat' in sub.lower():
        content_type = 'threat-mission-cards'
        hints.pop('color', None)
    if content_type == 'deployment-cards' and name.startswith('clawdite form'):
        content_type = 'form-cards'  # boardwars keeps the shapeshifter's forms with the deployment cards
    if name == 'back' or name.startswith('back ') or name.endswith((' card back', ' form back')):  # "Neutral Card Back"
        return Guess(product=product, content_type='card-backs', back_of=content_type, hints=hints)
    return Guess(product=product, content_type=content_type, hints=hints)
