"""Match gallery names against the dataset's records."""
import re
import unicodedata
from collections import defaultdict

# boardwars product names that differ from the dataset's (from crawler/pipelines.py, plus later ones).
PRODUCT_ALIASES = {
    'corebox': 'imperialassault',
    'stormtrooper': 'stormtroopers',
    'ahsokatano': 'ahsoka',
    'wookiewarriors': 'wookieewarriors',
}

# boardwars card names that differ from the dataset's (misspellings, a plural with no elite version beside it).
NAME_ALIASES = {
    'wookiewarrior': 'wookieewarrior',
    'ewebenigneer': 'ewebengineer',
    'echobasetroopers': 'echobasetrooper',
    'emergencymedpack': 'emergencymedpac',
    'tatooinehuntungrifle': 'tatooinehuntingrifle',
    'scouringofthehoumestead': 'scouringofthehomestead',
}

# Words boardwars adds to image names that the dataset's names don't have (deployment cards: parse_deployment_name).
NAME_NOISE = {
    'heroes': re.compile(r'(\s+hero)?\s+(healthy|wounded)$', re.I),
    'condition-cards': re.compile(r'\s+condition$', re.I),
    'supply-cards': re.compile(r'\s+supply$', re.I),
    'command-cards': re.compile(r'\s+command card$', re.I),
    'companion-cards': re.compile(r'\s+companion$', re.I),
    'form-cards': re.compile(r'^clawdite form\s+', re.I),
}

# Words boardwars puts in deployment card image names; the dataset keeps them in `elite` and `modes` instead.
DEPLOYMENT_MARKERS = re.compile(r'\b(elite|regular|campaign|skirmish)\b', re.I)


def normalise(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower().replace('&', 'and')
    name = re.sub(r'[^a-z0-9]', '', name)
    return name.removeprefix('the')


def parse_deployment_name(raw):
    """boardwars image name → (name, 'elite' | 'regular' | None, modes): 'Elite Death Troopers campaign' →
    ('Death Troopers', 'elite', ['Campaign'])."""
    text = raw.replace('-', ' ') if '_' in raw else raw  # 'Elite-Royal-Guard_errata'
    text = re.sub(r'\b(errata|deployment card)\b', ' ', text.replace('_', ' '), flags=re.I)
    marks = [m.lower() for m in DEPLOYMENT_MARKERS.findall(text)]
    name = ' '.join(DEPLOYMENT_MARKERS.sub(' ', text).split()).strip(' -')
    grade = 'elite' if 'elite' in marks else 'regular' if 'regular' in marks else None
    return name, grade, [m.title() for m in marks if m in ('campaign', 'skirmish')]


def deployment_fits(record, grade, modes, affiliation):
    """Whether a deployment record is the card a parsed boardwars name and album describe."""
    if grade and record['elite'] != (grade == 'elite'):
        return False
    if modes and record['modes'] != modes:
        return False
    return not affiliation or record['affiliation'].lower()[:5] == affiliation.lower()[:5]  # "Mercenaries"


class NameIndex:
    """Records of each content type by normalised name (deployment cards also by name + subtitle)."""

    def __init__(self, dataset, content_types):
        self.by_name = defaultdict(list)
        for content_type in content_types:
            for record in dataset.records(content_type):
                if 'name' in record:
                    self.by_name[content_type, normalise(record['name'])].append(record)
                if content_type == 'deployment-cards' and record.get('description'):
                    self.by_name[content_type, normalise(record['name'] + record['description'])].append(record)

    def find(self, content_type, name, hints=None):
        if content_type == 'sources':
            key = normalise(name)
            # The plain name too: a dataset from before a rename ("Wookie Warriors", fixed in data 1.3.2).
            return (self.by_name.get((content_type, PRODUCT_ALIASES.get(key, key.removesuffix('box'))), [])
                    or self.by_name.get((content_type, key), []))
        if content_type == 'deployment-cards':
            return self.find_deployment(name, (hints or {}).get('affiliation'))
        if content_type in NAME_NOISE:
            name = NAME_NOISE[content_type].sub('', name)
        key = normalise(name)
        found = self.by_name.get((content_type, NAME_ALIASES.get(key, key)), [])
        if not found and content_type == 'heroes' and key:
            # boardwars often uses just the first name ("Diala Hero Healthy" for Diala Passil).
            found = [r for (t, k), records in self.by_name.items() if t == 'heroes' and k.startswith(key) for r in records]
            found = found if len(found) == 1 else []
        return found

    def find_deployment(self, raw, affiliation=None):
        name, grade, modes = parse_deployment_name(raw)
        key = normalise(name)
        # boardwars pluralises units ("Elite Royal Guards"); the dataset doesn't ("Royal Guard").
        keys = [key, key[:-1]] if key.endswith('s') else [key]
        found = next((f for k in keys if (f := self.by_name.get(('deployment-cards', NAME_ALIASES.get(k, k)), []))), [])
        found = [r for r in found if deployment_fits(r, grade, modes, affiliation)]
        if not grade and any(r['elite'] for r in found) and any(not r['elite'] for r in found):
            found = [r for r in found if not r['elite']]  # unmarked means regular ("Stormtrooper", "Elite Stormtrooper")
        return found
