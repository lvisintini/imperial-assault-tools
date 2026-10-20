"""ia scrape: download boardwars albums (a product, part of one, or the skirmish maps), or every gap the last audit
found, into a staging folder."""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from PIL import Image

from ia_tools import boardwars
from ia_tools.classify import BACK_KEYS, SKIRMISH_MAP_PRODUCTS, classify, product_of
from ia_tools.dataset import CONTENT_TYPES
from ia_tools.match import NameIndex
from ia_tools.staging import Staging, slugify


def album_key(url):
    return unquote(urlsplit(url).path).rstrip('/')


def cover_image(client, url, images):
    """The album's cover as an image, when it isn't one of the album's own images: ally and villain packs keep their
    box image there ("Thrawn Pack.png"), shown on the wave's page but not listed in the pack's album."""
    parent = url.rstrip('/').rsplit('/', 1)[0] + '/'
    page = boardwars.parse_album_page(client.get(parent).text, parent)
    cover = next((c for album, c in page.covers.items() if album_key(album) == album_key(url)), None)
    if not cover or not images or album_key(cover) in {album_key(i.url) for i in images}:
        return None
    _, start = product_of(images[0].path)
    name = PurePosixPath(unquote(urlsplit(cover).path)).stem
    return boardwars.ImageRef(path=images[0].path[:start], name=name, url=cover)


def run(client, dataset, urls, product=None, root=None, log=print, folder=None):
    """Stage every image in the albums at urls into staging/<folder or the product's slug>/."""
    urls = [urls] if isinstance(urls, str) else list(urls)
    images = list(dict.fromkeys(image for url in urls for image in boardwars.crawl(client, url)))
    guesses = [classify(image) for image in images]
    if not any(g.content_type == 'sources' for g in guesses):
        cover = cover_image(client, urls[0], images)
        if cover:
            images.insert(0, cover)
            guesses.insert(0, classify(cover))
    product = product or next((g.product for g in guesses if g.product), None)
    if not product:
        raise SystemExit('Could not tell the product from the album; pass --product')
    return stage(client, dataset, images, guesses, Staging(folder or slugify(product), root), product, urls, log)


def gaps(client, dataset, report, root=None, log=print, folder='gaps'):
    """Stage every image the last audit found unseen into one folder. They come from many products, so each staged
    image names its own (see item_source); the folder has none."""
    entries = [e for e in report['entries'] if e['status'] == 'unseen']
    if not entries:
        raise SystemExit('The last audit found no unseen images')
    images = [boardwars.ImageRef(path=tuple(e['path']), name=e['name'], url=e['url']) for e in entries]
    return stage(client, dataset, images, [classify(image) for image in images], Staging(folder, root), None,
                 [report['start_url']], log)


def item_source(index, image, guess, product):
    """The existing product an image belongs to, when the dataset has it: the album's, or for a skirmish map the one
    SKIRMISH_MAP_PRODUCTS names, or else the folder's."""
    name = guess.product or (SKIRMISH_MAP_PRODUCTS.get(image.name) if guess.content_type == 'skirmish-maps' else None)
    found = index.find('sources', name or product) if (name or product) else []
    return {'id': found[0]['id'], 'name': found[0]['name']} if len(found) == 1 else None


def stage(client, dataset, images, guesses, staging, product, urls, log):
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
            'source': item_source(index, image, guess, product),
            'matches': [
                {'content_type': guess.content_type, 'id': r['id'], 'name': r['name']}
                for r in (index.find(guess.content_type, image.name, guess.hints)
                          if guess.content_type not in (None, 'card-backs') else [])
                if 'id' in r
            ],
        })
        log(f'{key} {guess.content_type or "?":22} {image.name}')

    manifest = {
        'product': product, 'urls': urls, 'scraped': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'existing_product': [{'id': r['id'], 'name': r['name']} for r in index.find('sources', product)] if product else [],
        'items': items,
    }
    staging.manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return staging, manifest
