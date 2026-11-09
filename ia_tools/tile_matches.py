"""ia tile-matches: tile sides with the same art, but for their number pill ("interchangeable": the maintainer's
examples are Twin Shadows 10A = Core Set 35A and Twin Shadows 11A = Core Set 36A).

Compared on the dataset's own images (images/large, at 128 px per square: the maintainer's scans), with both sides'
pills masked out (their boxes from `ia tile-orientation`'s turns.json, "ours", PAD px around). Every side is stored
with its pill upright, so the same art lines up as stored: sides are compared at turn 0 only (a match found only
turned was a plain square room that looks alike turned):
1. coarse: every two sides of different tiles with the same squares whose outlines overlap at least OUTLINE: the
   correlation of their gradient magnitudes at 32 px per square. A pair needs COARSE;
2. fine: their fine detail (a high-pass) at 64 px per square, at the best shift of up to SHIFT px (two sides' fits can
   sit a pixel or two apart). A pair needs FINE.
Every square of a tile has the same grid lines, so a whole-tile score is high for any two tiles with a similar
layout; the thresholds were set on the maintainer's examples (35A/10A score 0.79 coarse, 0.77 fine, the lowest true
pair) and on the gap below them (no other pair scores between 0.68 and 0.77 fine). The pairs that pass are joined
into groups, for the maintainer to rule which sides really are the same.

Writes staging/tile-matches/:
- candidates.json: {"groups": [{"sides": [key, ...], "reference": key, "pairs": [{"sides": [a, b], "coarse",
  "fine", "shift": [dx, dy]}]}]};
- img/: each side (48 px per square, its pill boxed) and each side's difference from its group's reference;
- index.html: the groups, a section each.

The tools measure the images; the maintainer looks at them."""
import html
import itertools
import json
from pathlib import Path

from ia_tools import settings

PAD = 14  # px at 128 per square around a pill
OUTLINE = 0.85
COARSE = 0.6
FINE = 0.7
SHIFT = 4  # px at 64 per square


def out_dir():
    return settings.STAGING / 'tile-matches'


def slug(key):
    return key.lower().replace("'", '').replace(' ', '-')


def _ncc(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = (float((a * a).sum()) * float((b * b).sum())) ** 0.5
    return float((a * b).sum() / d) if d else 0.0


def prepare(image, pill):
    """A side's measures: its image (RGBA, 128 px per square) and pill box ((x, y), (h, w)) at 128 px per square."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
    alpha = (image[..., 3] > 250).astype(np.uint8)
    box = np.zeros(alpha.shape, np.uint8)
    (x, y), (h, w) = pill
    box[max(0, y - PAD):y + h + PAD, max(0, x - PAD):x + w + PAD] = 1
    found = {}
    for name, f, erode in (('coarse', 0.25, 3), ('fine', 0.5, 9)):
        g = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        size = (g.shape[1], g.shape[0])
        a = cv2.resize(alpha, size, interpolation=cv2.INTER_AREA) > 0
        inside = cv2.erode(a.astype(np.uint8), np.ones((erode, erode), np.uint8)) > 0
        p = cv2.resize(box, size, interpolation=cv2.INTER_NEAREST) > 0
        if name == 'coarse':
            g = cv2.GaussianBlur(g, (0, 0), 0.8)
            signal = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
        else:
            signal = cv2.GaussianBlur(g, (0, 0), 0.7) - cv2.GaussianBlur(g, (0, 0), 4)
        found[name] = {'signal': signal, 'alpha': a, 'mask': inside & ~p, 'pill': p}
    return found


def compare(one, two):
    """(coarse, fine, (dx, dy)) for two onto one as stored, or None when their outlines don't overlap enough."""
    import numpy as np

    a1, a2 = one['coarse']['alpha'], two['coarse']['alpha']
    if a1.shape != a2.shape or (a1 & a2).sum() / (a1 | a2).sum() < OUTLINE:
        return None
    m = one['coarse']['mask'] & two['coarse']['mask']
    score = _ncc(one['coarse']['signal'][m], two['coarse']['signal'][m])
    fine = (-1.0, (0, 0))
    s2, m2 = two['fine']['signal'], two['fine']['mask']
    for dy in range(-SHIFT, SHIFT + 1):
        for dx in range(-SHIFT, SHIFT + 1):
            m = one['fine']['mask'] & np.roll(m2, (dy, dx), (0, 1))
            v = _ncc(one['fine']['signal'][m], np.roll(s2, (dy, dx), (0, 1))[m])
            if v > fine[0]:
                fine = (v, (dx, dy))
    return round(score, 3), round(fine[0], 3), fine[1]


def groups_of(pairs, order):
    """The pairs' sides joined into groups (connected), each in order, groups by their first side."""
    parent = {}

    def root(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    for p in pairs:
        parent[root(p['sides'][0])] = root(p['sides'][1])
    found = {}
    for x in list(parent):
        found.setdefault(root(x), []).append(x)
    return sorted((sorted(g, key=order.index) for g in found.values()), key=lambda g: order.index(g[0]))


def run(dataset, out=None, log=print):
    from ia_tools import hires_tiles

    out = Path(out or out_dir())
    (out / 'img').mkdir(parents=True, exist_ok=True)
    turns = json.loads((settings.STAGING / 'tile-orientation' / 'turns.json').read_text(encoding='utf-8'))
    every = hires_tiles.sides(dataset)
    order = [key for key, *_ in every]
    sides, images = {}, {}
    for key, product, tile, side, field in every:
        image = hires_tiles.stored(dataset, tile[field], 128)
        pill = (tuple(turns[key]['ours']['at']), tuple(turns[key]['ours']['size']))
        images[key] = (image, pill)
        sides[key] = {'tile': tile['id'], 'squares': tile['squares'], **prepare(image, pill)}

    pairs = []
    for a, b in itertools.combinations(order, 2):
        if sides[a]['tile'] == sides[b]['tile'] or sides[a]['squares'] != sides[b]['squares']:
            continue
        found = compare(sides[a], sides[b])
        if found and found[0] >= COARSE and found[1] >= FINE:
            pairs.append({'sides': [a, b], 'coarse': found[0], 'fine': found[1], 'shift': list(found[2])})
    groups = []
    for members in groups_of(pairs, order):
        inside = [p for p in pairs if p['sides'][0] in members]
        reference = max(members, key=lambda k: (sum(p['fine'] for p in inside if k in p['sides']), -order.index(k)))
        groups.append({'sides': members, 'reference': reference, 'pairs': inside})
    (out / 'candidates.json').write_text(json.dumps({'groups': groups}, indent=1), encoding='utf-8')
    pictures(groups, sides, images, out)
    review(groups, out)
    log(f'  {len(pairs)} pairs in {len(groups)} groups')
    return groups


def pictures(groups, sides, images, out):
    """img/<slug>.jpg: a side at 48 px per square, its pill boxed; img/<slug>-diff.jpg: its fine detail's difference
    from its group's reference, red over the reference's grey (pills blue)."""
    import cv2
    import numpy as np

    for group in groups:
        for key in group['sides']:
            image, ((x, y), (h, w)) = images[key]
            rgb = np.where(image[..., 3:] > 127, image[..., :3], 40).astype(np.uint8)
            cv2.rectangle(rgb, (x - PAD, y - PAD), (x + w + PAD, y + h + PAD), (60, 140, 255), 4)
            small = cv2.resize(rgb, None, fx=48 / 128, fy=48 / 128, interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out / 'img' / f'{slug(key)}.jpg'), cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, 85])
        ref = sides[group['reference']]
        base_image = images[group['reference']][0]
        gray = cv2.cvtColor(cv2.resize(base_image[..., :3], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
                            cv2.COLOR_RGB2GRAY).astype(np.float32)
        for key in group['sides']:
            if key == group['reference']:
                continue
            found = compare(ref, sides[key])
            if found is None:
                continue
            _, fine, (dx, dy) = found
            s1, m1 = ref['fine']['signal'], ref['fine']['mask']
            s2 = np.roll(sides[key]['fine']['signal'], (dy, dx), (0, 1))
            m2 = np.roll(sides[key]['fine']['mask'], (dy, dx), (0, 1))
            m = m1 & m2
            a, b = s1 / (s1[m].std() or 1), s2 / (s2[m].std() or 1)
            diff = np.clip(cv2.GaussianBlur(np.abs(a - b), (0, 0), 1.5) / 1.5, 0, 1) * m
            rgb = np.stack([gray * 0.45] * 3, -1)
            rgb[..., 0] = np.maximum(rgb[..., 0], diff * 255)
            pills = (ref['fine']['pill'] | np.roll(sides[key]['fine']['pill'], (dy, dx), (0, 1))) & ref['fine']['alpha']
            rgb[pills] = rgb[pills] * 0.5 + np.array([0, 40, 120])
            rgb[~ref['fine']['alpha']] = 40
            small = cv2.resize(rgb.astype(np.uint8), None, fx=48 / 64, fy=48 / 64, interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out / 'img' / f'{slug(key)}-diff.jpg'), cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, 85])


