"""ia hires-tiles: the map tiles' sides from the maintainer's scans (tiles/, ~299 px per square), at SQUARE px per
square, staged for the data repo (data 2.x).

Each side's scan (tiles/<Prefix>_<number><side>.png, cut on its outline, any turn) is fitted onto the dataset's image
of that side (first Vassal's; since data PR #94 the stored hi-res one), then straightened on its own printed grid:
- turned upright first, by its number pill's turn (`ia tile-orientation`'s turns.json, "scan"), as the dataset's
  images are stored: the fit then keeps it at that turn;
- scaled by SQUARE / SCAN_PX, then registered onto ours upscaled to SQUARE px per square: SIFT features and a
  similarity (RANSAC), or, for a tile too plain for features (or whose features turn it), its outline (at each
  quarter turn for a scan with no pill turn);
- refined by ECC (affine), on the colours and on the outline, keeping whichever fits best (scored on blurred colour
  correlation and outline overlap with ours);
- straightened (straighten): its printed grid lines found in the fitted image (grid_fit: thin-line response averaged
  along the lines, searched over turn, scale and shift) and the turn, scale and shift that put its inner lines on the
  frame's folded into the fit, so the scan is resampled once. A grid too faint or too far off (GRID_*) is left as
  fitted, and flagged (2026-11-10: most sides sat 1-4 px off, a few turned up to 2 degrees);
- drawn into our side's frame: SQUARE px per square plus SQUARE / 4 at each end of an axis with tabs, as the dataset's
  tiles are at 64 (so a side's grid and tabs land where ours are). Its outline is the scan's own, moved with its art.

`--keep-colours` keeps the last run's tone curves for every product, so a refit only moves the art.

Colours: one tone curve per product and channel, histogram-matched from the scans' pixels to ours, pooled over the
product's well-registered sides (colour correlation >= GOOD); the maintainer chose this from samples
(staging/tile-samples, 2026-11-06).

Writes staging/hires-tiles/:
- map-tiles/<the dataset's file name>: the new sides;
- manifest.json: {"square", "luts": {product: [[256] x 3]}, "sides": {"<tile name> <side>": {"scan", "file", "turn",
  "scan_turn", "how", "corr", "iou", "clipped", "band", "scale", "after", "fits_better"?}}}: clipped is the scan's pixels outside
  our frame, band that as px all along our outline (the scans are cut a pixel or so outside the print), fits_better
  {"side", "corr"} when the scan fits another side's image clearly better than its own; turn the clockwise degrees
  the fit turns the scan (from the file), scan_turn its pill's (a fit at another turn is flagged);
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


def stored(dataset, path, px):
    """A side's stored image (RGBA array) at px per square: images/large, at whatever px per square it has (its size
    against images/small's, which is 64), scaled to px."""
    import cv2
    import numpy as np
    from PIL import Image

    image = np.array(Image.open(dataset.root / 'images' / 'large' / path).convert('RGBA'))
    with Image.open(dataset.root / 'images' / 'small' / path) as small:
        k = px * small.width / (64 * image.shape[1])
    if k == 1:
        return image
    return cv2.resize(image, (round(image.shape[1] * k), round(image.shape[0] * k)),
                      interpolation=cv2.INTER_CUBIC if k > 1 else cv2.INTER_AREA)


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
    if 'scan_turn' in info and info['turn'] != info['scan_turn']:
        found.append(f"fitted at {info['turn']}°, its pill reads upright at {info['scan_turn']}°")
    if info.get('grid', {}).get('skipped'):
        found.append(f"not straightened on its grid: {info['grid']['skipped']}")
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


def by_outline(ours, scan, turns=range(4)):
    """For a plain tile: the quarter turn (of turns) and scale that best fit the scan's outline (and colours) onto
    ours."""
    import numpy as np

    h, w = ours.shape[:2]
    H, W = scan.shape[:2]
    best = None
    for k in turns:
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


