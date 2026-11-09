"""ia tile-matches: tile sides with the same art, but for their number pill ("interchangeable": the maintainer's
examples are Twin Shadows 10A = Core Set 35A and Twin Shadows 11A = Core Set 36A).

Compared on the dataset's own images (images/large, at 128 px per square: the maintainer's scans), with both sides'
pills masked out (their boxes from `ia tile-orientation`'s turns.json, "ours", PAD px around). Every side is stored
with its pill upright, so the same art lines up as stored: sides are compared at turn 0 only (a match found only
turned was a plain square room that looks alike turned):
1. coarse: every two sides of different tiles with the same squares whose outlines overlap at least OUTLINE: the
   correlation of their gradient magnitudes at 32 px per square. A pair needs COARSE;
2. fine: their fine detail (a high-pass) at 64 px per square, at the best shift of up to SHIFT px (two sides' fits can
   sit a pixel or two apart), as stored or with the second side aligned onto the first (a turn and shift by ECC, up
   to a few degrees and px: two scans fitted separately can be that far apart), whichever scores better. A pair needs
   FINE. Pairs below that but with fine at least WEAK are listed one by one to check: no threshold separates true
   pairs from look-alikes (Return to Hoth 27A / Core Set 35A, the same art by the maintainer's tiles, scores 0.67;
   plain rooms that aren't, 0.75).
A pair's "turned" score is its best fine score with the second side turned (where the outlines allow): copied art
scores clearly better as stored than turned (Core 35A / Twin Shadows 10A: 0.77 against 0.49), while plain,
near-symmetric rooms look about as alike either way (Jabba's Realm 13A / Tyrants of Lothal 08A: 0.82 at 0, 90 and
270 degrees), so the page notes a pair whose turned score is within PLAIN of its own.
Every square of a tile has the same grid lines, so a whole-tile score is high for any two tiles with a similar
layout; the thresholds were set on the maintainer's examples (35A/10A score 0.79 coarse, 0.77 fine, the lowest true
pair) and on the gap below them (no other pair scores between 0.68 and 0.77 fine). The pairs that pass are joined
into groups, for the maintainer to rule which sides really are the same.

Writes staging/tile-matches/:
- candidates.json: {"groups": [{"sides": [key, ...], "reference": key, "pairs": [{"sides": [a, b], "coarse",
  "fine", "shift": [dx, dy], "turned": fine score turned or null}]}], "weak": [{"sides", "coarse", "fine", "shift"}]};
- img/: each side (48 px per square, its pill boxed) and each side's difference from its group's reference;
- index.html: the groups, a section each, with the maintainer's rulings (rulings.json, by side), then the weaker pairs.

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
WEAK = 0.5  # a pair below the groups' thresholds but with fine detail this alike is listed to check
SHIFT = 4  # px at 64 per square
PLAIN = 0.05
ALIGN_SCALE = 0.06
ALIGN_TURN = 3.0
ALIGN_MOVE = 8.0  # px at 64 per square


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
    return _measures(gray, alpha, box)


def _measures(gray, alpha, box):
    import cv2
    import numpy as np

    found = {'source': (gray, alpha, box)}
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
            found['blurred'] = cv2.GaussianBlur(g, (0, 0), 2)
            signal = cv2.GaussianBlur(g, (0, 0), 0.7) - cv2.GaussianBlur(g, (0, 0), 4)
        found[name] = {'signal': signal, 'alpha': a, 'mask': inside & ~p, 'pill': p}
    return found


def aligned(one, two):
    """two warped onto one (a turn and shift found by ECC on their blurred art at 64 px per square, pills masked), or two as it
    is when ECC fails or the warp is more than a small fit error: scale off by over ALIGN_SCALE, turned over
    ALIGN_TURN degrees or moved over ALIGN_MOVE px. Two scans fitted separately can be a degree or a few px apart."""
    import math

    import cv2
    import numpy as np

    mask = (one['fine']['mask'] & two['fine']['mask']).astype(np.uint8)
    try:
        _, W = cv2.findTransformECC(one['blurred'], two['blurred'], np.eye(2, 3, dtype=np.float32), cv2.MOTION_EUCLIDEAN,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), mask, 5)
    except cv2.error:
        return two
    A = W[:, :2]
    scales = np.linalg.svd(A, compute_uv=False)
    turn = abs(math.degrees(math.atan2(A[1, 0] - A[0, 1], A[0, 0] + A[1, 1])))
    if abs(scales - 1).max() > ALIGN_SCALE or turn > ALIGN_TURN or abs(W[:, 2]).max() > ALIGN_MOVE:
        return two
    W2 = W.copy()
    W2[:, 2] *= 2  # at 128 px per square
    gray, alpha, box = two['source']
    size = gray.shape[::-1]
    warp = lambda image, how: cv2.warpAffine(image, W2, size, flags=how | cv2.WARP_INVERSE_MAP)
    return _measures(warp(gray, cv2.INTER_LINEAR), warp(alpha, cv2.INTER_NEAREST), warp(box, cv2.INTER_NEAREST))


def compare(one, two):
    """(coarse, fine, (dx, dy)) for two onto one as stored, or None when their outlines don't overlap enough: the better
    of two as it is and two aligned onto one (a small fit error taken out)."""
    found = matched(one, two)
    return found and found[0]


def matched(one, two):
    """compare()'s scores and the measures of two they were taken on (two itself or two aligned), or None."""
    a1, a2 = one['coarse']['alpha'], two['coarse']['alpha']
    if a1.shape != a2.shape or (a1 & a2).sum() / (a1 | a2).sum() < OUTLINE:
        return None
    found = [(_scores(one, two), two)]
    moved = aligned(one, two)
    if moved is not two:
        found.append((_scores(one, moved), moved))
    return max(found, key=lambda f: f[0][1])


