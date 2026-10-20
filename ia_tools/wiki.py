"""ia wiki: what each product contains, and how many copies of each component, from the Imperial Assault wiki
(imperial-assault.fandom.com).

The wiki's product pages list their components under headings ("Command Cards", "Condition Cards", "Other"), one bullet
each, with the count in brackets: "* [[Pummel]] (x2)". ia wiki fetches every product page the main page lists, through
the MediaWiki API (the site's pages sit behind a bot challenge; the API is the interface meant for tools), and caches
them in staging/wiki/:

    pages/<slug>.json   the API's answer for each page (wikitext and revision id), so parsing never needs the network
    products.json       every product: code, wave, dates, the dataset's source id, and its components, parsed

A component is {"headings": [...], "parent": str | None, "name", "link", "copies", "notes": [...], "raw"}: the headings
it's under (outermost first, counting the plain-text labels some pages use instead, like " [[Rebel]]"), the bullet it's
nested under, its text without the bracketed notes, the page it links to, the count (None: the page gives none, so 1),
and the other bracketed notes ("Skirmish Upgrade", a figure's name). Pages are written by hand and differ in layout, so
nothing here guesses a content type: matching components to records is up to whoever reads the cache."""
import json
import re
from collections import Counter
from datetime import datetime, timezone

from ia_tools import settings
from ia_tools.match import NameIndex, normalise
from ia_tools.staging import Staging, slugify

API_URL = 'https://imperial-assault.fandom.com/api.php'
MAIN_PAGE = 'Imperial Assault'

HEADING = re.compile(r'^(=+)\s*(.*?)\s*\1\s*$')
BULLET = re.compile(r'^(\*+)\s*(.*)$')
FILE_EMBED = re.compile(r'\[\[(?:File|Image):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]', re.I)
LINK = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]*))?\]\]')
EXTERNAL = re.compile(r'\[(https?://\S+)\s+([^\]]+)\]')
TEMPLATE = re.compile(r'\{\{[^{}]*\}\}')
TAG = re.compile(r'<[^>]+>')
NOTE = re.compile(r'\(([^()]*)\)')
COPIES = re.compile(r'^[x×]?\s*(\d+)\s*[x×]?$', re.I)  # "x2", "2x", "20"
LEADING_COUNT = re.compile(r'^(\d+)\s+(?=\D)')

# "SWI19 [[Return to Hoth]] (Big Box Expansion)" on the main page.
PRODUCT_LINE = re.compile(r'^(SWI\d+)\s+(.*)$')
DATES = re.compile(r'Announced\s+([^/]+?)\s*/\s*(?:Release[sd]?\s+)?(.+?)\)', re.I)
# The wiki's product names that differ from the dataset's beyond the "Ally Pack" / "Villain Pack" suffix, tried
# when the name itself finds nothing.
PRODUCT_ALIASES = {'coreset': 'Imperial Assault', 'lukeskywalkerjediknight': 'Luke Skywalker'}
ORDINAL = re.compile(r'(\d+)(?:st|nd|rd|th)\b')
INFOBOX_FIELD = re.compile(r'^\|\s*(\w+)\s*=\s*(.*?)\s*$', re.M)
# A product page's infobox type → the dataset's source type. The Core Set's infobox has none.
SOURCE_TYPES = {'Big Box': 'Expansion', 'Ally Pack': 'Ally Pack', 'Villain Pack': 'Villain Pack',
                'Villian Pack': 'Villain Pack'}  # Captain Terro's page


def clean(text):
    """Wiki markup → plain text."""
    text = FILE_EMBED.sub('', text)
    text = LINK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(1), text)
    text = EXTERNAL.sub(lambda m: m.group(2), text)
    text = TEMPLATE.sub('', TAG.sub('', text))
    return ' '.join(text.replace('&nbsp;', ' ').replace("'''", '').replace("''", '').split())


