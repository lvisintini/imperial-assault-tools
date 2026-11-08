"""ia hires-tiles: the map tiles' sides from the maintainer's scans (tiles/, ~299 px per square), at SQUARE px per
square, staged for the data repo (data 2.x).

Each side's scan (tiles/<Prefix>_<number><side>.png, cut on its outline, any turn) is fitted onto the dataset's image
of that side (Vassal's, 64 px per square), which fixes where the tile's grid is:
- scaled by SQUARE / SCAN_PX, then registered onto ours upscaled to SQUARE px per square: SIFT features and a
  similarity (RANSAC), or, for a tile too plain for features, its outline at each quarter turn;
- refined by ECC (affine), on the colours and on the outline, keeping whichever fits best (scored on blurred colour
  correlation and outline overlap with ours);
- drawn into our side's frame: SQUARE px per square plus SQUARE / 4 at each end of an axis with tabs, as the dataset's
  tiles are at 64 (so a side's grid and tabs land where ours are). Its outline is the scan's own.

Colours: one tone curve per product and channel, histogram-matched from the scans' pixels to ours, pooled over the
product's well-registered sides (colour correlation >= GOOD); the maintainer chose this from samples
(staging/tile-samples, 2026-11-06).

Writes staging/hires-tiles/:
- map-tiles/<the dataset's file name>: the new sides;
- manifest.json: {"square", "luts": {product: [[256] x 3]}, "sides": {"<tile name> <side>": {"scan", "file", "turn",
  "how", "corr", "iou", "clipped", "band", "scale", "after", "fits_better"?}}}: clipped is the scan's pixels outside
  our frame, band that as px all along our outline (the scans are cut a pixel or so outside the print), fits_better
  {"side", "corr"} when the scan fits another side's image clearly better than its own;
- index.html and review/: a review page (review()), a collapsible section per product, each side's current and new
  images, and the same spot of a map drawn with each: where the side touches the most other tiles.

The tools measure the images; the maintainer looks at them."""
import html
import json
import math
from pathlib import Path

from ia_tools import settings

SQUARE = 128
SCAN_PX = 299  # the scans' px per square, roughly (registration finds each one's exactly)
GOOD = 0.9
# A fit the review page flags: colour correlation below GOOD, outline overlap below OVERLAP, or more than BAND px of
# the scan outside our frame, on average along our outline.
OVERLAP = 0.95
BAND = 1.5
PREFIXES = {'Imperial Assault': 'Core', 'Twin Shadows': 'Twin', 'Return to Hoth': 'Hoth', 'The Bespin Gambit': 'Bespin',
            "Jabba's Realm": 'Jabba', 'Heart of the Empire': 'Heart', 'Tyrants of Lothal': 'Tyrants'}


def scans_dir():
    return settings.TOOLS_ROOT / 'tiles'


def out_dir():
    return settings.STAGING / 'hires-tiles'


def sides(dataset):
    """[(key "Core Set 01 A", product name, tile record, side, field)] for every tile side, in the file's order."""
    from ia_tools.tiles import EXPANSIONS, NAMES

    products = {NAMES.get(p, p): p for p in EXPANSIONS.values()}
    found = []
    for tile in dataset.records('map-tiles'):
        product = products[tile['name'].rsplit(' ', 1)[0]]
        for side in 'AB':
            found.append((f"{tile['name']} {side}", product, tile, side, f'side_{side.lower()}'))
    return found


def scan_file(product, number, side, folder):
    """The scan of a side, its name's case aside (heart_1B.png), or None."""
    wanted = f'{PREFIXES[product]}_{number}{side}.png'.lower()
    return next((f for f in folder.glob('*.png') if f.name.lower() == wanted), None)


# Registration ------------------------------------------------------------------------------------------------------

def _gray(rgba):
    import cv2
    return cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY)


def _solid(alpha, px=5):
    import cv2
    import numpy as np
    return cv2.erode((alpha > 250).astype(np.uint8), np.ones((px, px), np.uint8)) > 0


