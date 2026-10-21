"""ia stage: stage images that aren't on boardwars, for ia enter and ia import like a scraped product.

Two sources:
- image files: each is an item, guessed as the given content type;
- a Tabletop Simulator saved object (`--tts`, the .json or a .zip holding it and its Mods/Images): every card's face
  is an item, guessed as the given type, and every distinct back is an item guessed as that type's card back. Items
  are named by position ("Card 3", "Back B, of cards 3 and 4"), since saves rarely name their cards.

The staging folder (staging/<slug>/) gets the originals and a manifest in the scraper's format; items have no product
unless --product names an existing one. Where the images came from is recorded in each item's `url` (a file path or
the save's image URL), and in the manifest's `urls`."""
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ia_tools.dataset import INDEX_TYPES
from ia_tools.match import NameIndex
from ia_tools.staging import Staging, slugify


def tts_cards(path):
    """[(name, bytes, url, is_back)] from a TTS saved object: faces in deck order, then each distinct back."""
    path = Path(path)
    archive = zipfile.ZipFile(path) if path.suffix.lower() == '.zip' else None
    save_name = next((n for n in archive.namelist() if n.endswith('.json')), None) if archive else None
    save = json.loads(archive.read(save_name) if archive else path.read_text(encoding='utf-8'))

    def image(url):
        if archive is None:
            raise ValueError(f'{path} is a bare save: its images ({url}) are not included; stage the .zip')
        cached = 'Mods/Images/' + ''.join(c for c in url if c.isalnum())
        name = next((n for n in archive.namelist() if n.rsplit('.', 1)[0] == cached), None)
        if name is None:
            raise ValueError(f'{url} is not in {path}')
        return archive.read(name)

    def cards(objects):
        for obj in objects:
            if obj.get('Name', '').startswith('Card'):
                (deck,) = obj['CustomDeck'].values()
                yield obj, deck
            yield from cards(obj.get('ContainedObjects') or [])

    faces, backs = [], {}
    for n, (obj, deck) in enumerate(cards(save['ObjectStates']), 1):
        if deck.get('NumWidth', 1) != 1 or deck.get('NumHeight', 1) != 1:
            raise ValueError(f'card {n} is on a sheet of {deck["NumWidth"]}x{deck["NumHeight"]}; only single-card images')
        faces.append((obj.get('Nickname') or f'Card {n}', image(deck['FaceURL']), deck['FaceURL'], False))
        backs.setdefault(deck['BackURL'], []).append(n)
    lettered = []
    for i, (url, numbers) in enumerate(backs.items()):
        of = f'card {numbers[0]}' if len(numbers) == 1 else 'cards ' + ' and '.join(map(str, numbers))
        lettered.append((f'Back {chr(65 + i)}, of {of}', image(url), url, True))
    return faces + lettered


def run(dataset, slug, content_type, files=(), tts=None, product=None, root=None, log=print):
    sources = [(Path(f).stem, Path(f).read_bytes(), str(Path(f).resolve()), False) for f in files]
    if tts:
        sources += tts_cards(tts)
    if not sources:
        raise ValueError('nothing to stage: give image files or --tts')
    staging = Staging(slug, root)
    (staging.dir / 'originals').mkdir(parents=True, exist_ok=True)
    index = NameIndex(dataset, dataset.content_types(exclude=INDEX_TYPES + ['card-backs']))
    found = index.find('sources', product) if product else []
    if product and len(found) != 1:
        raise ValueError(f'product {product!r} is not one existing source')
    source = {'id': found[0]['id'], 'name': found[0]['name']} if found else None

    items = []
    for n, (name, content, url, is_back) in enumerate(sources):
        key = f'{n:04d}'
        with Image.open(io.BytesIO(content)) as im:  # metadata only
            width, height, fmt = im.width, im.height, im.format
        file = f'originals/{key}-{slugify(name) or "image"}.{fmt.lower().replace("jpeg", "jpg")}'
        (staging.dir / file).write_bytes(content)
        items.append({
            'key': key, 'path': [], 'name': name, 'url': url, 'file': file,
            'sha512': hashlib.sha512(content).hexdigest(), 'bytes': len(content),
            'width': width, 'height': height, 'format': fmt,
            'guess': {'content_type': 'card-backs' if is_back else content_type,
                      'back_content_type': content_type if is_back else None, 'hints': {}},
            'source': source,
            'matches': [],
        })
        log(f'{key} {"card-backs" if is_back else content_type:22} {name}')
    manifest = {
        'product': product, 'urls': [str(Path(tts).resolve())] if tts else [str(Path(f).resolve()) for f in files],
        'scraped': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'existing_product': [source] if source else [], 'items': items,
    }
    staging.manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return staging, manifest
