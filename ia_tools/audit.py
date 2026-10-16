"""ia audit: crawl the whole gallery, hash every original, and report what the dataset may be missing.

The SHA-512 register (settings.SEEN_HASHES) holds every original the 2017–18 batches downloaded, and boardwars still
serves the same files, so an unseen hash is a candidate gap. Images are hashed in memory and never saved."""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from ia_tools import boardwars, settings
from ia_tools.classify import classify
from ia_tools.dataset import CONTENT_TYPES
from ia_tools.match import NameIndex

# seen-*: the hash is in the register. unseen-known: not in the register, but a record with that type and name exists
# (probably a re-uploaded scan). unseen: a candidate gap. skipped: listed in known-skipped-sha512.txt.
STATUSES = ['unseen', 'unseen-known', 'seen-no-record', 'seen', 'skipped']


def load_hashes(path):
    return set(path.read_text().split()) if path.exists() else set()


def status_of(sha512, guess, image, index, seen, skipped):
    if sha512 in skipped:
        return 'skipped'
    if guess.content_type == 'sources':  # box images are called "Box", "Pack", ...: match by product
        named = bool(index.find('sources', guess.product))
    else:
        named = guess.content_type not in (None, 'card-backs') and bool(index.find(guess.content_type, image.name))
    if sha512 in seen:
        return 'seen' if named or guess.content_type == 'card-backs' else 'seen-no-record'
    return 'unseen-known' if named else 'unseen'


def run(client, dataset, out_dir, start_url=boardwars.BASE_URL, log=print):
    out_dir.mkdir(parents=True, exist_ok=True)
    # url → hash, appended as we go so an interrupted audit picks up where it stopped.
    cache_path = out_dir / 'hashes.jsonl'
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            entry = json.loads(line)
            cache[entry['url']] = entry
    seen, skipped = load_hashes(settings.SEEN_HASHES), load_hashes(settings.SKIPPED_HASHES)
    index = NameIndex(dataset, [t for t in CONTENT_TYPES if t not in ('source-contents', 'card-backs')])

    entries = []
    with open(cache_path, 'a') as cache_file:
        for n, image in enumerate(boardwars.crawl(client, start_url), 1):
            hashed = cache.get(image.url)
            if not hashed:
                content = client.get(image.url).content
                hashed = {'url': image.url, 'sha512': hashlib.sha512(content).hexdigest(), 'bytes': len(content)}
                cache_file.write(json.dumps(hashed) + '\n')
                cache_file.flush()
            entries.append(entry(image, hashed, index, seen, skipped))
            if n % 50 == 0:
                log(f'{n} images audited', flush=True)
    return write_report(entries, index, seen, start_url, out_dir)


def entry(image, hashed, index, seen, skipped):
    guess = classify(image)
    return {
        'path': list(image.path), 'name': image.name, 'url': image.url, 'sha512': hashed['sha512'],
        'bytes': hashed['bytes'], 'product': guess.product, 'content_type': guess.content_type,
        'back_of': guess.back_of, 'hints': guess.hints,
        'status': status_of(hashed['sha512'], guess, image, index, seen, skipped),
    }


def rescore(dataset, out_dir):
    """Rebuild the report from the last run's entries, with today's classification, matching and hash lists, without
    crawling again."""
    previous = json.loads((out_dir / 'report.json').read_text(encoding='utf-8'))
    seen, skipped = load_hashes(settings.SEEN_HASHES), load_hashes(settings.SKIPPED_HASHES)
    index = NameIndex(dataset, [t for t in CONTENT_TYPES if t not in ('source-contents', 'card-backs')])
    entries = [
        entry(boardwars.ImageRef(path=tuple(boardwars.clean_title(p) for p in e['path']), name=e['name'], url=e['url']),
              e, index, seen, skipped)
        for e in previous['entries']
    ]
    return write_report(entries, index, seen, previous['start_url'], out_dir)


def write_report(entries, index, seen, start_url, out_dir):
    products = sorted({e['product'] for e in entries if e['product']})
    report = {
        'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'start_url': start_url,
        'counts': dict(Counter(e['status'] for e in entries)),
        'register_size': len(seen),
        'register_hashes_found': len(seen & {e['sha512'] for e in entries}),
        'products_missing_from_dataset': [p for p in products if not index.find('sources', p)],
        'entries': entries,
    }
    (out_dir / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (out_dir / 'report.md').write_text(markdown(report), encoding='utf-8')
    return report


def markdown(report):
    lines = [
        '# boardwars audit', '',
        f"Generated {report['generated']} from {report['start_url']}.", '',
        '| Status | Images |', '|---|---|',
        *[f"| {s} | {report['counts'].get(s, 0)} |" for s in STATUSES],
        '',
        f"{report['register_hashes_found']} of the register's {report['register_size']} hashes were found on boardwars.",
        '',
        '## Products not in the dataset', '',
        *([f'- {p}' for p in report['products_missing_from_dataset']] or ['None.']),
        '',
    ]
    by_album = defaultdict(list)
    for entry in report['entries']:
        if entry['status'] in ('unseen', 'unseen-known', 'seen-no-record'):
            by_album[' / '.join(entry['path'])].append(entry)
    lines += ['## Images to triage, by album', '']
    for album in sorted(by_album):
        lines += [f'### {album}', '', '| Status | Name | Guessed type | Original |', '|---|---|---|---|']
        for e in sorted(by_album[album], key=lambda e: (STATUSES.index(e['status']), e['name'])):
            kind = f"back of {e['back_of']}" if e['content_type'] == 'card-backs' else e['content_type'] or '?'
            lines.append(f"| {e['status']} | {e['name']} | {kind} | [file]({e['url']}) |")
        lines.append('')
    return '\n'.join(lines)
