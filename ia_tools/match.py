"""Match gallery names against the dataset's records."""
import re
import unicodedata
from collections import defaultdict

# boardwars product names that differ from the dataset's (from crawler/pipelines.py, plus later ones).
PRODUCT_ALIASES = {
    'corebox': 'imperialassault',
    'stormtrooper': 'stormtroopers',
    'ahsokatano': 'ahsoka',
}

# Words boardwars adds to image names that the dataset's names don't have.
NAME_NOISE = {
    'deployment-cards': re.compile(r'^(regular|elite)\s+', re.I),
    'heroes': re.compile(r'(\s+hero)?\s+(healthy|wounded)$', re.I),
    'condition-cards': re.compile(r'\s+condition$', re.I),
    'supply-cards': re.compile(r'\s+supply$', re.I),
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
        if content_type == 'sources':
            key = normalise(name)
            return self.by_name.get((content_type, PRODUCT_ALIASES.get(key, key.removesuffix('box'))), [])
        if content_type in NAME_NOISE:
            name = NAME_NOISE[content_type].sub('', name)
        key = normalise(name)
        found = self.by_name.get((content_type, key), [])
        if not found and content_type == 'deployment-cards' and key.endswith('s'):
            # boardwars pluralises units ("Elite Royal Guards"); the dataset doesn't ("Royal Guard").
            found = self.by_name.get((content_type, key[:-1]), [])
        if not found and content_type == 'heroes' and key:
            # boardwars often uses just the first name ("Diala Hero Healthy" for Diala Passil).
            found = [r for (t, k), records in self.by_name.items() if t == 'heroes' and k.startswith(key) for r in records]
            found = found if len(found) == 1 else []
        return found