def register(ours, scan, upright=False):
    """(M scan px -> ours px, how, (corr, iou)): features (or the outline), then the best of the ECC refinements. An
    upright scan keeps its turn: features that turn it give way to its outline at turn 0."""
    M = by_features(ours, scan)
    how = 'features'
    if M is not None and upright and turn_of(M):
        M = None
    if M is None:
        M, how = by_outline(ours, scan, (0,) if upright else range(4)), 'outline'
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


# Grid -------------------------------------------------------------------------------------------------------------

# A side is straightened on its printed grid lines (thin lines on every square's edge): turned, scaled and shifted so its
# inner grid lines sit on the frame's (margin + k * SQUARE), within these limits; past them the fit is flagged and left
# as it was. A grid whose lines stand out less than GRID_WEAK times the art around them is too faint to go by.
GRID_TURN = 2.0  # degrees
GRID_MOVE = 8.0  # px at SQUARE
GRID_SCALE = 0.02
GRID_WEAK = 2.0


def _grid_lines(rgba):
    """(across x, across y, inside): the thin-line response across vertical and horizontal lines (blurred second
    derivatives), and where the tile is solid (well inside its outline)."""
    import cv2
    import numpy as np

    gray = cv2.GaussianBlur(_gray(rgba).astype(np.float32), (0, 0), 1)
    inside = cv2.erode((rgba[..., 3] > 250).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(np.float32)
    return (np.abs(cv2.Sobel(gray, cv2.CV_32F, 2, 0, ksize=3)) * inside,
            np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 2, ksize=3)) * inside, inside)


def _profile(response, inside, axis):
    """The response averaged along the lines: per column (axis 0) or per row (axis 1), over the solid tile."""
    import numpy as np
    return response.sum(axis) / np.maximum(inside.sum(axis), 1)


def _comb(profile, expected, centre, scale, shift):
    """How strongly the profile peaks at the expected lines scaled about centre and shifted: their mean over the
    profile's median."""
    import numpy as np

    at = centre + (np.asarray(expected, float) - centre) * scale + shift
    if len(at) == 0 or at.min() < 0 or at.max() > len(profile) - 1:
        return 0.0
    base = float(np.median(profile)) or 1e-6
    return float(np.interp(at, np.arange(len(profile)), profile).mean()) / base


def grid_lines(length):
    """The inner grid lines of an axis length px long (SQUARE px per square, tab margins either end)."""
    n = length // SQUARE
    margin = (length - n * SQUARE) // 2
    return [margin + k * SQUARE for k in range(1, n)]


def grid_fit(rgba):
    """Where a side's printed grid is in its frame (a side with a single inner line keeps turn 0: one short line can't
    tell a turn from noise): {"turn": degrees (cv2's, anticlockwise on the page) that square it,
    "scale": its squares' size over SQUARE, "dx", "dy": px its inner lines sit off the frame's (None on an axis without
    one), "strength": how strongly its lines stand out (the weaker axis)}."""
    import cv2
    import numpy as np

    h, w = rgba.shape[:2]
    centre = ((w - 1) / 2, (h - 1) / 2)
    across_x, across_y, inside = _grid_lines(rgba)
    lines_x, lines_y = grid_lines(w), grid_lines(h)
    shifts = np.arange(-10, 10.01, 1.0)

    def turned(angle):
        R = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rot = lambda a: cv2.warpAffine(a, R, (w, h), flags=cv2.INTER_LINEAR)
        m = rot(inside)
        return _profile(rot(across_x), m, 0), _profile(rot(across_y), m, 1)

    def score(px, py, scale=1.0, shifts=shifts):
        sx = max((_comb(px, lines_x, centre[0], scale, d), d) for d in shifts) if lines_x else (0.0, None)
        sy = max((_comb(py, lines_y, centre[1], scale, d), d) for d in shifts) if lines_y else (0.0, None)
        return sx, sy

    def total(sx, sy):
        return sx[0] + sy[0]

    best = None
    # One inner line (a 1 x 2 tile) can't tell a turn from noise: such a side keeps its fitted turn and is only moved.
    searches = ((0.25, GRID_TURN), (0.05, 0.25)) if len(lines_x) + len(lines_y) >= 2 else ((1.0, 0.0),)
    for step, span in searches:
        middle = best[1] if best else 0.0
        for angle in np.arange(middle - span, middle + span + 1e-9, step):
            px, py = turned(float(angle))
            sx, sy = score(px, py)
            if best is None or total(sx, sy) > best[0]:
                best = (total(sx, sy), float(angle))
    angle = best[1]
    px, py = turned(angle)
    fine = np.arange(-10, 10.01, 0.25)
    scale = max(np.arange(1 - GRID_SCALE * 1.5, 1 + GRID_SCALE * 1.5 + 1e-9, 0.0025),
                key=lambda k: total(*score(px, py, k)))
    sx, sy = score(px, py, float(scale), fine)
    strengths = [s for s, d in (sx, sy) if d is not None]
    return {'turn': round(angle, 2), 'scale': round(float(scale), 4), 'dx': sx[1], 'dy': sy[1],
            'strength': round(min(strengths), 2) if strengths else 0.0}