def component(text):
    """One bullet's text → name, link, copies and notes. Brackets inside a link ("[[Riot Trooper (Campaign)]]") are
    part of the name; brackets outside are notes, and a number among them ("x2", "20") is the count."""
    text = FILE_EMBED.sub('', text).strip()
    first = LINK.search(text) or EXTERNAL.search(text)
    link = None
    if first:
        link = first.group(1).strip() if first.re is LINK else first.group(1)
    # Notes are bracketed text outside links: blank the links out, find the brackets, then remove them from the text.
    masked = LINK.sub(lambda m: '\0' * len(m.group(0)), EXTERNAL.sub(lambda m: '\0' * len(m.group(0)), text))
    notes, copies, kept, end = [], None, [], 0
    for match in NOTE.finditer(masked):
        kept.append(text[end:match.start()])
        end = match.end()
        note = clean(text[match.start() + 1:match.end() - 1])
        if COPIES.match(note) and copies is None:
            copies = int(COPIES.match(note).group(1))
        elif note:
            notes.append(note)
    name = clean(''.join(kept) + text[end:])
    if copies is None and (count := LEADING_COUNT.match(name)):  # "4 Door Tokens", "[[Entrance Token|1 Entrance token]]"
        copies, name = int(count.group(1)), name[count.end():]
    return {'name': name, 'link': link, 'copies': copies, 'notes': notes}


def parse_contents(wikitext):
    """Every bulleted component on a product page, with the headings and parent bullet it sits under."""
    components, headings, parents = [], [], {}
    for line in wikitext.splitlines():
        if heading := HEADING.match(line):
            level = len(heading.group(1))
            headings = [h for h in headings if h[0] < level] + [(level, clean(heading.group(2)))]
            parents = {}
        elif line.startswith(' ') and line.strip() and not line.strip().startswith(('<', '{')):
            # A plain-text label (" Condition Cards", " [[Rebel]]") stands in for a heading. Pages use them beside the
            # second heading ("Included Components / Miniatures" → "Included Components / Condition Cards"), or under
            # the only one ("Deployment Cards" → "Deployment Cards / Rebel").
            level = headings[1][0] if len(headings) > 1 else (headings[0][0] + 1 if headings else 2)
            headings = [h for h in headings if h[0] < level] + [(level, clean(line))]
            parents = {}
        elif bullet := BULLET.match(line):
            depth = len(bullet.group(1))
            item = component(bullet.group(2))
            if not item['name'] and not item['link']:
                continue
            parents = {d: p for d, p in parents.items() if d < depth} | {depth: item['name']}
            components.append({
                'headings': [h for _, h in headings],
                'parent': parents.get(depth - 1),
                **item,
                'raw': line,
            })
    return components


def parse_products(wikitext):
    """The main page's product list: code, page title, wave, dates, and the product a bundled pack ships in."""
    products, wave, dates, last = [], None, (None, None), None
    for line in wikitext.splitlines():
        if heading := HEADING.match(line):
            wave = clean(heading.group(2))
            dates = (None, None)
        elif found := DATES.search(clean(line)) if 'Announced' in line else None:
            dates = (found.group(1).strip(), found.group(2).strip())
        elif bullet := BULLET.match(line):
            depth, text = len(bullet.group(1)), bullet.group(2).strip()
            code_line = PRODUCT_LINE.match(text)
            link = LINK.search(text)
            if not link:
                continue  # "SWI37 [https://... Never print]"
            product = {
                'code': code_line.group(1) if code_line else None, 'title': link.group(1).strip(),
                'label': clean(link.group(0)), 'wave': wave, 'announced': dates[0], 'released': dates[1],
                'included_in': last['title'] if depth > 1 and last else None,
            }
            products.append(product)
            if depth == 1:
                last = product
    return products


def source_for(index, label):
    """The dataset's source id for a wiki product name, or None."""
    name = re.sub(r'\s+(Ally|Villain)\s+Pack$', '', label.replace(',', ''))
    found = index.find('sources', name) or index.find('sources', PRODUCT_ALIASES.get(normalise(name), name))
    return found[0]['id'] if len(found) == 1 else None


def fetch(client, title):
    response = client.get(API_URL, params={
        'action': 'parse', 'page': title, 'prop': 'wikitext|revid', 'redirects': 1, 'format': 'json',
        'formatversion': 2})
    answer = response.json()
    if 'error' in answer:
        raise LookupError(f"{title}: {answer['error'].get('info', answer['error'])}")
    return answer