def score(ours, warped):
    """(colour correlation, outline IoU) of a warped scan against ours, both RGBA in one frame. The colours are
    blurred a little, so resampling and the scans' grain don't count."""
    import cv2
    import numpy as np

    both = (ours[..., 3] > 250) & (warped[..., 3] > 250)
    if both.sum() < 100:
        return 0.0, 0.0
    blur = lambda x: cv2.GaussianBlur(_gray(x).astype(np.float32), (0, 0), 2)
    corr = float(np.corrcoef(blur(ours)[both], blur(warped)[both])[0, 1])
    a, b = ours[..., 3] > 127, warped[..., 3] > 127
    return (0.0 if math.isnan(corr) else corr), float((a & b).sum() / (a | b).sum())


def outline_length(alpha):
    """px along an image's outline (a frame edge counts where the tile reaches it)."""
    import cv2
    import numpy as np
    inside = np.pad((alpha > 127).astype(np.uint8), 1)
    return int((inside - cv2.erode(inside, np.ones((3, 3), np.uint8))).sum())


def reasons(info):
    """Why the review page flags a fit (none: it isn't)."""
    found = []
    if info.get('fits_better'):
        found.append(f"its scan fits {info['fits_better']['side']}'s image better ({info['fits_better']['corr']}, "
                     f"against {info['corr']} for its own)")
    if info['corr'] < GOOD:
        found.append(f"colour correlation {info['corr']} (below {GOOD})")
    if info['iou'] < OVERLAP:
        found.append(f"outline overlap {info['iou']} (below {OVERLAP})")
    if info['band'] > BAND:
        found.append(f"{info['band']} px of the scan outside the frame (over {BAND})")
    return found


def weak(info):
    return bool(reasons(info))