def review(groups, out):
    """index.html: a section per group, its sides and their differences from the group's reference."""
    e = html.escape
    sections = []
    for n, group in enumerate(groups, 1):
        ref = group['reference']
        cells = []
        for key in group['sides']:
            if key == ref:
                cells.append(f'<figure><img src="img/{slug(key)}.jpg"><figcaption><b>{e(key)}</b> (reference)'
                             f'</figcaption></figure>')
                continue
            pair = next((p for p in group['pairs'] if set(p['sides']) == {ref, key}), None)
            score = f"fine {pair['fine']}, coarse {pair['coarse']}" if pair else 'linked through others'
            cells.append(f'<figure><img src="img/{slug(key)}.jpg"><img src="img/{slug(key)}-diff.jpg">'
                         f'<figcaption><b>{e(key)}</b>: {score}</figcaption></figure>')
        sections.append(f'<section id="g{n}"><h2>Group {n}: {e(", ".join(group["sides"]))}</h2>'
                        f'<div class="grid">{"".join(cells)}</div></section>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Interchangeable tile sides</title>
<style>
body {{ font: 14px/1.4 system-ui, sans-serif; margin: 16px; background: #fff; color: #222; }}
section {{ border-bottom: 1px solid #ddd; padding: 8px 0 16px; }}
h2 {{ font-size: 16px; }}
.grid {{ display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }}
figure {{ margin: 0; max-width: 420px; }} figure img {{ display: block; margin-bottom: 4px; max-width: 200px; height: auto; }}
figure {{ display: grid; grid-template-columns: auto auto; gap: 4px; }} figcaption {{ grid-column: 1 / -1; font-size: 12px; color: #555; }}
</style></head><body>
<h1>Interchangeable tile sides</h1>
<p>Sides whose art looks the same but for their number pill (boxed in blue), from our stored images, grouped. Next to
each side: where its fine detail differs from the group's reference, red over the reference (pills masked, in blue).
Same art shows only faint, even speckle; different art shows red shapes. Rule each group in chat: all the same, or
which sides aren't.</p>
{''.join(sections)}
</body></html>"""
    (out / 'index.html').write_text(page, encoding='utf-8')
