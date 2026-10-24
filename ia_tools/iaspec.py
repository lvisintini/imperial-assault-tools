"""The dataset's iaspec rule (its tests/test_integrity.py TestCanonicalNames checks it): elite + name, then, only while
another card would get the same value, name plus one of mode, affiliation or description.

Data 2.0.0 (#32) follows the IA Skirmish Specification's practice, and has its keys (tests/fixtures/iaspec-spec.json):
`elite` only when a regular card of the same name exists, only a Campaign-only card adds its mode, and six cards keep
the spec's own spellings. Data 1.x adds `elite` to every elite, non-unique card and either mode."""
import re
import unicodedata

STRATEGIES = [('elite', 'name'), ('elite', 'name', 'modes'), ('elite', 'name', 'affiliation'),
              ('elite', 'name', 'description')]
# Data 2.0.0: the spec's spellings of cards the rule would spell otherwise.
SPEC_SPELLINGS = {
    'furyofkashyyyk': 'furyofkashyyk',
    'sarlaccsweep': 'sarlacsweep',
    'temporaryallianceimperial': 'temporaryallianceempire',
    'temporaryalliancemercenary': 'tempoaryalliancescum',
    'lukeskywalkerherooftherebellion': 'lukeskywalker',
    'lukeskywalkerjediknight': 'lukeskywalkerjedi',
}


def normalise(text):
    text = unicodedata.normalize('NFKD', text)
    return re.sub(r'[\W_]+', '', text.encode('ascii', 'ignore').decode()).lower()


def part(record, attr, regular_names=None):
    """regular_names: the names of non-elite cards (data 2.0.0), or None (1.x)."""
    value = record.get(attr)
    if attr == 'elite':
        regular = regular_names is None or normalise(record['name']) in regular_names
        return 'elite' if value and not record.get('unique') and regular else ''
    if attr == 'modes':
        if regular_names is not None:
            return 'campaign' if value == ['Campaign'] else ''
        return value[0] if value and len(value) == 1 else ''
    return value or ''


def key(record, strategy, regular_names=None):
    return normalise(''.join(part(record, attr, regular_names) for attr in strategy))


def iaspec_for(record, others, spec=False):
    """record's iaspec by the dataset's rule, given the other deployment, command and companion records; spec: the
    dataset follows the IA Skirmish Specification (data 2.0.0)."""
    regular_names = {normalise(r['name']) for r in [record, *others] if not r.get('elite')} if spec else None
    clashing = list(others)
    for strategy in STRATEGIES:
        clashing = [o for o in clashing if key(o, strategy, regular_names) == key(record, strategy, regular_names)]
        if not clashing:
            break
    value = key(record, strategy, regular_names)
    return SPEC_SPELLINGS.get(value, value) if spec else value