def grid_fix(fit, size):
    """The 3 x 3 correction (frame px -> frame px) that puts a side's grid where its frame's is, from grid_fit."""
    import cv2
    import numpy as np

    w, h = size
    cx, cy = (w - 1) / 2, (h - 1) / 2
    R = np.vstack([cv2.getRotationMatrix2D((cx, cy), fit['turn'], 1.0), [0, 0, 1]])
    s, dx, dy = fit['scale'], fit['dx'] or 0.0, fit['dy'] or 0.0
    # A point of the grid at c + (e - c) s + d goes back to e: p -> c + (p - c - d) / s.
    S = np.array([[1 / s, 0, cx - (cx + dx) / s], [0, 1 / s, cy - (cy + dy) / s], [0, 0, 1]])
    return S @ R


def _plain(fit):
    """A grid fit as JSON values."""
    return {k: (None if v is None else float(v)) for k, v in fit.items()}


def grid_problem(fit):
    """Why a side isn't straightened on its grid (None: it is)."""
    if fit['strength'] < GRID_WEAK:
        return f"its grid lines are too faint to go by ({fit['strength']})"
    if abs(fit['turn']) > GRID_TURN - 0.01:
        return f"its grid is turned {fit['turn']}°, at the edge of what's searched"
    if abs(fit['scale'] - 1) > GRID_SCALE:
        return f"its squares are {fit['scale']} of the frame's"
    off = max(abs(fit['dx'] or 0), abs(fit['dy'] or 0))
    if off > GRID_MOVE:
        return f"its grid is {off} px off the frame's"
    return None


def straighten(scan, M, size):
    """(M, before, after, problem): M with the grid correction folded in (the scan is warped once, from the scan), the
    grid fits before and after, and why it wasn't applied (None: it was)."""
    import numpy as np

    before = grid_fit(warp(scan, M, size))
    problem = grid_problem(before)
    if problem:
        return M, before, before, problem
    fixed = (grid_fix(before, size) @ np.vstack([np.asarray(M, np.float64), [0, 0, 1]]))[:2]
    return fixed, before, grid_fit(warp(scan, fixed, size)), None


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

def upright_turns():
    """{side key: clockwise degrees that make its scan's pill upright}, from `ia tile-orientation` (none before it)."""
    path = settings.STAGING / 'tile-orientation' / 'turns.json'
    turns = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return {key: entry['scan']['turn'] for key, entry in turns.items() if 'scan' in entry}