def _scores(one, two):
    import numpy as np

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


def rotated(image, pill, q):
    """A side's image and pill box ((x, y), (h, w)) turned q quarters counter-clockwise (numpy's rot90)."""
    import numpy as np

    (x, y), (h, w) = pill
    height, width = image.shape[:2]
    for _ in range(q % 4):
        x, y, w, h, width, height = y, width - x - w, h, w, height, width
    return np.ascontiguousarray(np.rot90(image, q)), ((x, y), (h, w))


def turned_score(one, image, pill):
    """The best fine score of a side (image, pill) onto one at a quarter turn other than 0, or None if none fits."""
    found = [r[1] for q in (1, 2, 3) for r in [compare(one, prepare(*rotated(image, pill, q)))] if r]
    return max(found) if found else None


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

    pairs, weak = [], []
    for a, b in itertools.combinations(order, 2):
        if sides[a]['tile'] == sides[b]['tile'] or sides[a]['squares'] != sides[b]['squares']:
            continue
        found = compare(sides[a], sides[b])
        if not found:
            continue
        pair = {'sides': [a, b], 'coarse': found[0], 'fine': found[1], 'shift': list(found[2])}
        if found[0] >= COARSE and found[1] >= FINE:
            turned = turned_score(sides[a], *images[b])
            pairs.append(pair | {'turned': turned and round(turned, 3)})
        elif found[1] >= WEAK:
            weak.append(pair)
    groups = []
    for members in groups_of(pairs, order):
        inside = [p for p in pairs if p['sides'][0] in members]
        reference = max(members, key=lambda k: (sum(p['fine'] for p in inside if k in p['sides']), -order.index(k)))
        groups.append({'sides': members, 'reference': reference, 'pairs': inside})
    grouped = {k: n for n, g in enumerate(groups) for k in g['sides']}
    weak = [p for p in weak if grouped.get(p['sides'][0], -1) != grouped.get(p['sides'][1], -2)]  # not in one group
    weak.sort(key=lambda p: -p['fine'])
    (out / 'candidates.json').write_text(json.dumps({'groups': groups, 'weak': weak}, indent=1), encoding='utf-8')
    rules = rulings(out)
    pictures(groups, weak, rules, sides, images, out)
    review(groups, weak, rules, out)
    log(f'  {len(pairs)} pairs in {len(groups)} groups, {len(weak)} weaker pairs (fine {WEAK} to {FINE}) to check')
    return groups


def rulings(out):
    """The maintainer's rulings (rulings.json, written from chat): [{"same": [[side, ...], ...], "not": [side, ...],
    "apart": [[side, ...], ...], "note"}], whatever group numbers they were filed under (groups renumber when the
    matcher changes). "not": sides of a group that aren't its same-sets' art; "apart": sets of sides whose art differs
    from each other set's (a weaker pair across two groups ruled not the same)."""
    path = out / 'rulings.json'
    return list(json.loads(path.read_text(encoding='utf-8')).values()) if path.exists() else []


