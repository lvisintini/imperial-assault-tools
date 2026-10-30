"""ia maps: the campaign maps, drawn from ImperialCommander2's layouts with the Vassal module's tiles (data 2.0.0).

IC2's mission files place each tile (ic2.parse_sections) with its texture's top-left corner at (x, y) / 10 squares,
turned clockwise by its rotation about that corner: TileRenderer.cs turns it by -rotation, and the sprites' pivot is
their top-left corner (alignment 1 in their .meta files).

A Vassal image is the side cut on its outline: on an axis with tabs it is 32 px wider than its squares, a 16 px margin
at each end (grid_rect). IC2's textures are cut to the grid, and not always turned like
the Vassal image of the same side. A side's turn k (the Vassal image turned counter-clockwise k times looks like IC2's
texture) is the one whose colours match IC2's best, compared at 32 px per square. When two turns score within MARGIN of
each other, the side gets the turn that fits its neighbours best across the maps that use it: the fewest gaps left
inside the tiles' squares (a notch whose neighbour's tab went elsewhere) and squares covered twice. Aftermath's turns
are checked against the Vassal module's Aftermath save, which places the same tiles.

The tools compare images numerically; they never look at them.

Writes staging/campaign-maps/:
- <map slug>.png for each campaign map: 64 px per square, the tiles only (no doors, crates or tokens), the sections
  drawn in order (later ones on top), transparent around the tiles and cropped to them. A map whose sections replace
  each other during the mission (more than OVERLAP of it covered twice) is drawn with the sections shown at the start;
- manifest.json: {"ic2_commit", "turns": {"<product> <number><side>": {"turn", "scores", "by"}},
  "maps": [{"name", "map_id", "ic2", "file", "size", "bytes", "sections": "all" | "start", "overlap"}]}. overlap is the
  share of the drawn tile pixels that two tiles cover (tabs' anti-aliased edges make a little)."""
import json
import re
from pathlib import Path

import numpy as np

from ia_tools import ic2, settings, tiles, vassal
from ia_tools.match import normalise
from ia_tools.staging import slugify

SQUARE = 64
MATCH_PX = 32   # per square, comparing colours
SOLVE_PX = 16   # per square, fitting tabs into notches
MARGIN = 0.03
# The fit must be this much better than the colours' turn's (and FIT_PX at least) to overrule the colours.
FIT_SHARE = 0.01
FIT_PX = 100
# A map whose sections cover more than this share of its tile pixels twice is built from sections that replace each
# other: it's drawn with its start section only.
OVERLAP = 0.01


def grid_rect(alpha, px=SQUARE):
    """(x0, y0, width, height): where an image's grid starts, in px, and its size in squares, at px per square. An
    axis with tabs has a margin of a quarter square at each end, for the tabs on either side."""
    h, w = alpha.shape
    gw, gh = w // px, h // px
    return (w - gw * px) // 2, (h - gh * px) // 2, gw, gh


def alpha_of(image):
    return image[..., 3] if image.ndim == 3 else image


def rotate_point(x, y, degrees):
    """Clockwise on a y-down page, by a multiple of 90 degrees."""
    for _ in range(round(degrees / 90) % 4):
        x, y = -y, x
    return x, y


def side_key(product, number, side):
    return f'{product} {number}{side}'


def texture_key(texture):
    expansion, number, side = ic2.TEXTURE.match(texture).groups()
    return side_key(tiles.EXPANSIONS[expansion], int(number), side)


def load_rgba(path):
    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert('RGBA'))


def ncc(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) or 1))


def shape(width, height):
    """Landscape (1), portrait (-1) or square (0): textures aren't always cut to their squares' exact ratio."""
    return 1 if width > height * 1.15 else -1 if height > width * 1.15 else 0


def turn_scores(texture, side):
    """{turn: colour match} for the turns whose shape fits the texture's."""
    from PIL import Image

    scores = {}
    for k in range(4):
        turned = np.rot90(side, k)
        x0, y0, gw, gh = grid_rect(turned[..., 3])
        if shape(texture.shape[1], texture.shape[0]) != shape(gw, gh):
            continue
        size = (gw * MATCH_PX, gh * MATCH_PX)
        grid = Image.fromarray(np.ascontiguousarray(turned[y0:y0 + gh * SQUARE, x0:x0 + gw * SQUARE]))
        ours = np.asarray(grid.resize(size, Image.BOX), dtype=float)
        theirs = np.asarray(Image.fromarray(texture).convert('RGB').resize(size, Image.BOX), dtype=float)
        mask = ours[..., 3] > 250
        scores[k] = round(ncc(ours[..., :3][mask], theirs[mask]), 3)
    return scores