def run(dataset, scans=None, out=None, only=None, log=print, page=True, upright=None, keep_colours=False):
    """(manifest, problems). only: keys ("Core Set 01 A") to do; with an earlier full run, its tone curves and other
    sides are kept. upright: {key: the scan's pill turn} (default upright_turns()). keep_colours: keep the last run's
    tone curves (manifest.json) for every product, so a refit changes where the art sits but not its colours. Each
    fit is then straightened on the side's printed grid (straighten), unless its grid is too faint or too far off."""
    import cv2
    import numpy as np
    from PIL import Image

    scans = Path(scans or scans_dir())
    out = Path(out or out_dir())
    (out / 'map-tiles').mkdir(parents=True, exist_ok=True)

    def ours_of(tile, field):
        return stored(dataset, tile[field], SQUARE)

    from ia_tools.tile_orientation import k_of_turn

    upright = upright_turns() if upright is None else upright
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
        if key in upright:
            scan = np.ascontiguousarray(np.rot90(scan, k_of_turn(upright[key])))
        scanned[key] = scan
        M, how, _ = register(ours, scan, key in upright)
        size = ours.shape[1], ours.shape[0]
        M, grid_before, grid_after, grid_skip = straighten(scan, M, size)
        warped = warp(scan, M, size)
        corr, iou = score(ours, warped)
        # Scan pixels the frame cuts off (the outline sticking out of ours' frame): the scan drawn with 100 px of room
        # all round, against the frame.
        roomy = np.float32(M).copy()
        roomy[:, 2] += 100
        clipped = int((cv2.warpAffine(scan[..., 3], roomy, (size[0] + 200, size[1] + 200)) > 127).sum()
                      - (warped[..., 3] > 127).sum())
        fitted[key] = {'product': product, 'tile': tile, 'field': field, 'ours': ours, 'warped': warped,
                       'info': {'scan': file.name, 'file': tile[field],
                                'turn': (upright.get(key, 0) + turn_of(M)) % 360,
                                **({'scan_turn': upright[key]} if key in upright else {}), 'how': how,
                                'corr': round(corr, 3), 'iou': round(iou, 4), 'clipped': clipped,
                                'band': round(max(clipped, 0) / outline_length(ours[..., 3]), 2),
                                'scale': round(math.hypot(M[0][0], M[1][0]) * SCAN_PX, 1),
                                'grid': {'before': _plain(grid_before), 'after': _plain(grid_after),
                                         **({'skipped': grid_skip} if grid_skip else {})}}}
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
    earlier = json.loads((out / 'manifest.json').read_text(encoding='utf-8')) if (only or keep_colours) and (
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
            squares.append(covered(alphas[path], p['rotation'], p['x'], p['y'], SQUARE))  # large images: SQUARE px
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
                             'neighbours': [placed[j] for j in touching], 'touching': len(touching), 'shared': shared,
                             'others': [placed[j] for j in range(len(placed)) if j != i]}
    return best


def draw_usage(dataset, use, image_of, px):
    """The spot of a map a usage shows: its side and every other tile of that map image inside the spot (the tiles it
    touches, and those at its corners), drawn at px per square from image_of(tile, side) (RGBA arrays), cropped to the
    side's grid plus a square all round. The side is drawn last, on top."""
    import numpy as np
    from PIL import Image
    from ia_tools.campaign_maps import grid_rect

    tiles = {t['id']: t for t in dataset.records('map-tiles')}
    page = None
    pieces = []
    for p in use.get('others', use['neighbours']) + [use['placement']]:
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


