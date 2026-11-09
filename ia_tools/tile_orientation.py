"""Tile sides with their number pills upright.

Every tile side has a pill in a corner with its code: the product's icon, two digits and a smaller A or B ("01A").
The scans in tiles/ are ~299 px per square, enough to read it; our stored images are read at 128 px per square
(OURS_PX: the hi-res tiles' size since `ia hires-tiles --write`), where its text is about 11 px tall.

1. Bootstrap: find pill-sized light rounded rectangles in each scan and keep the ones that segment as an upright
   pill (two tall glyphs, then a shorter one on their baseline); their crops make each product's pill template, and
   their glyphs' boxes the product's glyph cells.
2. Each scan: its product's template matched at the 4 quarter turns finds its pill and which way up it reads.
3. Each scan's code: its glyph cells read by their nearest neighbours among every other scan's (labelled with those
   sides' codes; Tesseract can't read the pills' font), so a scan reading another side's code shows.
4. Each of our images: turned like the scan's registration onto it (`ia hires-tiles`), checked by matching the pill
   template, shrunk to its scale, at the 4 turns; its code read like the scans' (its own scan and the scan's copies
   don't vote).

Turns are clockwise degrees that make an image's pill upright. The maintainer's rulings (rulings.json: {side key:
{"scan": turn, "ours": turn}}) override them.
"""
import hashlib
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from ia_tools import settings

SCAN_PX = 299
PILL_H = 44  # a pill crop's height once normalised, px
INSET = 3  # px of a normalised crop that are the pill's frame
CELL_PAD = 3
SHIFTS = [(dx, dy) for dx in (-4, -2, 0, 2, 4) for dy in (-2, 0, 2)]
NEIGHBOURS = 7
MARGIN = 0.15  # a turn's template score must beat the next turn's by this much
SURE = 0.6  # a glyph's share of its neighbours' votes
OURS_PX = 128


def out_dir():
    return settings.STAGING / 'tile-orientation'


def code_of(tile, side):
    return f"{tile['number']:02d}{side}"


def turn_of_k(k):
    """Clockwise degrees for k counter-clockwise quarter turns (np.rot90)."""
    return (-90 * k) % 360


