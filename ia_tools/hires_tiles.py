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
  "how", "corr", "iou", "clipped", "band", "scale", "after"}}}: clipped is the scan's pixels outside our frame, band
  that as px all along our outline (the scans are cut a pixel or so outside the print);
- index.html: a review page, ours and the new side next to each other, the weakest fits first.

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


def weak(info):
    return info['corr'] < GOOD or info['iou'] < OVERLAP or info['band'] > BAND


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

def run(dataset, scans=None, out=None, only=None, log=print):
    """(manifest, problems). only: keys ("Core Set 01 A") to do, for a sample run."""
    import cv2
    import numpy as np
    from PIL import Image

    scans = Path(scans or scans_dir())
    out = Path(out or out_dir())
    (out / 'map-tiles').mkdir(parents=True, exist_ok=True)
    problems, fitted = [], {}
    for key, product, tile, side, field in sides(dataset):
        if only and key not in only:
            continue
        file = scan_file(product, tile['number'], side, scans)
        if file is None:
            problems.append(f'{key}: no scan')
            continue
        ours = np.array(Image.open(dataset.root / 'images' / 'large' / tile[field]).convert('RGBA'))
        k = SQUARE / 64
        ours = cv2.resize(ours, (round(ours.shape[1] * k), round(ours.shape[0] * k)), interpolation=cv2.INTER_CUBIC)
        scan = np.array(Image.open(file).convert('RGBA'))
        ys, xs = np.where(scan[..., 3] > 0)
        scan = scan[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        scan = cv2.resize(scan, None, fx=SQUARE / SCAN_PX, fy=SQUARE / SCAN_PX, interpolation=cv2.INTER_AREA)
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

    rng = np.random.default_rng(0)
    curves = {}
    for product in PREFIXES:
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
    sides_info = {}
    for key, f in fitted.items():
        if f['product'] not in curves:
            continue
        final = apply_curves(f['warped'], curves[f['product']])
        f['info']['after'] = round(score(f['ours'], final)[0], 3)
        Image.fromarray(final).save(out / f['info']['file'], optimize=True)
        sides_info[key] = f['info']
    manifest = {'square': SQUARE, 'luts': {p: c.tolist() for p, c in curves.items()}, 'sides': sides_info}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    review(dataset, manifest, out)
    return manifest, problems


def review(dataset, manifest, out):
    """index.html: each side, ours (upscaled) and the new one, the flagged fits first, then the weakest."""
    import os

    rows = sorted(manifest['sides'].items(), key=lambda item: (not weak(item[1]), item[1]['corr'], item[1]['iou']))
    # Relative, so the page works from any browser that opens the file (Windows' too).
    data = Path(os.path.relpath(dataset.root / 'images' / 'large', out)).as_posix()
    flagged = sum(weak(info) for _, info in rows)
    page = ['<!doctype html><meta charset="utf-8"><title>High-res tiles</title><style>',
            'body{font:14px system-ui;margin:16px;background:#222;color:#ddd}h2{margin:24px 0 4px;font-size:15px}',
            '.row{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}img{width:100%;height:auto}',
            '.row.zoom{grid-template-columns:1fr}.weak{color:#f99}figcaption{font-size:12px;opacity:.8}</style>',
            f'<p><b>{len(rows)} tile sides at {manifest["square"]} px per square</b>; {flagged} flagged (in red: '
            f'colour correlation below {GOOD}, outline overlap below {OVERLAP}, or more than {BAND} px of the scan '
            'outside the frame), first. Left: the current image (Vassal, 64 px per square); right: the scan, fitted '
            'onto it and colour-corrected. Click a row for full size.</p>']
    for key, info in rows:
        page.append(f'<h2 class="{"weak" if weak(info) else ""}">{html.escape(key)}</h2><div>{html.escape(info["scan"])}: '
                    f'{html.escape(info["how"])}, turned {info["turn"]}°, {info["scale"]} px per square in the scan; '
                    f'colour correlation {info["corr"]} (after the curve {info.get("after")}), outline overlap '
                    f'{info["iou"]}, {info["band"]} px outside the frame</div>'
                    '<div class="row" onclick="this.classList.toggle(\'zoom\')">'
                    f'<figure><img loading="lazy" src="{data}/{info["file"]}"><figcaption>current</figcaption></figure>'
                    f'<figure><img loading="lazy" src="{info["file"]}"><figcaption>new</figcaption></figure></div>')
    (out / 'index.html').write_text('\n'.join(page), encoding='utf-8')