def warp(scan, M, size):
    import cv2
    import numpy as np
    return cv2.warpAffine(scan, np.asarray(M, np.float32), size, flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def by_features(ours, scan):
    """A similarity (2 x 3, scan px -> ours px) from SIFT matches, or None."""
    import cv2
    import numpy as np

    sift = cv2.SIFT_create(nfeatures=8000)
    ka, da = sift.detectAndCompute(_gray(ours), _solid(ours[..., 3]).astype(np.uint8))
    kb, db = sift.detectAndCompute(_gray(scan), _solid(scan[..., 3]).astype(np.uint8))
    if da is None or db is None or len(ka) < 8 or len(kb) < 8:
        return None
    pairs = cv2.BFMatcher().knnMatch(db, da, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return None
    M, inliers = cv2.estimateAffinePartial2D(np.float32([kb[m.queryIdx].pt for m in good]),
                                             np.float32([ka[m.trainIdx].pt for m in good]),
                                             method=cv2.RANSAC, ransacReprojThreshold=3, maxIters=5000)
    return None if M is None or inliers.sum() < 8 else M


def by_outline(ours, scan):
    """For a plain tile: the quarter turn and scale that best fit the scan's outline (and colours) onto ours."""
    import numpy as np

    h, w = ours.shape[:2]
    H, W = scan.shape[:2]
    best = None
    for k in range(4):
        sh, sw = np.rot90(scan[..., 3], k).shape
        # numpy's rot90, k quarter turns counter-clockwise, as a matrix on (x, y), then scaled onto ours: scan px ->
        # ours px.
        R = {0: [[1, 0, 0], [0, 1, 0]], 1: [[0, 1, 0], [-1, 0, W - 1]],
             2: [[-1, 0, W - 1], [0, -1, H - 1]], 3: [[0, -1, H - 1], [1, 0, 0]]}[k]
        R = np.vstack([np.float32(R), [0, 0, 1]])
        S = np.diag([w / sw, h / sh, 1]).astype(np.float32)
        M = (S @ R)[:2]
        corr, iou = score(ours, warp(scan, M, (w, h)))
        if best is None or corr + iou > best[0]:
            best = (corr + iou, M)
    return best[1]


def refine(ours, scan, M, channel):
    """M refined by ECC (affine) on the colours ('colour') or the outline ('outline'), or None if ECC fails."""
    import cv2
    import numpy as np

    h, w = ours.shape[:2]
    start = warp(scan, M, (w, h))
    if channel == 'colour':
        template, image = _gray(ours).astype(np.float32), _gray(start).astype(np.float32)
        mask = (_solid(start[..., 3], 9) & _solid(ours[..., 3], 9)).astype(np.uint8)
    else:
        blur = lambda a: cv2.GaussianBlur(a.astype(np.float32), (0, 0), 3)
        template, image = blur(ours[..., 3]), blur(start[..., 3])
        mask = None
    try:
        _, D = cv2.findTransformECC(template, image, np.eye(2, 3, dtype=np.float32), cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), mask, 5)
    except cv2.error:
        return None
    # D maps ours' px to the start's px (ECC's warp of the input); the scan -> ours map is D's inverse after M.
    full = lambda A: np.vstack([np.asarray(A, np.float64), [0, 0, 1]])
    return (np.linalg.inv(full(D)) @ full(M))[:2]


def register(ours, scan):
    """(M scan px -> ours px, how, (corr, iou)): features (or the outline), then the best of the ECC refinements."""
    M = by_features(ours, scan)
    how = 'features'
    if M is None:
        M, how = by_outline(ours, scan), 'outline'
    size = ours.shape[1], ours.shape[0]
    candidates = [(M, how)]
    for channel in ('colour', 'outline'):
        refined = refine(ours, scan, M, channel)
        if refined is not None:
            candidates.append((refined, f'{how} + ECC on the {channel}'))
    scored = [(sum(score(ours, warp(scan, C, size))), C, h) for C, h in candidates]
    total, M, how = max(scored, key=lambda s: s[0])
    return M, how, score(ours, warp(scan, M, size))


def turn_of(M):
    """The quarter turns (clockwise degrees) a registration gives the scan, to the nearest."""
    return round(math.degrees(math.atan2(M[1][0], M[0][0])) / 90) % 4 * 90


# Colour ------------------------------------------------------------------------------------------------------------

def tone_curve(src, dst):
    """A 256-entry curve that maps src's histogram onto dst's (both 1-D uint8 samples)."""
    import numpy as np

    hs = np.bincount(src, minlength=256).cumsum() / len(src)
    hd = np.bincount(dst, minlength=256).cumsum() / len(dst)
    return np.clip(np.interp(hs, hd, np.arange(256)), 0, 255).round().astype(np.uint8)


def apply_curves(rgba, curves):
    out = rgba.copy()
    for c in range(3):
        out[..., c] = curves[c][rgba[..., c]]
    return out


# Run ---------------------------------------------------------------------------------------------------------------

def run(dataset, scans=None, out=None, only=None, log=print, page=True):
    """(manifest, problems). only: keys ("Core Set 01 A") to do; with an earlier full run, its tone curves and other
    sides are kept."""
    import cv2
    import numpy as np
    from PIL import Image

    scans = Path(scans or scans_dir())
    out = Path(out or out_dir())
    (out / 'map-tiles').mkdir(parents=True, exist_ok=True)

    def ours_of(tile, field):
        image = np.array(Image.open(dataset.root / 'images' / 'large' / tile[field]).convert('RGBA'))
        k = SQUARE / 64
        return cv2.resize(image, (round(image.shape[1] * k), round(image.shape[0] * k)), interpolation=cv2.INTER_CUBIC)

    every = sides(dataset)
    problems, fitted, scanned = [], {}, {}
    for key, product, tile, side, field in every:
        if only and key not in only:
            continue
        file = scan_file(product, tile['number'], side, scans)
        if file is None:
            problems.append(f'{key}: no scan')
            continue
        ours = ours_of(tile, field)
        scan = np.array(Image.open(file).convert('RGBA'))
        ys, xs = np.where(scan[..., 3] > 0)
        scan = scan[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        scan = cv2.resize(scan, None, fx=SQUARE / SCAN_PX, fy=SQUARE / SCAN_PX, interpolation=cv2.INTER_AREA)
        scanned[key] = scan
        M, how, (corr, iou) = register(ours, scan)
        size = ours.shape[1], ours.shape[0]
        warped = warp(scan, M, size)
        # Scan pixels the frame cuts off (the outline sticking out of ours' frame): the scan drawn with 100 px of room
        # all round, against the frame.
        roomy = np.float32(M).copy()
        roomy[:, 2] += 100
        clipped = int((cv2.warpAffine(scan[..., 3], roomy, (size[0] + 200, size[1] + 200)) > 127).sum()
                      - (warped[..., 3] > 127).sum())
        fitted[key] = {'product': product, 'tile': tile, 'field': field, 'ours': ours, 'warped': warped,
                       'info': {'scan': file.name, 'file': tile[field], 'turn': turn_of(M), 'how': how,
                                'corr': round(corr, 3), 'iou': round(iou, 4), 'clipped': clipped,
                                'band': round(max(clipped, 0) / outline_length(ours[..., 3]), 2),
                                'scale': round(math.hypot(M[0][0], M[1][0]) * SCAN_PX, 1)}}
        log(f"  {key}: {how}, turn {fitted[key]['info']['turn']}, corr {corr:.3f}, outline IoU {iou:.3f}, "
            f"{fitted[key]['info']['band']} px outside the frame")

    # A weak fit may be a scan of another side, or of a tile printed with another's art (Heart_13A.png fits 15A's
    # image, its number pill says 13A): try it on the product's other sides of the same size, and flag one that fits
    # clearly better, for the maintainer to look at.
    for key, f in list(fitted.items()):
        if f['info']['corr'] >= GOOD:
            continue
        tile = f['tile']
        best = None
        for other, product, other_tile, _, other_field in every:
            if other == key or product != f['product'] or other_tile['squares'] != tile['squares'] or \
                    sorted((other_tile['width'], other_tile['height'])) != sorted((tile['width'], tile['height'])):
                continue
            if not (dataset.root / 'images' / 'large' / other_tile[other_field]).exists():
                continue
            theirs = ours_of(other_tile, other_field)
            M = by_features(theirs, scanned[key])
            corr = M is not None and score(theirs, warp(scanned[key], M, (theirs.shape[1], theirs.shape[0])))[0]
            if corr and corr > f['info']['corr'] + 0.05 and (best is None or corr > best[0]):
                best = (corr, other)
        if best:
            f['info']['fits_better'] = {'side': best[1], 'corr': round(best[0], 3)}
            log(f"  {key}: its scan fits {best[1]}'s image better ({best[0]:.3f})")

    # A run of some sides (only) keeps the last full run's tone curves and sides, and updates these.
    earlier = json.loads((out / 'manifest.json').read_text(encoding='utf-8')) if only and (
        out / 'manifest.json').exists() else {'luts': {}, 'sides': {}}
    rng = np.random.default_rng(0)
    curves = {p: np.array(c, np.uint8) for p, c in earlier['luts'].items()}
    for product in PREFIXES:
        if product in curves:
            continue
        src, dst = [], []
        for f in fitted.values():
            if f['product'] != product or f['info']['corr'] < GOOD:
                continue
            both = np.flatnonzero(((f['ours'][..., 3] > 250) & (f['warped'][..., 3] > 250)).ravel())
            pick = rng.choice(both, min(len(both), 40000), replace=False)
            src.append(f['warped'][..., :3].reshape(-1, 3)[pick])
            dst.append(f['ours'][..., :3].reshape(-1, 3)[pick])
        if src:
            src, dst = np.concatenate(src), np.concatenate(dst)
            curves[product] = np.stack([tone_curve(src[:, c], dst[:, c]) for c in range(3)])
        elif any(f['product'] == product for f in fitted.values()):
            problems.append(f'{product}: no side fits well enough for its tone curve')
    sides_info = dict(earlier['sides'])
    for key, f in fitted.items():
        if f['product'] not in curves:
            continue
        final = apply_curves(f['warped'], curves[f['product']])
        f['info']['after'] = round(score(f['ours'], final)[0], 3)
        Image.fromarray(final).save(out / f['info']['file'], optimize=True)
        sides_info[key] = f['info']
    order = [key for key, *_ in sides(dataset)]
    manifest = {'square': SQUARE, 'luts': {p: c.tolist() for p, c in curves.items()},
                'sides': dict(sorted(sides_info.items(), key=lambda item: order.index(item[0])))}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    if page:
        review(dataset, manifest, out)
    return manifest, problems


# Review ------------------------------------------------------------------------------------------------------------

SHORT = {'Imperial Assault': 'Core', 'Twin Shadows': 'TS', 'Return to Hoth': 'H', 'The Bespin Gambit': 'BG',
         "Jabba's Realm": 'JR', 'Heart of the Empire': 'HotE', 'Tyrants of Lothal': 'ToL'}


def covered(alpha, rotation, x, y, px):
    """The squares a placement covers: its side's grid turned clockwise by rotation, a square counted when the tile
    is at its centre, from (x, y)."""
    import numpy as np
    from ia_tools.campaign_maps import grid_rect

    turned = np.rot90(alpha, -rotation // 90)
    x0, y0, w, h = grid_rect(turned, px)
    return {(x + i, y + j) for i in range(w) for j in range(h)
            if turned[y0 + j * px + px // 2, x0 + i * px + px // 2] > 127}


def usages(dataset):
    """{side key: {"map", "section", "placement", "neighbours": [placement], "touching"}}: for each tile side, the
    placement in map-layouts where it touches the most other tiles (then the most square edges shared), with those
    tiles. A placement here: {"tile_id", "side", "x", "y", "rotation"}, on one of the map's images."""
    import numpy as np
    from PIL import Image

    tiles = {t['id']: t for t in dataset.records('map-tiles')}
    maps = {m['id']: m['name'] for m in dataset.records('maps')}
    alphas, images = {}, {}
    for row in dataset.records('map-layouts'):
        for p in row['placements']:
            images.setdefault((row['map_id'], p['section']), []).append(
                {'tile_id': row['tile_id'], 'side': row['side'], 'x': p['x'], 'y': p['y'], 'rotation': p['rotation']})
    best = {}
    for (map_id, section), placed in images.items():
        squares = []
        for p in placed:
            field = f"side_{p['side'].lower()}"
            path = tiles[p['tile_id']][field]
            if path not in alphas:
                alphas[path] = np.array(Image.open(dataset.root / 'images' / 'large' / path).convert('RGBA'))[..., 3]
            squares.append(covered(alphas[path], p['rotation'], p['x'], p['y'], 64))
        for i, p in enumerate(placed):
            edges = {(x + dx, y + dy) for x, y in squares[i] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))}
            edges -= squares[i]
            touching = [j for j in range(len(placed)) if j != i and squares[j] & edges]
            shared = sum(len(squares[j] & edges) for j in touching)
            tile = tiles[p['tile_id']]
            key = f"{tile['name']} {p['side']}"
            rank = (len(touching), shared, maps[map_id])
            if key not in best or rank[:2] > best[key]['rank'][:2] or (
                    rank[:2] == best[key]['rank'][:2] and rank[2] < best[key]['rank'][2]):
                best[key] = {'rank': rank, 'map': maps[map_id], 'section': section, 'placement': p,
                             'neighbours': [placed[j] for j in touching], 'touching': len(touching), 'shared': shared}
    return best


def draw_usage(dataset, use, image_of, px):
    """The spot of a map a usage shows: its side and the tiles it touches, drawn at px per square from image_of(tile,
    side) (RGBA arrays), cropped to the side's grid plus a square all round. The side is drawn last, on top."""
    import numpy as np
    from PIL import Image
    from ia_tools.campaign_maps import grid_rect

    tiles = {t['id']: t for t in dataset.records('map-tiles')}
    page = None
    pieces = []
    for p in use['neighbours'] + [use['placement']]:
        image = np.rot90(image_of(tiles[p['tile_id']], p['side']), -p['rotation'] // 90)
        x0, y0, w, h = grid_rect(image[..., 3], px)
        pieces.append((image, p['x'] * px - x0, p['y'] * px - y0, (p['x'], p['y'], w, h)))
    _, _, _, (sx, sy, sw, sh) = pieces[-1]
    left, top = (sx - 1) * px, (sy - 1) * px
    width, height = (sw + 2) * px, (sh + 2) * px
    page = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    for image, x, y, _ in pieces:
        layer = Image.new('RGBA', page.size, (0, 0, 0, 0))
        layer.paste(Image.fromarray(np.ascontiguousarray(image)), (x - left, y - top))
        page = Image.alpha_composite(page, layer)
    return page


def review(dataset, manifest, out):
    """index.html and review/: every side in the tiles' file order, a collapsible section per product; flagged sides
    first in a list at the top, and marked in red. Per side: its current image, the new one, and the spot of a map
    where it touches the most other tiles, drawn with the current tiles and with the new ones."""
    import os

    import numpy as np
    from PIL import Image

    (out / 'review').mkdir(exist_ok=True)
    for old in (out / 'review').glob('*.png'):  # the PNGs earlier pages had
        old.unlink()
    data = dataset.root / 'images' / 'large'
    rel = Path(os.path.relpath(data, out)).as_posix()  # relative, so any browser opening the file finds them

    def current(tile, side):
        return np.array(Image.open(data / tile[f'side_{side.lower()}']).convert('RGBA'))

    def new(tile, side):
        path = out / tile[f'side_{side.lower()}']
        return np.array(Image.open(path).convert('RGBA')) if path.exists() else (
            np.array(Image.fromarray(current(tile, side)).resize(
                (current(tile, side).shape[1] * 2, current(tile, side).shape[0] * 2))))

    uses = usages(dataset)
    groups, flagged = {}, []
    for key, product, tile, side, field in sides(dataset):
        info = manifest['sides'].get(key)
        groups.setdefault(product, []).append((key, tile, side, info))
        if info is None or weak(info):
            flagged.append((key, product))
    slug = lambda key: key.lower().replace("'", '').replace(' ', '-')
    css = """
body{font:14px system-ui,sans-serif;margin:16px;background:#1e1e1e;color:#ddd}a{color:#9cf}
details.set{margin:10px 0;border:1px solid #444;border-radius:6px;padding:4px 10px}
details.set>summary{cursor:pointer;font-size:16px;font-weight:600;padding:6px 0}
.side{margin:12px 0 18px;padding:8px;border-radius:6px;background:#262626}
.side.flag{background:#3a1d1d;outline:2px solid #e55}
.side h3{margin:0 0 4px;font-size:14px}.flags{margin:4px 0;color:#fbb;font-weight:600}
.flags li{margin-left:18px}.meta{font-size:12px;opacity:.75;margin-bottom:6px}
.imgs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;align-items:start;max-width:1400px}
.imgs figure{margin:0}.imgs img{max-width:100%;height:auto;display:block;background:#333}
figcaption{font-size:12px;opacity:.8;margin-top:3px}.count{font-weight:normal;opacity:.7}
.badge{background:#e55;color:#fff;border-radius:10px;padding:1px 8px;font-size:12px;margin-left:6px}
.top{background:#3a1d1d;border:2px solid #e55;border-radius:6px;padding:8px 12px}"""
    page = [f'<!doctype html><meta charset="utf-8"><title>High-res tiles</title><style>{css}</style>',
            f'<h1>High-res tiles: {len(manifest["sides"])} sides at {manifest["square"]} px per square</h1>',
            '<p>Each side: the current image (Vassal, 64 px per square), the new one (the scan fitted onto it and '
            'colour-corrected), then the spot of a map where the side touches the most other tiles, drawn with the '
            'current tiles and with the new ones, to check how it fits its set. Click an image to open it.</p>']
    if flagged:
        page.append(f'<div class="top"><b>{len(flagged)} flagged</b>: ' + ', '.join(
            f'<a href="#{slug(k)}">{html.escape(k)}</a>' for k, _ in flagged) + '</div>')
    for product, members in groups.items():
        bad = sum(1 for k, _ in flagged if _ == product)
        page.append(f'<details class="set"><summary>{SHORT[product]}: '
                    f'{html.escape(members[0][1]["name"].rsplit(" ", 1)[0])} <span class="count">{len(members)} '
                    f'sides</span>{f"<span class=badge>{bad} flagged</span>" if bad else ""}</summary>')
        for key, tile, side, info in members:
            s = slug(key)
            found = reasons(info) if info else ['no high-res image (no scan, or not staged)']
            use = uses.get(key)
            figures = [f'<figure><a href="{rel}/{tile["side_" + side.lower()]}"><img loading="lazy" '
                       f'src="{rel}/{tile["side_" + side.lower()]}"></a><figcaption>current (Vassal)</figcaption></figure>']
            if info:
                figures.append(f'<figure><a href="{info["file"]}"><img loading="lazy" src="{info["file"]}"></a>'
                               '<figcaption>new (high-res)</figcaption></figure>')
            else:
                figures.append('<figure><figcaption>no high-res image</figcaption></figure>')
            if use:
                where = f'{use["map"]}' + (f' ({use["section"]})' if use['section'] else '')
                for label, image_of, px in (('current tiles', current, 64), ('new tiles', new, SQUARE)):
                    # JPEG on the page's grey: these are only to look at, and PNGs of them run to hundreds of MB.
                    file = f'review/{s}-{"vassal" if px == 64 else "hires"}.jpg'
                    drawn = draw_usage(dataset, use, image_of, px)
                    flat = Image.new('RGB', drawn.size, (51, 51, 51))
                    flat.paste(drawn, mask=drawn.getchannel('A'))
                    flat.save(out / file, quality=88)
                    figures.append(f'<figure><a href="{file}"><img loading="lazy" src="{file}"></a><figcaption>'
                                   f'{html.escape(where)}, {label}: touches {use["touching"]} tiles</figcaption></figure>')
            else:
                figures.append('<figure><figcaption>not used on any map, so no map spot to show</figcaption></figure>')
            meta = (f'{html.escape(info["scan"])}: {html.escape(info["how"])}, turned {info["turn"]}°, {info["scale"]} '
                    f'px per square; colour correlation {info["corr"]}, outline overlap {info["iou"]}, {info["band"]} '
                    'px outside the frame') if info else ''
            page.append(f'<div class="side{" flag" if found else ""}" id="{s}"><h3>{html.escape(key)}'
                        f'{"<span class=badge>check</span>" if found else ""}</h3>'
                        + (f'<ul class="flags">{"".join(f"<li>{html.escape(r)}</li>" for r in found)}</ul>' if found else '')
                        + f'<div class="meta">{meta}</div><div class="imgs">{"".join(figures)}</div></div>')
        page.append('</details>')
    # A link to a side (the flagged list, or the address) opens its set.
    page.append("""<script>
function reveal() {
  const side = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (side) { side.closest('details').open = true; side.scrollIntoView(); }
}
addEventListener('hashchange', reveal); reveal();
</script>""")
    (out / 'index.html').write_text('\n'.join(page), encoding='utf-8')
