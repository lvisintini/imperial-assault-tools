"""The maintainer's scans of the sheets in the ally and villain packs and the expansions' skirmish sheets, as PDFs.

Sheets/<folder>/ holds one sheet's two scans (300 DPI PNGs). The folder names its product: a pack ("han solo",
"Weiss"), or an expansion followed by "skirmish" ("Twin Shadows skirmish"). Pages are in file-name order by their
number: Scan.png, then Scan (2).png; a folder with no plain name starts at its lowest number (Scan (3).png, then
Scan (4).png). Each sheet becomes staging/sheets/<product>-[skirmish-]rules-sheet.pdf, scaled to 200 DPI and
JPEG-compressed, and staging/sheets/manifest.json lists them for the data repo's migration.

The tools never look at the images; the maintainer pages through the PDFs.
"""
import json
import re
from pathlib import Path

from ia_tools import settings
from ia_tools.match import normalise
from ia_tools.staging import slugify

DPI = 200
QUALITY = 85
SCAN_DPI = 300
# Folder names that aren't their product's name.
ALIASES = {
    'royal champion': 'Royal Guard Champion',
    'vader': 'Darth Vader',
    'weiss': 'General Weiss',
    'bantha': 'Bantha Rider',
    'blaise': 'Agent Blaise',
    'boba': 'Boba Fett',
    'c3p0 and r2d2': 'R2-D2 and C-3PO',
    'erza bridger and kanan jarrus': 'Ezra Bridger and Kanan Jarrus',
    'grand inqusitor': 'The Grand Inquisitor',
    'hera': 'Hera Syndulla and C1-10P',
    'hired gun': 'Hired Guns',
    'hondo': 'Hondo Ohnaka',
    'jabba the hut': 'Jabba the Hutt',
    'jawa': 'Jawa Scavenger',
    'lando': 'Lando Calrissian',
    'leia': 'Leia Organa',
    'luke skywalker jedi knight': 'Luke Skywalker, Jedi Knight',
    'obi-wan': 'Obi-Wan Kenobi',
    'sorin': 'General Sorin',
}


def page_number(path):
    """Scan.png → 0, Scan (2).png and Scan(2).png → 2, Scan-1.png → 1."""
    found = re.search(r'(?: ?\((\d+)\)|-(\d+))$', path.stem)
    return int(found[1] or found[2]) if found else 0


def product_for(folder, sources):
    """(product name, skirmish) for a folder, or (None, skirmish) when nothing matches."""
    name = folder.strip()
    skirmish = name.lower().endswith(' skirmish')
    if skirmish:
        name = name[:-len(' skirmish')]
    name = ALIASES.get(name.lower(), name)
    by_name = {normalise(s['name']): s['name'] for s in sources}
    return by_name.get(normalise(name)), skirmish


def plan(scans, sources):
    """[{folder, product, name, file, pages}] for every folder of scans, and the problems found."""
    sheets, problems = [], []
    for folder in sorted(p for p in Path(scans).iterdir() if p.is_dir()):
        product, skirmish = product_for(folder.name, sources)
        pages = sorted(folder.glob('*.png'), key=page_number)
        if product is None:
            problems.append(f'{folder.name}: no product of that name (add it to ALIASES)')
            continue
        if len(pages) != 2 or len({page_number(p) for p in pages}) != 2:
            problems.append(f'{folder.name}: {len(pages)} scans; a sheet has 2 pages, numbered apart')
            continue
        name = f"{product}{' Skirmish' if skirmish else ''} Rules Sheet"
        sheets.append({'folder': folder.name, 'product': product, 'name': name, 'file': f'{slugify(name)}.pdf',
                       'pages': [p.name for p in pages]})
    files = [s['file'] for s in sheets]
    problems += [f'{file}: two folders make it' for file in sorted({f for f in files if files.count(f) > 1})]
    return sheets, problems


def write_pdf(pages, target, title):
    from PIL import Image

    images = []
    for page in pages:
        with Image.open(page) as scan:
            scale = DPI / SCAN_DPI
            images.append(scan.convert('RGB').resize((round(scan.width * scale), round(scan.height * scale)),
                                                     Image.LANCZOS))
    images[0].save(target, save_all=True, append_images=images[1:], resolution=DPI, quality=QUALITY, title=title)


def run(scans, sources, out=None, check=False, log=print):
    out = Path(out or settings.STAGING / 'sheets')
    sheets, problems = plan(scans, sources)
    if problems or check:
        return sheets, problems
    out.mkdir(parents=True, exist_ok=True)
    for sheet in sheets:
        folder = Path(scans) / sheet['folder']
        write_pdf([folder / page for page in sheet['pages']], out / sheet['file'], sheet['name'])
        sheet['bytes'] = (out / sheet['file']).stat().st_size
        log(f"  {sheet['file']} ({sheet['bytes'] / 1e6:.1f} MB): {' + '.join(sheet['pages'])}")
    (out / 'manifest.json').write_text(json.dumps({'dpi': DPI, 'quality': QUALITY, 'sheets': sheets}, indent=2),
                                       encoding='utf-8')
    return sheets, []