def ruled(rules, a, b):
    """'same', 'not' or None: what the rulings say about two sides."""
    for rule in rules:
        if any(a in same and b in same for same in rule.get('same', [])):
            return 'same'
    for rule in rules:
        sides = {k for same in rule.get('same', []) for k in same} | set(rule.get('not', []))
        if a in sides and b in sides:
            return 'not'
        apart = rule.get('apart', [])
        if any(a in one and b in two for one in apart for two in apart if one is not two):
            return 'not'
    return None


def ruled_extra(rules, group):
    """Sides the rulings put in a group's same-sets that the matcher didn't find."""
    members = set(group['sides'])
    found = []
    for rule in rules:
        for same in rule.get('same', []):
            if members & set(same):
                found += [k for k in same if k not in members and k not in found]
    return found


def pictures(groups, weak, rules, sides, images, out):
    """img/<slug>.jpg: a side at 48 px per square, its pill boxed; img/<slug>-diff.jpg: its fine detail's difference
    from its group's reference, red over the reference's grey (pills blue); img/<slug>--<slug>-diff.jpg: a weaker
    pair's second side's difference from its first."""
    import cv2
    import numpy as np

    def side_picture(key):
        image, ((x, y), (h, w)) = images[key]
        rgb = np.where(image[..., 3:] > 127, image[..., :3], 40).astype(np.uint8)
        cv2.rectangle(rgb, (x - PAD, y - PAD), (x + w + PAD, y + h + PAD), (60, 140, 255), 4)
        small = cv2.resize(rgb, None, fx=48 / 128, fy=48 / 128, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out / 'img' / f'{slug(key)}.jpg'), cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])

    def diff_picture(ref_key, key, name):
        ref = sides[ref_key]
        found = matched(ref, sides[key])
        if found is None:
            return
        (_, _, (dx, dy)), two = found
        gray = cv2.cvtColor(cv2.resize(images[ref_key][0][..., :3], None, fx=0.5, fy=0.5,
                                       interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY).astype(np.float32)
        s1, m1 = ref['fine']['signal'], ref['fine']['mask']
        s2 = np.roll(two['fine']['signal'], (dy, dx), (0, 1))
        m2 = np.roll(two['fine']['mask'], (dy, dx), (0, 1))
        m = m1 & m2
        a, b = s1 / (s1[m].std() or 1), s2 / (s2[m].std() or 1)
        diff = np.clip(cv2.GaussianBlur(np.abs(a - b), (0, 0), 1.5) / 1.5, 0, 1) * m
        rgb = np.stack([gray * 0.45] * 3, -1)
        rgb[..., 0] = np.maximum(rgb[..., 0], diff * 255)
        pills = (ref['fine']['pill'] | np.roll(two['fine']['pill'], (dy, dx), (0, 1))) & ref['fine']['alpha']
        rgb[pills] = rgb[pills] * 0.5 + np.array([0, 40, 120])
        rgb[~ref['fine']['alpha']] = 40
        small = cv2.resize(rgb.astype(np.uint8), None, fx=48 / 64, fy=48 / 64, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out / 'img' / name), cv2.cvtColor(small, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])

    for group in groups:
        for key in group['sides'] + ruled_extra(rules, group):
            side_picture(key)
            if key != group['reference']:
                diff_picture(group['reference'], key, f'{slug(key)}-diff.jpg')
    for pair in weak:
        a, b = pair['sides']
        side_picture(a)
        side_picture(b)
        diff_picture(a, b, f'{slug(a)}--{slug(b)}-diff.jpg')