def run(client, dataset, root=None, refresh=False, log=print):
    """Fetch (or reuse) every product page and write products.json."""
    out = (root or settings.STAGING) / 'wiki'
    (out / 'pages').mkdir(parents=True, exist_ok=True)

    def page(title):
        path = out / 'pages' / f'{slugify(title)}.json'
        if refresh or not path.exists():
            path.write_text(json.dumps(fetch(client, title), indent=2), encoding='utf-8')
            log(f'fetched {title}')
        return json.loads(path.read_text(encoding='utf-8'))['parse']

    index = NameIndex(dataset, ['sources'])
    # Packs that ship inside another product (Luke and Vader in the Core Set) are sources only once the dataset models
    # them (sources.included_in); until then their names would find the stand-alone packs ("Luke Skywalker").
    bundled_packs = 'included_in' in dataset.schema('sources')['properties']
    main = page(MAIN_PAGE)
    products = []
    for product in parse_products(main['wikitext']):
        try:
            parsed = page(product['title'])
        except LookupError as error:
            log(f'skipped: {error}')
            continue
        products.append(product | {
            'page': parsed['title'], 'revid': parsed.get('revid'),
            'source_id': None if product['included_in'] and not bundled_packs
            else source_for(index, product['title']) if source_for(index, product['title']) is not None
            else source_for(index, product['label']),
            'components': parse_contents(parsed['wikitext']),
        })
    cache = {
        'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'api': API_URL,
        'main_page_revid': main.get('revid'), 'products': products,
    }
    (out / 'products.json').write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding='utf-8')
    return cache


def load(root=None):
    return json.loads(((root or settings.STAGING) / 'wiki' / 'products.json').read_text(encoding='utf-8'))


def parse_date(text):
    """A main-page date ("Aug 15th, 2014", "August 20th 2015") as YYYY-MM-DD, or None."""
    text = ' '.join(ORDINAL.sub(r'\1', (text or '').replace(',', ' ')).split())
    for pattern in ('%B %d %Y', '%b %d %Y'):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def infobox(wikitext):
    """A product page's infobox fields ("| sku = SWI30"), by lower-cased name; the first of each wins."""
    fields = {}
    for name, value in INFOBOX_FIELD.findall(wikitext):
        fields.setdefault(name.lower(), value)
    return fields


def source_values(product, wikitext):
    """A cached product's values for the dataset's sources fields, and notes on anything the wiki leaves unclear.
    Dates and wave come from the main page (announced dates are only there, once per wave), the type from the
    product page's infobox. Big boxes take the wave they were announced with; the Core Set is wave 0."""
    box = infobox(wikitext)
    core = product['code'] == 'SWI01'
    wave = re.fullmatch(r'Wave (\d+)', product['wave'] or '')
    values = {
        'product_code': product['code'],
        'announced_date': parse_date(product['announced']),
        'release_date': parse_date(product['released']),
        'wave': 0 if core else int(wave.group(1)) if wave else None,
    }
    notes = [f'unreadable {field} date {product[field]!r}'
             for field, value in (('announced', values['announced_date']), ('released', values['release_date']))
             if product[field] and not value]
    if box.get('release_date') and box['release_date'] != values['release_date']:
        notes.append(f"the product page says released {box['release_date']}")
    kind = 'Core Game' if core else SOURCE_TYPES.get(box.get('type'))
    if kind:
        values['type'] = kind
    elif box.get('type'):
        notes.append(f"unknown infobox type {box['type']!r}")
    return values, notes


def propose_sources(dataset, folder, root=None):
    """Stage an ia propose edit for every source whose fields differ from the wiki cache's values, to decide in
    ia enter. Sources that already have a proposal in the folder are left alone, so this can be run again.
    Returns the new proposals' keys."""
    from ia_tools import edits  # edits imports the importer; keep ia wiki's own imports light

    pages = (root or settings.STAGING) / 'wiki' / 'pages'
    staging = Staging(folder, root)
    staged = {e['id'] for e in staging.manifest().get('edits', []) if e['content_type'] == 'sources'} \
        if staging.manifest_path.exists() else set()
    products = load(root)['products']
    shared = [i for i, n in Counter(p['source_id'] for p in products if p['source_id'] is not None).items() if n > 1]
    if shared:
        raise ValueError(f'Several wiki products match source {", ".join(map(str, shared))}; fix the cache first')
    keys = []
    for product in products:
        source_id = product['source_id']
        if source_id is None or source_id in staged:
            continue
        page = json.loads((pages / f"{slugify(product['title'])}.json").read_text(encoding='utf-8'))['parse']
        values, notes = source_values(product, page['wikitext'])
        record = edits.find(dataset, 'sources', source_id)
        changes = {field: value for field, value in values.items() if record.get(field) != value}
        if changes:
            note = '; '.join([f"From the wiki: {product['page']} (revision {product['revid']})"] + notes)
            keys.append(edits.propose(dataset, folder, 'sources', source_id, changes, note=note, root=root))
            staged.add(source_id)
    return keys
