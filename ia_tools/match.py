"""Match gallery names against the dataset's records."""
import re
import unicodedata
from collections import defaultdict

# boardwars product names that differ from the dataset's (from crawler/pipelines.py, plus later ones).
PRODUCT_ALIASES = {
    'corebox': 'imperialassault',
    'stormtrooper': 'stormtroopers',
}


def normalise(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower().replace('&', 'and')
    name = re.sub(r'[^a-z0-9]', '', name)
    return name.removeprefix('the')


class NameIndex:
    """Records of each content type by normalised name."""

    def __init__(self, dataset, content_types):
        self.by_name = defaultdict(list)
        for content_type in content_types:
            for record in dataset.records(content_type):
                if 'name' in record:
                    self.by_name[content_type, normalise(record['name'])].append(record)

    def find(self, content_type, name):
        key = normalise(name)
        if content_type == 'sources':
            key = PRODUCT_ALIASES.get(key, key.removesuffix('box'))
        return self.by_name.get((content_type, key), [])
