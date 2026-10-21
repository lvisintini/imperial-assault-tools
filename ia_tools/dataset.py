"""Reading and writing the imperial-assault-data checkout, in its exact JSON formatting."""
import json
import uuid
from itertools import count
from pathlib import Path

import jsonref

from ia_tools import settings

# Data 2.0.0's types. A 1.x checkout lacks some (Dataset.content_types() lists the ones it has).
CONTENT_TYPES = [
    'sources', 'source-contents', 'maps', 'agenda-decks', 'agenda-cards', 'command-cards',
    'condition-cards', 'deployment-cards', 'heroes', 'hero-class-cards', 'imperial-classes', 'imperial-class-cards',
    'supply-cards', 'campaign-story-mission-cards', 'campaign-hero-side-mission-cards',
    'campaign-ally-side-mission-cards', 'campaign-regular-side-mission-cards', 'reward-cards', 'companion-cards',
    'upgrade-cards', 'card-backs', 'campaign-threat-mission-cards', 'form-cards', 'skirmish-mission-cards',
    'raid-missions', 'epilogue-cards', 'missions', 'mission-rewards', 'requirements',
]
# The mission card collections missions.json indexes (data 2.0.0; also agenda cards that are missions).
MISSION_TYPES = [
    'campaign-story-mission-cards', 'campaign-threat-mission-cards', 'campaign-hero-side-mission-cards',
    'campaign-ally-side-mission-cards', 'campaign-regular-side-mission-cards', 'skirmish-mission-cards',
    'raid-missions',
]
# Indexes and join tables: never entered, imported or matched by name.
INDEX_TYPES = ['source-contents', 'missions', 'mission-rewards', 'requirements']

# Types renamed in data 2.0.0. The tools use the new names; a 1.x checkout still stores the old ones, and Dataset
# translates wherever a name meets the files (file names, image folders, source-contents' content_type). 1.x's
# side-mission-cards was split in three; the tools don't import side missions into 1.x data.
RENAMED = {'maps': 'skirmish-maps', 'campaign-story-mission-cards': 'story-mission-cards',
           'campaign-threat-mission-cards': 'threat-mission-cards'}


def canonical(content_type):
    """The tools' name for a type, given either its 1.x or its 2.0.0 name."""
    return next((new for new, old in RENAMED.items() if old == content_type), content_type)


# Child → parent foreign keys (see docs/data-model.md in the data repo).
FOREIGN_KEYS = {
    ('agenda-cards', 'agenda_id'): 'agenda-decks',
    ('hero-class-cards', 'hero_id'): 'heroes',
    ('imperial-class-cards', 'class_id'): 'imperial-classes',
    ('campaign-hero-side-mission-cards', 'hero_id'): 'heroes',  # data 2.0.0: the hero a red side mission is for
    ('epilogue-cards', 'mission_id'): 'missions',  # data 2.0.0: the mission an epilogue ends
}
# Data 2.0.0: every card's back (card-backs). Not in FOREIGN_KEYS, which are parents (a hero class card's parent names
# its image); a card has a parent and a back.
BACK_ID = 'back_id'
# The type a back is sized and aligned for (1.x's card-backs.content_type): a child card's back is its parent's.
BACK_KEYS = {
    'hero-class-cards': 'heroes',
    'imperial-class-cards': 'imperial-classes',
    'agenda-cards': 'agenda-decks',
}


def dumps(records):
    """The data repo's formatting: 2-space indent, ASCII-escaped, no trailing newline."""
    return json.dumps(records, indent=2)


class Dataset:
    def __init__(self, root=None):
        self.root = Path(root or settings.DATA_ROOT)
        if not (self.root / 'data' / 'sources.json').is_file():
            raise FileNotFoundError(f'{self.root} is not an imperial-assault-data checkout (set IA_DATA_ROOT)')
        self._data = {}

    def stored(self, content_type):
        """The type's name in this checkout: its 1.x name if the checkout predates the rename."""
        old = RENAMED.get(content_type)
        return old if old and not (self.root / 'schemas' / f'{content_type}.json').exists() else content_type

    def content_types(self, exclude=()):
        """CONTENT_TYPES this checkout has, in order, without those in exclude."""
        return [t for t in CONTENT_TYPES if t not in exclude and self.path(t).exists()]

    def path(self, content_type):
        return self.root / 'data' / f'{self.stored(content_type)}.json'

    def records(self, content_type):
        if content_type not in self._data:
            self._data[content_type] = json.loads(self.path(content_type).read_text(encoding='utf-8'))
        return self._data[content_type]

    def save(self, content_type):
        self.path(content_type).write_text(dumps(self.records(content_type)), encoding='utf-8')

    def has_ids(self, content_type):
        """Whether the type's records have an id (source-contents and card-backs don't; condition-cards gained one in
        data 1.4.0)."""
        return 'id' in self.schema(content_type)['properties']

    def has_quantities(self):
        """Whether source-contents rows say how many copies a product has (quantity, data 2.0.0)."""
        return 'quantity' in self.schema('source-contents')['properties']

    def has_backs(self, content_type):
        """Whether the type's records point at their card back (back_id, data 2.0.0)."""
        return BACK_ID in self.schema(content_type)['properties']

    def back_type(self, back):
        """What a card back is sized and aligned for: its content_type (1.x), or the type of the cards using it, by
        BACK_KEYS (2.0.0). None for a back no card uses."""
        if 'content_type' in back:
            return back['content_type']
        for content_type in self.content_types(exclude=INDEX_TYPES):
            if self.has_backs(content_type) and any(r[BACK_ID] == back['id'] for r in self.records(content_type)):
                return BACK_KEYS.get(content_type, content_type)
        return None

    def uses_uuids(self, content_type):
        """Whether the type's ids are UUID strings (data 2.0.0 on) rather than numbers (1.x). Read from the schema, so
        the tools work with either checkout."""
        return self.schema(content_type)['properties'].get('id', {}).get('type') == 'string'

    def next_id(self, content_type):
        """The next numeric id (1.x data): the highest one plus one."""
        return max((r['id'] for r in self.records(content_type)), default=-1) + 1

    def new_ids(self, content_type):
        """Ids for new records of a type, one per next(): random UUIDs, or the numbers after the highest one."""
        if self.uses_uuids(content_type):
            return (str(uuid.uuid4()) for _ in count())
        return count(self.next_id(content_type))

    def placeholder_id(self, content_type):
        """A schema-valid id for checking records that don't have their real one yet."""
        return '00000000-0000-4000-8000-000000000000' if self.uses_uuids(content_type) else 0

    def parse_id(self, content_type, text):
        """An id typed on the command line, as the type stores it."""
        return text if self.uses_uuids(content_type) else int(text)

    def key_order(self, content_type):
        """Field order of the file's first record, so new records serialise like the existing ones."""
        records = self.records(content_type)
        return list(records[0]) if records else list(self.schema(content_type)['properties'])

    def schema(self, content_type):
        path = (self.root / 'schemas' / f'{self.stored(content_type)}.json').resolve()
        with open(path, encoding='utf-8') as f:
            return jsonref.load(f, base_uri=path.as_uri(), jsonschema=True, proxies=False)

    def image_path(self, size, relative):
        return self.root / 'images' / size / relative
