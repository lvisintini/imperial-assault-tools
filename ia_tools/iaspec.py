"""The dataset's iaspec rule (data repo commit 3bb85ed; its tests/test_integrity.py checks it): elite + name, then, only
while another card would get the same value, name plus one of mode, affiliation or description."""
import re
import unicodedata

STRATEGIES = [('elite', 'name'), ('elite', 'name', 'modes'), ('elite', 'name', 'affiliation'),
              ('elite', 'name', 'description')]


def part(record, attr):
    value = record.get(attr)
    if attr == 'elite':
        return 'elite' if value and not record.get('unique') else ''
    if attr == 'modes':
        return value[0] if value and len(value) == 1 else ''
    return value or ''


def key(record, strategy):
    text = unicodedata.normalize('NFKD', ''.join(part(record, attr) for attr in strategy))
    return re.sub(r'[\W_]+', '', text.encode('ascii', 'ignore').decode()).lower()


def iaspec_for(record, others):
    """record's iaspec by the dataset's rule, given the other deployment, command and companion records."""
    clashing = list(others)
    for strategy in STRATEGIES:
        clashing = [o for o in clashing if key(o, strategy) == key(record, strategy)]
        if not clashing:
            break
    return key(record, strategy)