def cut_offsets(alpha, px=SQUARE):
    """(x, y): how far a side's straight cut edges sit off its frame's outer grid lines, px (the mean of the two
    opposite edges; None on an axis without both), measured beside the corners, clear of the tabs and notches."""
    import numpy as np

    a = alpha > 127
    H, W = a.shape
    gw, gh = W // px, H // px
    mx, my = (W - gw * px) // 2, (H - gh * px) // 2
    filled = lambda i, j: 0 <= i < gw and 0 <= j < gh and a[my + j * px + px // 2, mx + i * px + px // 2]
    edges = {'L': [], 'R': [], 'T': [], 'B': []}
    reach = px * 20 // 128
    for i in range(gw):
        for j in range(gh):
            if not filled(i, j):
                continue
            x0, y0 = mx + i * px, my + j * px
            for f in (0.15, 0.85):
                yy, xx = int(y0 + f * px), int(x0 + f * px)
                if not filled(i - 1, j) and (e := np.where(a[yy, max(0, x0 - 6):x0 + reach])[0]).size:
                    edges['L'].append(max(0, x0 - 6) + e.min() - x0)
                if not filled(i + 1, j) and (e := np.where(a[yy, x0 + px - reach:min(W, x0 + px + 6)])[0]).size:
                    edges['R'].append(x0 + px - reach + e.max() + 1 - (x0 + px))
                if not filled(i, j - 1) and (e := np.where(a[max(0, y0 - 6):y0 + reach, xx])[0]).size:
                    edges['T'].append(max(0, y0 - 6) + e.min() - y0)
                if not filled(i, j + 1) and (e := np.where(a[y0 + px - reach:min(H, y0 + px + 6), xx])[0]).size:
                    edges['B'].append(y0 + px - reach + e.max() + 1 - (y0 + px))
    mid = lambda one, two: float((np.median(edges[one]) + np.median(edges[two])) / 2) if edges[one] and edges[two] \
        else None
    return mid('L', 'R'), mid('T', 'B')


def shifted(rgba, dx, dy):
    """The image moved by (dx, dy) px (sub-pixel), in the same frame."""
    import cv2
    import numpy as np

    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(rgba, M, (rgba.shape[1], rgba.shape[0]), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


PRINT_CUT = 4.0  # px at SQUARE: print and cut this far apart (or more) are flagged


def review(dataset, manifest, out):
    """index.html and review/: a row per side, three images: art on the grid (left: the side straightened on its
    printed grid lines, as staged), the current side (centre, the data repo's), cut on the grid (right: the
    straightened side moved so its cut edges sit on the frame instead). A toggle swaps them for the spot of a map where
    the side touches the most other tiles, every tile drawn in that version. The most problematic sides are flagged
    and listed first."""
    import os

    import numpy as np
    from PIL import Image

    (out / 'review').mkdir(exist_ok=True)
    (out / 'cut').mkdir(exist_ok=True)
    for old in (out / 'review').glob('*'):
        old.unlink()
    data = dataset.root / 'images' / 'large'
    rel = Path(os.path.relpath(data, out)).as_posix()
    cache = {}

    def load(path):
        if path not in cache:
            cache[path] = np.array(Image.open(path).convert('RGBA'))
        return cache[path]

    def current(tile, side):
        return load(data / tile[f'side_{side.lower()}'])

    def art(tile, side):
        path = out / tile[f'side_{side.lower()}']
        return load(path) if path.exists() else current(tile, side)

    cut_shift = {}

    def cut(tile, side):
        path = out / 'cut' / tile[f'side_{side.lower()}']
        if path not in cache:
            image = art(tile, side)
            sx, sy = cut_offsets(image[..., 3])
            cut_shift[tile[f'side_{side.lower()}']] = (sx, sy)
            cache[path] = shifted(image, -(sx or 0.0), -(sy or 0.0))
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(cache[path]).save(path)
        return cache[path]

    def jpg(image, name, px_per_square=None):
        im = image if isinstance(image, Image.Image) else Image.fromarray(np.ascontiguousarray(image))
        flat = Image.new('RGB', im.size, (51, 51, 51))
        flat.paste(im, mask=im.getchannel('A'))
        flat.save(out / 'review' / name, quality=88)
        return f'review/{name}'

    def grid_lines_all(length):
        """Every grid line of an axis length px long, its outer ones included."""
        n = length // SQUARE
        margin = (length - n * SQUARE) // 2
        return [margin + k * SQUARE for k in range(n + 1)]

    def guides(width, height, xs, ys, view):
        """An SVG over an image (same px), the frame's grid lines where the squares should be."""
        lines = ''.join(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}"/>' for x in xs)
        lines += ''.join(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}"/>' for y in ys)
        return (f'<svg class="guides {view}" viewBox="0 0 {width} {height}" preserveAspectRatio="none">{lines}'
                '</svg>')

    uses = usages(dataset)
    slug = lambda key: key.lower().replace("'", '').replace(' ', '-')
    rows, flagged = [], []
    for key, product, tile, side, field in sides(dataset):
        info = manifest['sides'].get(key)
        cut(tile, side)
        sx, sy = cut_shift[tile[field]]
        apart = max(abs(sx or 0), abs(sy or 0))
        problems = []
        grid = (info or {}).get('grid')
        if info is None:
            problems.append((9, 'No high-res image: no scan, or not staged.'))
        elif grid and grid.get('skipped'):
            problems.append((8, f"Not straightened: {grid['skipped']}. Left and centre are the same fit."))
        if apart >= PRINT_CUT:
            problems.append((apart, f'Its print and its cut are {apart:.1f} px apart (at 128 px per square): with the '
                                    'art on the grid, its edges overlap or gap that much against its neighbours; with '
                                    'the cut on the grid, its printed lines are that much off theirs.'))
        if info:
            for r in reasons(info):
                if 'grid' not in r:
                    problems.append((1, f'Fit: {r}.'))
        severity = max((s for s, _ in problems), default=0)
        if severity >= PRINT_CUT or any(s >= 8 for s, _ in problems):
            flagged.append((severity, key))
        rows.append((key, product, tile, side, field, info, grid, (sx, sy), problems, severity))

    order = {k: n for n, (_, k) in enumerate(sorted(flagged, reverse=True))}
    e = html.escape
    blocks = []
    for key, product, tile, side, field, info, grid, (sx, sy), problems, severity in rows:
        s = slug(key)
        use = uses.get(key)
        versions = [('art', 'Art on the grid', art), ('now', 'Now (in the data)', current), ('cut', 'Cut on the grid', cut)]
        figures = []
        for name, label, image_of in versions:
            image = image_of(tile, side)
            tile_img = jpg(image, f'{s}-{name}.jpg')
            drawn = draw_usage(dataset, use, image_of, SQUARE) if use else None
            spot = jpg(drawn, f'{s}-{name}-map.jpg') if use else None
            th, tw = image.shape[:2]
            tile_guides = guides(tw, th, grid_lines_all(tw), grid_lines_all(th), 'tile')
            map_guides = guides(drawn.width, drawn.height, range(0, drawn.width + 1, SQUARE),
                                range(0, drawn.height + 1, SQUARE), 'map') if use else ''
            figures.append(f'<figure class="{name}"><div class="pic"><img loading="lazy" src="{tile_img}" '
                           f'data-tile="{tile_img}" data-map="{spot or tile_img}">{tile_guides}{map_guides}</div>'
                           f'<figcaption>{label}</figcaption></figure>')
        if grid:
            b = grid['before']
            moved = ', '.join(f'{"left/right" if a == "dx" else "up/down"} {b[a]:+g} px' for a in ('dx', 'dy')
                              if b[a] is not None and b[a])
            turned = f'turned {b["turn"]:+g}°, ' if b['turn'] else ''
            sized = f'scale {b["scale"]:g}, ' if b['scale'] != 1 else ''
            art_note = f'{turned}{sized}{moved}' or 'already on the grid'
        else:
            art_note = 'no grid fit'
        cut_note = ', '.join(f'{"left/right" if a == 0 else "up/down"} {v:+.1f} px' for a, v in enumerate((sx, sy))
                             if v is not None and abs(v) >= 0.5) or 'cut already on the grid'
        where = f'{use["map"]}{" (" + use["section"] + ")" if use["section"] else ""}, with the {use["touching"]} ' \
                f'tiles it touches' if use else 'on no map, so no map spot'
        flag = key in order
        blocks.append((order.get(key, len(order)) if flag else None, product, f"""
<div class="side{' flag' if flag else ''}" id="{s}">
  <h3>{e(key)}{' <span class="badge">check</span>' if flag else ''}</h3>
  {''.join(f'<p class="problem">{e(t)}</p>' for _, t in sorted(problems, reverse=True))}
  <div class="row">{''.join(figures)}</div>
  <p class="note"><b>Art on the grid</b>: the scan as fitted was {e(art_note)} off the frame's grid lines; moved so
  they meet. <b>Cut on the grid</b>: the same, moved again so its cut edges sit on the frame ({e(cut_note)} from the
  left image). Map spot: {e(where)}.</p>
</div>"""))

    css = """
body{font:14px/1.45 system-ui,sans-serif;margin:0;background:#1e1e1e;color:#ddd}a{color:#9cf}
main{padding:0 16px 40px;max-width:1500px}
.bar{position:sticky;top:0;z-index:2;background:#151515;border-bottom:1px solid #444;padding:8px 16px;display:flex;
  gap:10px;align-items:center;flex-wrap:wrap}
.bar button{background:#333;color:#eee;border:1px solid #555;border-radius:4px;padding:4px 12px;cursor:pointer}
.bar button[aria-pressed="true"]{background:#1f5fbf;border-color:#7fb0ff}
.legend{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0}
.legend div{background:#262626;border-radius:6px;padding:8px}
details.set{margin:10px 0;border:1px solid #444;border-radius:6px;padding:4px 10px}
details.set>summary{cursor:pointer;font-size:16px;font-weight:600;padding:6px 0}
.side{margin:12px 0 18px;padding:8px;border-radius:6px;background:#262626}
.side.flag{background:#3a1d1d;outline:2px solid #e55}
.side h3{margin:0 0 4px;font-size:15px}.problem{margin:2px 0;color:#fbb}
.row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;align-items:start}
.pic{position:relative}.pic svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.guides line{stroke:#0ff;stroke-width:1.5;vector-effect:non-scaling-stroke;opacity:.8}
body[data-show="tile"] .guides.map,body[data-show="map"] .guides.tile,body.noguides .guides{display:none}
.row figure{margin:0}.row img{max-width:100%;height:auto;display:block;background:#333}
.row .now img{outline:2px solid #888}
figcaption{font-size:12px;opacity:.85;margin-top:3px;text-align:center}.note{font-size:12px;opacity:.75;margin:6px 0 0}
.badge{background:#e55;color:#fff;border-radius:10px;padding:1px 8px;font-size:12px;margin-left:6px}
.top{background:#3a1d1d;border:2px solid #e55;border-radius:6px;padding:8px 12px;margin:12px 0}"""
    flagged_sorted = sorted(flagged, reverse=True)
    page = [f'<!doctype html><meta charset="utf-8"><title>Tiles on their grid</title><style>{css}</style>',
            '<div class="bar"><b>Show:</b> <button type="button" data-show="tile" aria-pressed="true">the tiles</button>'
            '<button type="button" data-show="map">the tiles on a map</button>'
            '<label style="margin-left:12px"><input type="checkbox" id="guides" checked> grid guide lines</label>'
            '<span style="opacity:.7">(cyan: where the squares should be; the map view draws every tile around '
            'it in the same version)</span></div><main>',
            f'<h1>Tiles on their grid: {len(rows)} sides</h1>',
            '<p>Every tile has thin printed lines on the edges of its squares. On your scans, the print sits a few '
            'pixels off where the tile\'s squares are in its image, and the printed tile\'s cut is a few pixels off '
            'its print, by different amounts on each tile. So on a map either the printed lines meet, or the cut '
            'edges do, not both. Each row shows one side three ways:</p>',
            '<div class="legend"><div><b>Left: art on the grid</b><br>Turned and moved so its printed lines sit '
            'exactly on its squares. Lines and art continue from tile to tile; the cut edges may overlap or leave a '
            'gap of a few px.</div><div><b>Centre: now</b><br>The tile as it is in the data today (outlined).</div>'
            '<div><b>Right: cut on the grid</b><br>Turned like the left, then moved so its cut edges sit exactly on '
            'its squares. Tiles meet edge to edge; the printed lines may be a few px off their neighbours\'.</div>'
            '</div>',
            '<p>Use <b>the tiles on a map</b> (top) to see each version where the side touches the most other tiles. '
            'Sizes are at 128 px per square; the site shows half that.</p>']
    if flagged_sorted:
        page.append(f'<div class="top"><b>{len(flagged_sorted)} to check</b>, worst first: ' + ', '.join(
            f'<a href="#{slug(k)}">{e(k)}</a>' for _, k in flagged_sorted) + '</div>')
        page.append('<h2>To check</h2>')
        for _, product, block in sorted((b for b in blocks if b[0] is not None), key=lambda b: b[0]):
            page.append(block)
    page.append('<h2>Every side, by box</h2>')
    for product in PREFIXES:
        members = [b for b in blocks if b[1] == product]
        if members:
            page.append(f'<details class="set"><summary>{e({"Imperial Assault": "Core Set"}.get(product, product))}: {len(members)} sides</summary>'
                        + ''.join(b[2] for b in members) + '</details>')
    page.append("""</main><script>
const buttons = document.querySelectorAll('.bar button');
document.body.dataset.show = 'tile';
buttons.forEach(b => b.addEventListener('click', () => {
  buttons.forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  document.body.dataset.show = b.dataset.show;
  document.querySelectorAll('.row img').forEach(img => { img.src = img.dataset[b.dataset.show]; });
}));
document.getElementById('guides').addEventListener('change', e => document.body.classList.toggle('noguides', !e.target.checked));
function reveal() {
  const side = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (side) { const d = side.closest('details'); if (d) d.open = true; side.scrollIntoView(); }
}
addEventListener('hashchange', reveal); reveal();
</script>""")
    (out / 'index.html').write_text('\n'.join(page), encoding='utf-8')


# Write -------------------------------------------------------------------------------------------------------------

def write(dataset, out=None, log=print):
    """Puts the staged sides in the data repo: images/large/map-tiles at SQUARE px per square, and images/small/map-tiles
    halved (BOX) to 64, the frame the dataset's tiles have always had. Every side must be staged, fitted at its pill's
    turn and twice the size of its small image. map-tiles.json doesn't change (its sizes are in squares). Returns the
    problems; nothing is written if there are any."""
    from PIL import Image

    out = Path(out or out_dir())
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    root = dataset.root / 'images'
    problems, staged = [], []
    for key, product, tile, side, field in sides(dataset):
        info = manifest['sides'].get(key)
        path = tile[field]
        if info is None or not (out / path).exists():
            problems.append(f'{key}: not staged')
            continue
        if info.get('scan_turn') is None or info['turn'] != info['scan_turn']:
            problems.append(f"{key}: fitted at {info['turn']}°, not at its pill's turn")
        with Image.open(out / path) as image, Image.open(root / 'small' / path) as small:
            if image.size != (small.width * SQUARE // 64, small.height * SQUARE // 64):
                problems.append(f'{key}: staged {image.size}, but its small image is {small.size}')
        staged.append(path)
    if problems:
        return problems
    for path in staged:
        with Image.open(out / path) as image:
            image = image.convert('RGBA')
            (root / 'large' / path).write_bytes((out / path).read_bytes())
            image.resize((image.width * 64 // SQUARE, image.height * 64 // SQUARE), Image.BOX).save(
                root / 'small' / path, optimize=True)
    log(f'  {len(staged)} sides at {SQUARE} px per square (large) and 64 (small)')
    return []
