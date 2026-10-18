"""A product's staging folder: what ia scrape downloaded (manifest.json) and what the user decided in ia enter
(entries.json).

entries.json:
    {
      "product": {"action": "new", "record": {...}, "item": "0000"}      # or {"action": "existing", "id": 3}
      "items": {
        "0007": {"action": "new", "content_type": "command-cards", "record": {...}},
        "0008": {"action": "link", "content_type": "command-cards", "id": 12},     # same card already in the data
        "0009": {"action": "attach", "to": "0007", "field": "wounded"},            # extra image for another item
        "0010": {"action": "skip"},                                                 # ignore for now
        "0011": {"action": "known-skip"}                                            # never import; audits stop flagging it
      },
      "extra": {"x1": {"content_type": "agenda-decks", "record": {"name": "..."}}}  # records without an image
    }

Records leave out id and image fields (the importer assigns them). A foreign key to a record staged in the same product
is written "@<item or extra key>" and resolved on import."""
import json
import re
import unicodedata

from ia_tools import settings


def slugify(text):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    text = re.sub(r"['\"’]", '', text.replace('&', 'and'))
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


class Staging:
    def __init__(self, product_slug, root=None):
        self.slug = product_slug
        self.dir = (root or settings.STAGING) / product_slug

    @classmethod
    def all(cls, root=None):
        root = root or settings.STAGING
        return [cls(p.name, root) for p in sorted(root.iterdir()) if (p / 'manifest.json').is_file()] if root.is_dir() else []

    @property
    def manifest_path(self):
        return self.dir / 'manifest.json'

    @property
    def entries_path(self):
        return self.dir / 'entries.json'

    def manifest(self):
        return json.loads(self.manifest_path.read_text(encoding='utf-8'))

    def items(self):
        return {item['key']: item for item in self.manifest()['items']}

    def entries(self):
        if not self.entries_path.exists():
            return {'product': None, 'items': {}, 'extra': {}}
        return json.loads(self.entries_path.read_text(encoding='utf-8'))

    def save_entries(self, entries):
        tmp = self.entries_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(entries, indent=2), encoding='utf-8')
        tmp.replace(self.entries_path)
