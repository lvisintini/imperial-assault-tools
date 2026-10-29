"""The maintainer's scans of the sheets in the ally and villain packs and the expansions' skirmish sheets, as PDFs.

Sheets/<folder>/ holds one sheet's two scans (300 DPI PNGs), or a two-page PDF of it (a scanner's, or a printed one
whose pages are drawn in strips). The folder names its product: a pack ("han solo", "Weiss"), or an expansion followed
by "skirmish" ("Twin Shadows skirmish"). Scans are in file-name order by their number: Scan.png, then Scan (2).png; a
folder with no plain name starts at its lowest number (Scan (3).png, then Scan (4).png). A PDF's pages are rebuilt
from the images they draw, at those images' resolution. Each sheet becomes
staging/sheets/<product>-[skirmish-]rules-sheet.pdf, scaled to 200 DPI and JPEG-compressed, and
staging/sheets/manifest.json lists them for the data repo's migration.

The tools never look at the images; the maintainer pages through the PDFs.
"""
import json
import math
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ContentStream

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
        scans, pdfs = sorted(folder.glob('*.png'), key=page_number), sorted(folder.glob('*.pdf'))
        if product is None:
            problems.append(f'{folder.name}: no product of that name (add it to ALIASES)')
            continue
        if pdfs:
            count = len(PdfReader(pdfs[0]).pages) if len(pdfs) == 1 else 0
            if scans or count != 2:
                problems.append(f'{folder.name}: a sheet is one PDF of 2 pages, with no scans beside it')
                continue
            pages = [f'{pdfs[0].name}#{n}' for n in (1, 2)]
        elif len(scans) != 2 or len({page_number(p) for p in scans}) != 2:
            problems.append(f'{folder.name}: {len(scans)} scans; a sheet has 2 pages, numbered apart')
            continue
        else:
            pages = [p.name for p in scans]
        name = f"{product}{' Skirmish' if skirmish else ''} Rules Sheet"
        sheets.append({'folder': folder.name, 'product': product, 'name': name, 'file': f'{slugify(name)}.pdf',
                       'pages': pages})
    files = [s['file'] for s in sheets]
    problems += [f'{file}: two folders make it' for file in sorted({f for f in files if files.count(f) > 1})]
    return sheets, problems


def multiply(m, n):
    """PDF matrices [a b c d e f]: m, then n."""
    return [m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3], m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
            m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5]]


def pdf_page(path, number):
    """(image, DPI) of a PDF's page (1-based) that only draws images: one scan (which the scanner may have drawn
    slightly turned, to straighten it), or strips. The page is rebuilt at the resolution of its sharpest image, so
    strips join without seams; clipping paths are ignored."""
    import numpy as np
    from PIL import Image

    page = PdfReader(path).pages[number - 1]
    where = f'{Path(path).name} page {number}'
    if page.get('/Rotate', 0) % 360:
        raise ValueError(f'{where} is rotated')
    xobjects = page['/Resources'].get('/XObject', {})
    placed, stack, ctm = [], [], [1, 0, 0, 1, 0, 0]
    for operands, operator in ContentStream(page.get_contents(), page.pdf).operations:
        if operator == b'q':
            stack.append(ctm)
        elif operator == b'Q':
            ctm = stack.pop()
        elif operator == b'cm':
            ctm = multiply([float(x) for x in operands], ctm)
        elif operator == b'Do':
            xobject = xobjects[operands[0]].get_object()
            if xobject['/Subtype'] != '/Image':
                raise ValueError(f'{where} draws something other than images')
            placed.append((xobject, ctm))
    if not placed:
        raise ValueError(f'{where} has no images')
    box = page.mediabox
    left, top = float(box.left), float(box.top)
    scale = max(x['/Width'] / math.hypot(m[0], m[1]) for x, m in placed)  # pixels per point
    canvas = Image.new('RGB', (round(float(box.width) * scale), round(float(box.height) * scale)), 'white')
    for xobject, (a, b, c, d, e, f) in placed:
        image = xobject.decode_as_image().convert('RGB')
        width, height = image.size
        # Image pixel (u, v), v down → the unit square (u / width, 1 - v / height) → the page, by the CTM → the
        # canvas, y down.
        to_unit = np.array([[1 / width, 0, 0], [0, -1 / height, 1], [0, 0, 1]])
        to_page = np.array([[a, c, e], [b, d, f], [0, 0, 1]])
        to_canvas = np.array([[scale, 0, -left * scale], [0, -scale, top * scale], [0, 0, 1]])
        forward = to_canvas @ to_page @ to_unit
        corners = forward @ np.array([[0, width, 0, width], [0, 0, height, height], [1, 1, 1, 1]])
        x0, y0 = np.floor(corners[:2].min(axis=1)).astype(int)
        x1, y1 = np.ceil(corners[:2].max(axis=1)).astype(int)
        # Pillow maps each output pixel back to the image: the inverse, from the bounding box's corner.
        inverse = np.linalg.inv(np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]]) @ forward)
        data = tuple(inverse[:2].flatten())
        size = (int(x1 - x0), int(y1 - y0))
        drawn = image.transform(size, Image.AFFINE, data, Image.BICUBIC)
        mask = Image.new('L', image.size, 255).transform(size, Image.AFFINE, data, Image.NEAREST)
        canvas.paste(drawn, (int(x0), int(y0)), mask)
    return canvas, scale * 72


def page_image(folder, page):
    """(image, DPI) of a sheet's page: a scan, or "<file>.pdf#<n>"."""
    from PIL import Image

    if '.pdf#' in page:
        file, number = page.rsplit('#', 1)
        return pdf_page(folder / file, int(number))
    with Image.open(folder / page) as scan:
        return scan.convert('RGB'), SCAN_DPI


def write_pdf(pages, target, title):
    """pages: (image, DPI) each, scaled to DPI."""
    from PIL import Image

    images = [image.resize((round(image.width * DPI / dpi), round(image.height * DPI / dpi)), Image.LANCZOS)
              for image, dpi in pages]
    images[0].save(target, save_all=True, append_images=images[1:], resolution=DPI, quality=QUALITY, title=title)


def run(scans, sources, out=None, check=False, log=print):
    out = Path(out or settings.STAGING / 'sheets')
    sheets, problems = plan(scans, sources)
    if problems or check:
        return sheets, problems
    out.mkdir(parents=True, exist_ok=True)
    for sheet in sheets:
        folder = Path(scans) / sheet['folder']
        write_pdf([page_image(folder, page) for page in sheet['pages']], out / sheet['file'], sheet['name'])
        sheet['bytes'] = (out / sheet['file']).stat().st_size
        log(f"  {sheet['file']} ({sheet['bytes'] / 1e6:.1f} MB): {' + '.join(sheet['pages'])}")
    (out / 'manifest.json').write_text(json.dumps({'dpi': DPI, 'quality': QUALITY, 'sheets': sheets}, indent=2),
                                       encoding='utf-8')
    return sheets, []