def placed(side, k, x, y, rotation, px=SQUARE):
    """(image, left, top): a side (an image, or a mask at px per square) turned for its placement, and where its
    top-left pixel goes."""
    image = np.rot90(side, k - round(rotation / 90))
    _, _, tw, th = grid_rect(alpha_of(np.rot90(side, k)), px)
    corners = [rotate_point(cx, cy, rotation) for cx, cy in ((0, 0), (tw, 0), (0, th), (tw, th))]
    gx, gy = x / 10 + min(c[0] for c in corners), y / 10 + min(c[1] for c in corners)
    x0, y0, _, _ = grid_rect(alpha_of(image), px)
    return image, round(gx * px) - x0, round(gy * px) - y0


def fit(mission, sides, turns):
    """Gaps inside the tiles' squares plus pixels covered twice, at SOLVE_PX: the lower, the better the tabs fit."""
    pieces = []
    for section in mission['sections']:
        for tile in section['tiles']:
            key = texture_key(tile['texture'])
            pieces.append(placed(sides[key]['mask'], turns[key], tile['x'], tile['y'], tile['rotation'], SOLVE_PX))
    if not pieces:
        return 0
    left, top = min(p[1] for p in pieces), min(p[2] for p in pieces)
    width = max(p[1] + p[0].shape[1] for p in pieces) - left
    height = max(p[2] + p[0].shape[0] for p in pieces) - top
    count = np.zeros((height, width), dtype=np.int16)
    grid = np.zeros((height, width), dtype=bool)
    for mask, x, y in pieces:
        h, w = mask.shape
        count[y - top:y - top + h, x - left:x - left + w] += mask
        x0, y0, gw, gh = grid_rect(mask, SOLVE_PX)
        grid[y - top + y0:y - top + y0 + gh * SOLVE_PX, x - left + x0:x - left + x0 + gw * SOLVE_PX] = True
    return int(((count == 0) & grid).sum() + (count > 1).sum())