def k_of_turn(turn):
    return (-turn // 90) % 4


# Bootstrap: pills found by their shape -------------------------------------------------------------------------------

def pill_boxes(scan, px=SCAN_PX):
    """[(x, y, w, h)] light rounded rectangles of a pill's size inside a scan's outline (px per square)."""
    import cv2
    import numpy as np

    inside = scan[..., 3] > 127
    gray = cv2.GaussianBlur(cv2.cvtColor(scan[..., :3], cv2.COLOR_RGB2GRAY), (3, 3), 0)
    found = []
    for lo, hi in ((20, 60), (40, 120), (60, 160), (10, 40)):
        edges = cv2.dilate(cv2.Canny(gray, lo, hi), np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            short, long = sorted((w, h))
            if not (0.09 * px <= short <= 0.22 * px and 0.25 * px <= long <= 0.52 * px and 1.7 <= long / short <= 3.4):
                continue
            if cv2.contourArea(cv2.convexHull(contour)) / (w * h) < 0.85 or not inside[y:y + h, x:x + w].all():
                continue
            if all(abs(x - o[0]) > 8 or abs(y - o[1]) > 8 for o in found):
                found.append((x, y, w, h))
    return found


def normalise(gray, box, k):
    """A crop of gray at box, turned k quarter turns counter-clockwise, scaled to PILL_H tall."""
    import cv2
    import numpy as np

    x, y, w, h = box
    crop = np.ascontiguousarray(np.rot90(gray[y:y + h, x:x + w], k))
    return cv2.resize(crop, (round(crop.shape[1] * PILL_H / crop.shape[0]), PILL_H), interpolation=cv2.INTER_CUBIC)


def glyph_boxes(crop):
    """[(x, y, w, h)] a normalised pill crop's two digits and letter, or None when it doesn't read as an upright pill:
    three tall glyphs (narrower than the icon at the left), the last shorter and on the digits' baseline."""
    import cv2

    h, w = crop.shape
    _, dark = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dark[:INSET], dark[-INSET:], dark[:, :INSET], dark[:, -INSET:] = 0, 0, 0, 0
    n, _, stats, _ = cv2.connectedComponentsWithStats(dark)
    shapes = sorted(tuple(int(v) for v in stats[i][:4]) for i in range(1, n)
                    if stats[i][4] >= 25 and stats[i][0] > INSET and stats[i][1] > INSET
                    and stats[i][0] + stats[i][2] < w - INSET and stats[i][1] + stats[i][3] < h - INSET)
    tall = [s for s in shapes if s[3] >= 0.45 * h and s[2] < 0.5 * h]
    if len(tall) < 3 or tall[-3][0] < 0.25 * w:
        return None
    d1, d2, letter = tall[-3:]
    digit_h = min(d1[3], d2[3])
    bottom = max(d1[1] + d1[3], d2[1] + d2[3])
    if digit_h < 0.6 * h or letter[3] >= 0.9 * digit_h or abs(letter[1] + letter[3] - bottom) > 0.08 * h:
        return None
    return [d1, d2, letter]


def templates(grays):
    """{product: (template, cells)} from the scans' pills that read upright by their shape: the mean crop (at the
    median size) and the median glyph boxes in a normalised crop. grays: {key: (product, gray, scan)}."""
    import cv2
    import numpy as np

    crops, sizes, cells = defaultdict(list), defaultdict(list), defaultdict(list)
    for key, (product, gray, scan) in grays.items():
        upright = []
        for box in pill_boxes(scan):
            for k in ((0, 2) if box[2] > box[3] else (1, 3)):
                cells_of = glyph_boxes(normalise(gray, box, k))
                if cells_of:
                    upright.append((box, k, cells_of))
        if len(upright) != 1:
            continue
        (x, y, w, h), k, cells_of = upright[0]
        crop = np.rot90(gray[y:y + h, x:x + w], k)
        crops[product].append(crop)
        sizes[product].append(crop.shape)
        cells[product].append(cells_of)
    out = {}
    for product, found in crops.items():
        h, w = (int(np.median([s[i] for s in sizes[product]])) for i in (0, 1))
        mean = np.mean([cv2.resize(c, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) for c in found], axis=0)
        out[product] = (mean.astype(np.float32), np.median(np.array(cells[product]), axis=0).astype(int).tolist(),
                        len(found))
    return out


# Matching and reading --------------------------------------------------------------------------------------------

def match(gray, template):
    """[(score, k, (x, y), (h, w))] best first: the template's best match in gray when gray's pill needs k
    counter-clockwise quarter turns to stand upright, and where (the turned template's box)."""
    import cv2
    import numpy as np

    out = []
    for k in range(4):
        turned = np.ascontiguousarray(np.rot90(template, -k))
        if turned.shape[0] > gray.shape[0] or turned.shape[1] > gray.shape[1]:
            continue
        found = cv2.matchTemplate(gray, turned, cv2.TM_CCOEFF_NORMED)
        _, best, _, at = cv2.minMaxLoc(found)
        out.append((round(float(best), 3), k, at, turned.shape))
    return sorted(out, reverse=True)


def upright_crop(gray, found):
    """The pill a match found, upright and normalised."""
    _, k, (x, y), (h, w) = found
    return normalise(gray, (x, y, w, h), k)


def cell(crop, box, dx=0, dy=0):
    import cv2
    import numpy as np

    x, y, w, h = box
    x0, y0 = max(0, x - CELL_PAD + dx), max(0, y - CELL_PAD + dy)
    patch = crop[y0:y0 + h + 2 * CELL_PAD, x0:x0 + w + 2 * CELL_PAD].astype(np.float32)
    patch = cv2.resize(patch, (24, 40), interpolation=cv2.INTER_AREA)
    return (patch - patch.mean()) / (patch.std() + 1e-6)


def read_codes(pills, copies=None):
    """{key: (code read, [vote share per glyph])}. pills: {key: (code, crop, cells)}; each glyph is read by the
    similarity-weighted votes of its nearest NEIGHBOURS among the other sides' same glyph, with a few px of shift
    allowed. copies: {key: other keys whose scan is the same file}, which don't count."""
    import numpy as np

    copies = copies or {}
    keys = list(pills)
    ref = {key: [cell(crop, box) for box in cells] for key, (_, crop, cells) in pills.items()}
    out = {}
    for key, (code, crop, cells) in pills.items():
        read, shares = '', []
        for i, box in enumerate(cells):
            mine = np.stack([cell(crop, box, dx, dy) for dx, dy in SHIFTS])
            sims = []
            for other in keys:
                if other == key or other in copies.get(key, ()):
                    continue
                sims.append((float((mine * ref[other][i]).mean(axis=(1, 2)).max()), pills[other][0][i]))
            sims.sort(reverse=True)
            votes = defaultdict(float)
            for s, label in sims[:NEIGHBOURS]:
                votes[label] += max(s, 0)
            best = max(votes, key=votes.get) if votes else '?'  # only copies of itself to go by
            read += best
            shares.append(round(votes.get(best, 0) / (sum(votes.values()) or 1), 2))
        out[key] = (read, shares)
    return out


def digest(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def pixels_digest(image):
    return hashlib.md5(image.tobytes()).hexdigest()


# Run ----------------------------------------------------------------------------------------------------------------

def run(dataset, scans=None, out=None, log=print):
    """Find every side's turns (scan and our image), write turns.json and the review page; returns the turns."""
    import cv2
    import numpy as np
    from PIL import Image

    from ia_tools import hires_tiles

    scans = Path(scans or hires_tiles.scans_dir())
    out = Path(out or out_dir())
    (out / 'img').mkdir(parents=True, exist_ok=True)
    fits = json.loads((hires_tiles.out_dir() / 'manifest.json').read_text(encoding='utf-8'))['sides']
    rulings_file = out / 'rulings.json'
    rulings = json.loads(rulings_file.read_text(encoding='utf-8')) if rulings_file.exists() else {}

    every = hires_tiles.sides(dataset)
    grays, files = {}, {}
    for key, product, tile, side, field in every:
        file = hires_tiles.scan_file(product, tile['number'], side, scans)
        if file is None:
            continue
        scan = np.array(Image.open(file).convert('RGBA'))
        grays[key] = (product, cv2.cvtColor(scan[..., :3], cv2.COLOR_RGB2GRAY), scan)
        files[key] = file
    log(f'{len(grays)} scans; finding pill templates')
    shapes = templates(grays)
    for product, (template, cells, n) in shapes.items():
        log(f'  {product}: {n} pills, template {template.shape[1]}x{template.shape[0]} px')

    scan_dups = defaultdict(list)
    for key, file in files.items():
        scan_dups[digest(file)].append(key)
    copies = {key: [k for k in scan_dups[digest(file)] if k != key] for key, file in files.items()}
    ours_images, ours_dups = {}, defaultdict(list)
    for key, product, tile, side, field in every:
        image = hires_tiles.stored(dataset, tile[field], OURS_PX)
        ours_images[key] = image
        ours_dups[pixels_digest(image)].append(key)

    masked = {key: np.where(scan[..., 3] > 127, gray, 0).astype(np.float32) for key, (_, gray, scan) in grays.items()}
    product_of = {key: product for key, product, *_ in every}
    for rounds in range(2):
        found, pills = {}, {}
        for key, product, tile, side, field in every:
            if key not in grays:
                continue
            template, cells, _ = shapes[product]
            found[key] = match(masked[key], template)
            pills[key] = (code_of(tile, side), upright_crop(grays[key][1], found[key][0]), cells)
        reads = read_codes(pills, copies)
        if rounds:
            break
        # Again with each product's template from its pills found clearly and reading their own code.
        for product, (template, cells, _) in list(shapes.items()):
            sure = [k for k in found if product_of[k] == product and found[k][0][0] - found[k][1][0] >= MARGIN
                    and reads[k][0] == pills[k][0] and min(reads[k][1]) >= SURE]
            crops = []
            for k in sure:
                _, turn_k, (x, y), (h, w) = found[k][0]
                crop = np.rot90(grays[k][1][y:y + h, x:x + w], turn_k).astype(np.float32)
                crops.append(cv2.resize(crop, (template.shape[1], template.shape[0]), interpolation=cv2.INTER_AREA))
            if len(crops) > shapes[product][2]:
                shapes[product] = (np.mean(crops, axis=0).astype(np.float32), cells, len(crops))
                log(f'  {product}: template again from {len(crops)} pills')
    for key, matches in found.items():
        log(f'  {key}: pill upright after {turn_of_k(matches[0][1])}° ({matches[0][0]:.2f}, next {matches[1][0]:.2f}), '
            f'reads {reads[key][0]}')

    turns, ours_pills = {}, {}
    for key, product, tile, side, field in every:
        entry = {'code': code_of(tile, side), 'flags': []}
        flags = entry['flags']
        if key in found:
            best, second = found[key][0], found[key][1]
            read, shares = reads[key]
            entry['scan'] = {'file': files[key].name, 'turn': turn_of_k(best[1]), 'score': best[0],
                             'next': second[0], 'at': list(best[2]), 'size': list(best[3]), 'read': read,
                             'shares': shares}
            if best[0] - second[0] < MARGIN:
                flags.append(f'scan: which way up is unclear ({best[0]:.2f} against {second[0]:.2f})')
            if read != entry['code']:
                flags.append(f'scan: its pill reads {read}')
            elif min(shares) < SURE:
                flags.append(f'scan: its pill reads {read}, but not clearly')
            twins = [k for k in scan_dups[digest(files[key])] if k != key]
            if twins:
                flags.append(f"scan: the same file as {', '.join(twins)}'s")
                entry['new_scan'] = True
            elif read != entry['code'] and min(shares) >= SURE:
                entry['new_scan'] = True
        else:
            flags.append('no scan')

        # Our image: the scan's upright turn and its registration onto ours (scan -> ours, clockwise), checked by the
        # pill template.
        image = ours_images[key]
        plain = cv2.cvtColor(image[..., :3], cv2.COLOR_RGB2GRAY)
        gray = np.where(image[..., 3] > 127, plain, 0).astype(np.float32)
        template = shapes[product][0]
        small = cv2.resize(template, (round(template.shape[1] * OURS_PX / SCAN_PX),
                                      round(template.shape[0] * OURS_PX / SCAN_PX)), interpolation=cv2.INTER_AREA)
        pill = match(gray, small)
        by_pill = turn_of_k(pill[0][1])
        ours = {'turn': by_pill, 'pill': pill[0][0], 'next': pill[1][0], 'at': list(pill[0][2]),
                'size': list(pill[0][3])}
        if 'scan' in entry and key in fits:
            by_fit = (entry['scan']['turn'] - fits[key]['turn']) % 360
            ours['fit'] = by_fit
            sure_pill = pill[0][0] - pill[1][0] >= MARGIN
            if by_fit != by_pill:
                ours['turn'] = by_pill if sure_pill else by_fit
                flags.append(f"ours: its fit onto the scan says {by_fit}°, its pill {by_pill}° "
                             f"({pill[0][0]:.2f} against {pill[1][0]:.2f}); taking {ours['turn']}°")
            elif fits[key]['how'] == 'outline':
                flags.append('ours: the scan was fitted by its outline alone')
        elif pill[0][0] - pill[1][0] < MARGIN:
            flags.append(f'ours: which way up is unclear ({pill[0][0]:.2f} against {pill[1][0]:.2f})')
        twins = [k for k in ours_dups[pixels_digest(image)] if k != key]
        if twins:
            flags.append(f"ours: the same image as {', '.join(twins)}'s")
            entry['same_image'] = True
        entry['ours'] = ours
        ours_pills[key] = (entry['code'], upright_crop(plain, pill[0]), shapes[product][1])
        if key in rulings:
            entry['ruled'] = rulings[key]
            for which in ('scan', 'ours'):
                if which in rulings[key] and which in entry:
                    entry[which]['turn'] = rulings[key][which]
        turns[key] = entry

    # Our pills' codes, read by the scans' pills and each other's (not its own scan's, nor that scan's copies').
    both = pills | {f'{key} (ours)': pill for key, pill in ours_pills.items()}
    skip = copies | {f'{key} (ours)': [key, *copies.get(key, [])] for key in ours_pills}
    ours_reads = read_codes(both, skip)
    for key, entry in turns.items():
        read, shares = ours_reads[f'{key} (ours)']
        entry['ours'] |= {'read': read, 'shares': shares}
        if read != entry['code']:
            entry['flags'].append(f'ours: its pill reads {read}')
        elif min(shares) < SURE:
            entry['flags'].append(f'ours: its pill reads {read}, but not clearly')

    (out / 'turns.json').write_text(json.dumps(turns, indent=1), encoding='utf-8')
    images(dataset, turns, grays, ours_images, out)
    review(dataset, turns, out)
    return turns


# Review -------------------------------------------------------------------------------------------------------------

def slug(key):
    return key.lower().replace("'", '').replace(' ', '-')


def turned(image, turn):
    import numpy as np

    return np.ascontiguousarray(np.rot90(image, k_of_turn(turn)))


def images(dataset, turns, grays, ours_images, out):
    """img/<slug>-{scan,ours}{,-pill}.jpg: each image upright (64 px per square), and its pill enlarged."""
    import cv2
    import numpy as np
    from PIL import Image

    def save(image, path, width=None):
        rgb = image[..., :3].astype(np.float32)
        if image.shape[2] == 4:
            a = image[..., 3:4].astype(np.float32) / 255
            rgb = rgb * a + 51 * (1 - a)
        rgb = rgb.astype(np.uint8)
        if width:
            rgb = cv2.resize(rgb, (width, round(rgb.shape[0] * width / rgb.shape[1])), interpolation=cv2.INTER_AREA)
        Image.fromarray(rgb).save(path, quality=88)

    for key, entry in turns.items():
        name = slug(key)
        if 'scan' in entry:
            _, gray, scan = grays[key]
            x, y = entry['scan']['at']
            h, w = entry['scan']['size']
            pad = 12
            crop = scan[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
            save(turned(crop, entry['scan']['turn']), out / 'img' / f'{name}-scan-pill.jpg', 240)
            small = cv2.resize(scan, None, fx=64 / SCAN_PX, fy=64 / SCAN_PX, interpolation=cv2.INTER_AREA)
            save(turned(small, entry['scan']['turn']), out / 'img' / f'{name}-scan.jpg')
        image = ours_images[key]
        x, y = entry['ours']['at']
        h, w = entry['ours']['size']
        pad = 6
        crop = image[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
        save(turned(crop, entry['ours']['turn']), out / 'img' / f'{name}-ours-pill.jpg', 240)
        save(turned(image, entry['ours']['turn']), out / 'img' / f'{name}-ours.jpg', image.shape[1] * 64 // OURS_PX)


def review(dataset, turns, out):
    """index.html: every side by product, its two images upright with their pills; flagged sides listed first."""
    from ia_tools import hires_tiles

    products = defaultdict(list)
    for key, product, *_ in hires_tiles.sides(dataset):
        products[product].append(key)
    e = html.escape

    def row(key):
        entry = turns[key]
        name = slug(key)
        scan = entry.get('scan')
        flagged = bool(entry['flags'])
        meta = [f"code {entry['code']}"]
        if scan:
            meta.append(f"scan {e(scan['file'])}: reads {scan['read']}, turned {scan['turn']}°")
        meta.append(f"our image: reads {entry['ours'].get('read', '?')}, turned {entry['ours']['turn']}°")
        if 'ruled' in entry:
            meta.append('ruled')
        cells = []
        if scan:
            cells.append(f'<figure><img src="img/{name}-scan-pill.jpg" class="pill"><figcaption>scan pill</figcaption></figure>')
        cells.append(f'<figure><img src="img/{name}-ours-pill.jpg" class="pill"><figcaption>our pill</figcaption></figure>')
        if scan:
            cells.append(f'<figure><img src="img/{name}-scan.jpg"><figcaption>scan, upright</figcaption></figure>')
        cells.append(f'<figure><img src="img/{name}-ours.jpg"><figcaption>ours, upright</figcaption></figure>')
        reasons = ''.join(f'<li>{e(f)}</li>' for f in entry['flags'])
        return (f'<div class="side{" flag" if flagged else ""}" id="{name}"><h3>{e(key)}'
                f'{" <span class=badge>check</span>" if flagged else ""}</h3>'
                f'{f"<ul>{reasons}</ul>" if reasons else ""}<p class="meta">{" · ".join(meta)}</p>'
                f'<div class="grid">{"".join(cells)}</div></div>')

    def listing(title, keys, note):
        if not keys:
            return ''
        links = ''.join(f'<li><a href="#{slug(k)}">{e(k)}</a>: {e("; ".join(turns[k]["flags"]))}</li>' for k in keys)
        return f'<section class="top"><h2>{e(title)} ({len(keys)})</h2><p>{e(note)}</p><ul>{links}</ul></section>'

    # The maintainer's notes (notes.json: {side key: {"new_scan" or "edit": why}}): sides the pills alone can't tell.
    notes_file = out / 'notes.json'
    notes = json.loads(notes_file.read_text(encoding='utf-8')) if notes_file.exists() else {}
    turns = {k: dict(v, flags=list(v['flags'])) for k, v in turns.items()}
    for key, note in notes.items():
        entry = turns[key]
        if 'new_scan' in note:
            entry['new_scan'] = True
            entry['flags'].insert(0, f"needs a new scan: {note['new_scan']}")
        if 'edit' in note:
            entry.pop('new_scan', None)
            entry['edit'] = True
            entry['flags'].insert(0, f"scan to edit: {note['edit']}")
    new_scan = [k for k, v in turns.items() if v.get('new_scan')]
    edit = [k for k, v in turns.items() if v.get('edit')]
    wrong = [k for k, v in turns.items() if v.get('same_image')]
    flagged = [k for k, v in turns.items() if v['flags'] and k not in new_scan + edit + wrong]
    sets = []
    for product, keys in products.items():
        n = sum(1 for k in keys if turns[k]['flags'])
        badge = f' <span class="badge">{n} to check</span>' if n else ''
        sets.append(f'<details class="set"><summary>{e(product)} ({len(keys)} sides){badge}</summary>'
                    f'{"".join(row(k) for k in keys)}</details>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Upright tile sides</title>
<style>
body {{ font: 14px/1.4 system-ui, sans-serif; margin: 16px; background: #fff; color: #222; }}
.top {{ border: 2px solid #c33; padding: 8px 16px; margin-bottom: 16px; }}
.set > summary {{ font-size: 18px; font-weight: 600; cursor: pointer; padding: 6px 0; }}
.side {{ border-bottom: 1px solid #ddd; padding: 8px 0; }}
.side.flag {{ border: 2px solid #c33; padding: 8px; margin: 8px 0; }}
.badge {{ background: #c33; color: #fff; border-radius: 8px; padding: 0 6px; font-size: 12px; }}
.meta {{ color: #555; margin: 4px 0; }}
.grid {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; }}
figure {{ margin: 0; }} figcaption {{ font-size: 12px; color: #666; }}
img {{ max-width: 220px; height: auto; background: #333; }} img.pill {{ width: 240px; max-width: 240px; }}
</style></head><body>
<h1>Upright tile sides</h1>
<p>Each side's scan and our stored image, turned so the pill reads upright, with their pills enlarged. Both codes
are read from the pills (ours at {OURS_PX} px per square), and our image's turn checked against the scan's fit.
Rulings go in rulings.json as {{"side key": {{"scan": turn, "ours": turn}}}}.</p>
{listing('Needs a new scan', new_scan, 'The scan is the same file as another side, clearly reads another code, or '
                                        "isn't the tile the maintainer has.")}
{listing('Scan to edit', edit, "The scan is right, but its pill is printed wrong (an errata).")}
{listing('Same image', wrong, 'Our image is the same as another side: one of them shows the wrong pill.')}
{listing('To check', flagged, 'OCR or the pill match was unsure: rule the turn, or confirm.')}
{''.join(sets)}
<script>
for (const a of document.querySelectorAll('a[href^="#"]')) a.addEventListener('click', () => {{
  const target = document.querySelector(a.getAttribute('href'));
  if (target) target.closest('details').open = true;
}});
</script></body></html>"""
    (out / 'index.html').write_text(page, encoding='utf-8')
