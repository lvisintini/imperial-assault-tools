"""Reading and writing the imperial-assault-data checkout, in its exact JSON formatting."""
import json
import uuid
from itertools import count
from pathlib import Path

import jsonref

from ia_tools import settings

CONTENT_TYPES = [
    'sources', 'source-contents', 'skirmish-maps', 'agenda-decks', 'agenda-cards', 'command-cards',
    'condition-cards', 'deployment-cards', 'heroes', 'hero-class-cards', 'imperial-classes', 'imperial-class-cards',
    'supply-cards', 'story-mission-cards', 'side-mission-cards', 'reward-cards', 'companion-cards', 'upgrade-cards',
    'card-backs', 'threat-mission-cards', 'form-cards',
]

# Child → parent foreign keys (see docs/data-model.md in the data repo).
FOREIGN_KEYS = {
    ('agenda-cards', 'agenda_id'): 'agenda-decks',
    ('hero-class-cards', 'hero_id'): 'heroes',
    ('imperial-class-cards', 'class_id'): 'imperial-classes',
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

    def path(self, content_type):
        return self.root / 'data' / f'{content_type}.json'

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
        path = (self.root / 'schemas' / f'{content_type}.json').resolve()
        with open(path, encoding='utf-8') as f:
            return jsonref.load(f, base_uri=path.as_uri(), jsonschema=True, proxies=False)

    def image_path(self, size, relative):
        return self.root / 'images' / size / relative