def solve(cache, module, textures, log=print):
    """{side key: {"turn", "scores", "by"}} and the sides' images and masks."""
    from PIL import Image

    pieces = vassal.tiles(Path(module) / 'buildFile')
    sides = {}
    for piece in pieces:
        image = load_rgba(Path(module) / 'images' / piece['image'])
        # A tab or notch is 32 px deep: SOLVE_PX keeps it at least 8 px.
        small = Image.fromarray(image[..., 3]).resize(
            (image.shape[1] * SOLVE_PX // SQUARE, image.shape[0] * SOLVE_PX // SQUARE), Image.BOX)
        sides[side_key(piece['product'], piece['number'], piece['side'])] = {
            'piece': piece, 'image': image, 'mask': (np.asarray(small) > 127).astype(np.int16)}
    names = {texture_key(name): name for name in textures}
    turns = {}
    for key, side in sides.items():
        scores = turn_scores(load_rgba(textures[names[key]]), side['image'])
        ranked = sorted(scores, key=scores.get, reverse=True)
        clear = len(ranked) == 1 or scores[ranked[0]] - scores[ranked[1]] >= MARGIN
        turns[key] = {'turn': ranked[0], 'scores': scores, 'by': 'colours' if clear else 'unsure'}
    current = {key: t['turn'] for key, t in turns.items()}
    uses = {}
    for mission in cache['missions']:
        for section in mission['sections']:
            for tile in section['tiles']:
                uses.setdefault(texture_key(tile['texture']), []).append(mission)
    for _ in range(3):  # until no side changes
        changed = False
        for key, turn in turns.items():
            if turn['by'] == 'colours' or key not in uses:
                continue
            missions = list({id(m): m for m in uses[key]}.values())
            fits = {}
            for k in turn['scores']:
                trial = current | {key: k}
                fits[k] = sum(fit(m, sides, trial) for m in missions)
            colours = max(turn['scores'], key=turn['scores'].get)
            best = min(fits, key=lambda k: (fits[k], -turn['scores'][k]))
            if fits[colours] - fits[best] <= max(FIT_PX, FIT_SHARE * fits[colours]):
                best = colours
            turn['fits'] = fits
            if best != current[key]:
                current[key], changed = best, True
        if not changed:
            break
    for key, turn in turns.items():
        if turn['by'] == 'unsure':
            colours = max(turn['scores'], key=turn['scores'].get)
            turn['turn'] = current[key]
            turn['by'] = 'tabs' if current[key] != colours else 'colours (close)'
    return turns, sides


def save_turns(save, pieces, mission):
    """{side key: turn} the Aftermath save shows, for the sides it places once: IC2 turns the texture clockwise by
    rotation and Vassal the image clockwise by 90 per facing, so turn = rotation / 90 - facing."""
    by_image = {p['image']: p for p in pieces}
    facings = {}
    for command in vassal.decode_save(save).split('\x1b'):
        image = re.search(r'piece;[^;]*;[^;]*;([^;]+\.png);', command)
        facing = re.search(r'Tile\\\t(\d+)\\', command)
        if image and image[1] in by_image and facing:
            p = by_image[image[1]]
            facings.setdefault(side_key(p['product'], p['number'], p['side']), []).append(int(facing[1]))
    rotations = {}
    for section in mission['sections']:
        for tile in section['tiles']:
            rotations.setdefault(texture_key(tile['texture']), []).append(tile['rotation'])
    return {key: round(rotations[key][0] / 90 - f[0]) % 4 for key, f in facings.items()
            if len(f) == 1 and len(rotations.get(key, [])) == 1}


def draw(mission, sides, turns, start_only=False):
    """(RGBA image, overlap share). start_only: only the sections shown when the mission starts (the first section if
    IC2 hides them all)."""
    from PIL import Image

    shown = [s for s in mission['sections'] if not (start_only and s['hidden'])] or mission['sections'][:1]
    pieces = []
    for section in shown:
        for tile in section['tiles']:
            key = texture_key(tile['texture'])
            pieces.append(placed(sides[key]['image'], turns[key]['turn'], tile['x'], tile['y'], tile['rotation']))
    left = min(p[1] for p in pieces)
    top = min(p[2] for p in pieces)
    width = max(p[1] + p[0].shape[1] for p in pieces) - left
    height = max(p[2] + p[0].shape[0] for p in pieces) - top
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    count = np.zeros((height, width), dtype=np.int16)
    for image, x, y in pieces:
        h, w = image.shape[:2]
        layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        layer.paste(Image.fromarray(np.ascontiguousarray(image)), (x - left, y - top))
        canvas = Image.alpha_composite(canvas, layer)
        count[y - top:y - top + h, x - left:x - left + w] += image[..., 3] > 127
    covered = (count > 0).sum()
    return canvas.crop(canvas.getbbox()), round(float((count > 1).sum() / covered), 4) if covered else 0.0


def campaign_maps(dataset):
    """{normalised name: map record} for the maps without an image (data 2.0.0's campaign maps)."""
    return {normalise(m['name']): m for m in dataset.records('maps') if m['image'] is None}


def run(module, cache, textures, dataset, sample=None, out=None, log=print):
    """(manifest, problems). sample: mission names to draw, instead of all."""
    out = Path(out or settings.STAGING / 'campaign-maps')
    turns, sides = solve(cache, module, textures, log)
    problems = []
    aftermath = next(m for m in cache['missions'] if m['name'] == 'Aftermath')
    pieces = [s['piece'] for s in sides.values()]
    for key, turn in save_turns(Path(module) / 'Aftermath.vsav', pieces, aftermath).items():
        if turns[key]['turn'] != turn:
            problems.append(f"{key}: turned {turns[key]['turn']}, but the Aftermath save shows {turn}")
    records = campaign_maps(dataset)
    wanted = {normalise(n) for n in sample} if sample else None
    missions = [m for m in cache['missions'] if wanted is None or normalise(m['name']) in wanted]
    if wanted and len(missions) != len(wanted):
        problems.append(f'IC2 has no mission named {sorted(wanted - {normalise(m["name"]) for m in missions})}')
    out.mkdir(parents=True, exist_ok=True)
    maps = []
    for mission in missions:
        record = records.get(normalise(mission['name']))
        name = record['name'] if record else mission['name']
        if record is None:
            problems.append(f"{mission['name']}: no campaign map of that name")
        image, overlap = draw(mission, sides, turns)
        sections = 'all'
        if overlap > OVERLAP:
            image, overlap = draw(mission, sides, turns, start_only=True)
            sections = 'start'
        file = f'{slugify(name)}.png'
        image.save(out / file, optimize=True)
        maps.append({'name': name, 'map_id': record and record['id'], 'ic2': f"{mission['folder']}/{mission['file']}",
                     'file': file, 'size': list(image.size), 'bytes': (out / file).stat().st_size,
                     'sections': sections, 'overlap': overlap})
        log(f"  {file}: {image.size[0]}x{image.size[1]} px, {maps[-1]['bytes'] / 1e6:.1f} MB"
            + (', start section only' if sections == 'start' else '')
            + (f', {overlap:.1%} covered twice' if overlap else ''))
    manifest = {'ic2_commit': cache['commit'],
                'turns': {k: {f: t[f] for f in ('turn', 'scores', 'by', 'fits') if f in t} for k, t in turns.items()},
                'maps': maps}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest, problems
