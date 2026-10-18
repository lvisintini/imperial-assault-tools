"""ia scrape: download one boardwars album (a product, or the skirmish maps) into a staging folder."""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from PIL import Image

from ia_tools import boardwars
from ia_tools.classify import BACK_KEYS, classify
from ia_tools.dataset import CONTENT_TYPES
from ia_tools.match import NameIndex
from ia_tools.staging import Staging, slugify


def run(client, dataset, url, product=None, root=None, log=print):
    images = list(boardwars.crawl(client, url))
    guesses = [classify(image) for image in images]
    product = product or next((g.product for g in guesses if g.product), None)
    if not product:
        raise SystemExit('Could not tell the product from the album; pass --product')
    staging = Staging(slugify(product), root)
    (staging.dir / 'originals').mkdir(parents=True, exist_ok=True)
    index = NameIndex(dataset, [t for t in CONTENT_TYPES if t not in ('source-contents', 'card-backs')])

    items = []
    for n, (image, guess) in enumerate(zip(images, guesses)):
        key = f'{n:04d}'
        suffix = PurePosixPath(unquote(urlsplit(image.url).path)).suffix.lower()
        file = f'originals/{key}-{slugify(image.name) or "image"}{suffix}'
        target = staging.dir / file
        content = target.read_bytes() if target.exists() else client.get(image.url).content
        target.write_bytes(content)
        with Image.open(io.BytesIO(content)) as im:  # metadata only
            width, height, fmt = im.width, im.height, im.format
        back_type = BACK_KEYS.get(guess.back_of, guess.back_of) if guess.content_type == 'card-backs' else None
        items.append({
            'key': key, 'path': list(image.path), 'name': image.name, 'url': image.url, 'file': file,
            'sha512': hashlib.sha512(content).hexdigest(), 'bytes': len(content),
            'width': width, 'height': height, 'format': fmt,
            'guess': {'content_type': guess.content_type, 'back_content_type': back_type, 'hints': guess.hints},
            'matches': [
                {'content_type': guess.content_type, 'id': r['id'], 'name': r['name']}
                for r in (index.find(guess.content_type, image.name) if guess.content_type not in (None, 'card-backs') else [])
                if 'id' in r
            ],
        })
        log(f'{key} {guess.content_type or "?":22} {image.name}')

    manifest = {
        'product': product, 'url': url, 'scraped': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'existing_product': [{'id': r['id'], 'name': r['name']} for r in index.find('sources', product)],
        'items': items,
    }
    staging.manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return staging, manifest