def review(groups, weak, rules, out):
    """index.html: a section per group, its sides and their differences from the group's reference, with the
    maintainer's rulings; then the weaker pairs, one by one."""
    e = html.escape
    sections = []
    for n, group in enumerate(groups, 1):
        ref = group['reference']
        extra = ruled_extra(rules, group)
        cells = []
        for key in group['sides'] + extra:
            if key == ref:
                cells.append(f'<figure><img src="img/{slug(key)}.jpg"><figcaption><b>{e(key)}</b> (reference)'
                             f'</figcaption></figure>')
                continue
            pair = next((p for p in group['pairs'] if set(p['sides']) == {ref, key}), None)
            score = f"fine {pair['fine']}, coarse {pair['coarse']}" if pair else 'linked through others'
            if key in extra:
                score = 'added by your ruling (the matcher missed it)'
            if pair and pair['turned'] is not None:
                score += f", turned {pair['turned']}"
                if pair['turned'] >= pair['fine'] - PLAIN:
                    score += ' <span class="warn">(as alike turned: plain art?)</span>'
            cells.append(f'<figure><img src="img/{slug(key)}.jpg"><img src="img/{slug(key)}-diff.jpg">'
                         f'<figcaption><b>{e(key)}</b>: {score}</figcaption></figure>')
        plain = [p for p in group['pairs'] if p['turned'] is not None and p['turned'] >= p['fine'] - PLAIN]
        note = (f'<p class="warn">About as alike turned as stored: '
                f'{e("; ".join(" / ".join(p["sides"]) for p in plain))}. Plain rooms look alike any way round; '
                f'copied art matches clearly better as stored.</p>' if plain else '')
        members = set(group['sides']) | set(extra)
        mine = [r for r in rules
                if members & ({k for same in r.get('same', []) for k in same} | set(r.get('not', [])))]
        if mine:
            parts = [f'same: {e(", ".join(same))}' for r in mine for same in r.get('same', []) if members & set(same)]
            parts += [f'not the same: {e(", ".join(r["not"]))}' for r in mine if r.get('not')]
            verdict = f'<p class="ruled">Your ruling: {"; ".join(parts)}.</p>'
        else:
            verdict = '<p class="open">Not ruled yet.</p>'
        sections.append(f'<section id="g{n}"><h2>Group {n}: {e(", ".join(group["sides"]))}</h2>{verdict}{note}'
                        f'<div class="grid">{"".join(cells)}</div></section>')
    rows = []
    for n, pair in enumerate(weak, 1):
        a, b = pair['sides']
        status = {'same': '<p class="ruled">Your ruling: the same.</p>',
                  'not': '<p class="ruled">Your ruling: not the same.</p>'}.get(ruled(rules, a, b),
                                                                             '<p class="open">Not ruled yet.</p>')
        rows.append(f'<section id="w{n}"><h2>Pair {n}: {e(a)} / {e(b)}</h2>{status}<div class="grid">'
                    f'<figure><img src="img/{slug(a)}.jpg"><figcaption><b>{e(a)}</b></figcaption></figure>'
                    f'<figure><img src="img/{slug(b)}.jpg"><img src="img/{slug(a)}--{slug(b)}-diff.jpg">'
                    f'<figcaption><b>{e(b)}</b>: fine {pair["fine"]}, coarse {pair["coarse"]}</figcaption></figure>'
                    f'</div></section>')
    sections.append(f'<h1 id="weak">Weaker pairs to check</h1><p>Pairs whose fine detail scores {WEAK} to {FINE}: '
                    f'below what groups need, but true pairs have scored this low (Return to Hoth 27A / Core Set 35A). '
                    f'Most will be different art with a similar layout.</p>' + ''.join(rows))
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Interchangeable tile sides</title>
<style>
body {{ font: 14px/1.4 system-ui, sans-serif; margin: 16px; background: #fff; color: #222; }}
section {{ border-bottom: 1px solid #ddd; padding: 8px 0 16px; }}
h2 {{ font-size: 16px; }}
.grid {{ display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }}
figure {{ margin: 0; max-width: 420px; }} figure img {{ display: block; margin-bottom: 4px; max-width: 200px; height: auto; }}
figure {{ display: grid; grid-template-columns: auto auto; gap: 4px; }} figcaption {{ grid-column: 1 / -1; font-size: 12px; color: #555; }}
.warn {{ color: #a30; }} .ruled {{ color: #070; font-weight: 600; }} .open {{ color: #888; }}
</style></head><body>
<h1>Interchangeable tile sides</h1>
<p>Sides whose art looks the same but for their number pill (boxed in blue), from our stored images, grouped. Next to
each side: where its fine detail differs from the group's reference, red over the reference (pills masked, in blue).
Same art shows only faint, even speckle; different art shows red shapes. Rule each group in chat: all the same, or
which sides aren't. Your rulings so far are in green. <a href="#weak">Weaker pairs</a> follow the groups.</p>
{''.join(sections)}
</body></html>"""
    (out / 'index.html').write_text(page, encoding='utf-8')
