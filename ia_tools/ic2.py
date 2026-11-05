"""ia ic2: ImperialCommander2's map tile sizes and campaign mission layouts, cached in staging/ic2/.

ImperialCommander2 (github.com/GlowPuff/ImperialCommander2, MIT) is a companion app that plays the Imperial side of
campaign missions. Two of its files are what the dataset uses:
- Assets/Resources/dimensions.json: every map tile, {expansion, id, width, height, biomeA, biomeB}, with width and
  height in squares (the file has trailing commas, which json rejects);
- Assets/Resources/SagaMissions/<folder>/<FILE>.json: a mission each, with its name (missionProperties.missionName)
  and the tiles of each map section (mapSections[].mapTiles[].textureName, "Core_1A" = Core Set tile 1, side A).

ia ic2 fetches them at COMMIT and writes staging/ic2/ic2.json:
    {"commit", "tiles": [{"expansion", "number", "width", "height"}],
     "missions": [{"file", "folder", "name", "campaign", "tiles": {"Core_1A": count},
                   "sections": [{"name", "hidden", "tiles": [{"texture", "x", "y", "rotation"}]}]}]}
Tiles placed in several map sections, or several times in one, add up. A section is hidden until the mission reveals
it (invisibleUntilActivated). A tile's x and y are IC2's editor coordinates (10 per square, y down) and its rotation
is in degrees; IC2 draws a tile turned by -rotation about its pivot (TileRenderer.cs).

load() applies CORRECTIONS, the maintainer's checks of IC2's layouts against the Campaign Guide and the rulebooks (with
Zack Gomez's campaign tile guide as a checklist). A corrected side keeps IC2's position and rotation: the right side's
tabs then fit, which ia maps measures."""
import json
import re
from collections import Counter

from ia_tools import settings

REPO = 'GlowPuff/ImperialCommander2'
COMMIT = 'a7bb92102f70e2f306bce48c661143c1a7da4735'
RAW = f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/'
TREE = f'https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1'
DIMENSIONS = 'ImperialCommander2/Assets/Resources/dimensions.json'
MISSIONS = re.compile(r'^ImperialCommander2/Assets/Resources/SagaMissions/([^/]+)/([^/]+\.json)$')
TEXTURE = re.compile(r'^([A-Za-z]+)_(\d+)([AB])$')
# The tiles' own images, cut to the grid: only used to tell how each Vassal image is turned (ia maps).
TEXTURES = re.compile(r'^ImperialCommander2/Assets/SagaTiles/[^/]+/([A-Za-z]+_\d+[AB])\.png$')
# {mission file: correction}. A correction has any of:
# - sides: {IC2's texture: the right one}, for each of the mission's placements of it;
# - section sides: {section name: {IC2's texture: the right one}}, for one section's placements only;
# - drop: section names IC2 has but the mission doesn't, or [section name, texture] for that section's placements of it;
# - add: {section name: [{"texture", "x", "y", "rotation"}]}, placements IC2 lacks;
# - counts: {texture: count}, the copies the mission takes where that isn't its placements' sum (sections that reuse
#   the same tiles);
# - main: the sections the map's image shows. Each other section is a hidden image of its own, revealed during the
#   mission. Without main, the image shows every section.
CORRECTIONS = {
    'CORE4.json': {'sides': {'Core_24A': 'Core_24B', 'Core_32A': 'Core_32B'}},  # Desperate Hour
    'CORE6.json': {  # Fly Solo: the second 18B, right of 6B and under 16B
        'add': {'Start Section': [{'texture': 'Core_18B', 'x': 1030.0, 'y': 970.0, 'rotation': 270.0}]}},
    'CORE9.json': {'sides': {'Core_24A': 'Core_24B', 'Core_32A': 'Core_32B'}},  # Last Stand
    'CORE26.json': {'drop': ['Section 3 - Control']},  # The Spice Job
    'CORE31.json': {'drop': ['Section 3 - Control Room']},  # Means of Production
    'EMPIRE2.json': {'section sides': {'Start Section': {'Empire_17A': 'Empire_17B'}}},  # Dark Recon
    'EMPIRE3.json': {  # Disruption
        'counts': {'Empire_16B': 3, 'Empire_17B': 3},
        'main': ['Start Section']},
    'EMPIRE9.json': {  # Into a Corner
        'sides': {'Empire_13B': 'Empire_13A'},
        'drop': [['Start Section', 'Empire_18B']],
        'counts': {'Empire_1B': 1, 'Empire_2B': 1, 'Empire_3B': 1, 'Empire_7B': 1, 'Empire_17B': 1, 'Empire_18B': 5},
        'main': ['Start Section']},
    'EMPIRE12.json': {'sides': {'Empire_4A': 'Empire_4B'}},  # The Realm of the Dark Side
    'EMPIRE14.json': {'drop': ['Section 3 - Penthouse Elevator']},  # Extraction: one elevator, on 15B
    'HOTH1.json': {'sides': {'Hoth_9A': 'Hoth_9B'}},  # Disaster
    'HOTH2.json': {'sides': {'Core_36B': 'Core_36A'}},  # Home Front
    'HOTH3.json': {'sides': {'Core_24A': 'Core_24B'}},  # One Step Behind
    'HOTH4.json': {'main': ['Start Section']},  # Our Last Hope
    'HOTH12.json': {'sides': {'Hoth_7A': 'Hoth_7B'}},  # Preventative Measures
    'HOTH13.json': {'sides': {'Core_24B': 'Core_24A'}},  # Escape from Cloud City
    'HOTH15.json': {'main': ['Start Section']},  # Survival of the Fittest
    'JABBA5.json': {'sides': {'Jabba_9A': 'Jabba_9B'}},  # Hostile Negotiations
    'LOTHAL3.json': {  # Race on Ryloth
        'counts': {'Core_18B': 4, 'Lothal_12B': 3},
        'main': ['Start Section', 'Section 2']},
    'LOTHAL6.json': {  # The Final Order
        'sides': {'Lothal_2A': 'Lothal_2B', 'Lothal_5A': 'Lothal_5B', 'Lothal_6A': 'Lothal_6B', 'Lothal_7A': 'Lothal_7B'}},
    'OTHER24.json': {'main': ['Start Section']},  # Into the Unknown
}


def lenient_json(text):
    """JSON with trailing commas before a closing bracket or brace."""
    return json.loads(re.sub(r',\s*([\]}])', r'\1', text))


def parse_dimensions(text):
    return [{'expansion': d['expansion'], 'number': d['id'], 'width': d['width'], 'height': d['height']}
            for d in lenient_json(text)]


def parse_mission(text):
    """(name, campaign, {texture: count}) from a mission file."""
    mission = lenient_json(text.lstrip('﻿'))
    properties = mission.get('missionProperties', {})
    tiles = Counter(tile['textureName'] for section in mission.get('mapSections', [])
                    for tile in section.get('mapTiles', []) if TEXTURE.match(tile.get('textureName', '')))
    return properties.get('missionName'), properties.get('campaignName'), dict(sorted(tiles.items()))


def parse_sections(text):
    """A mission file's map sections, with each tile's placement."""
    mission = lenient_json(text.lstrip('﻿'))
    sections = []
    for section in mission.get('mapSections', []):
        placed = []
        for tile in section.get('mapTiles', []):
            if TEXTURE.match(tile.get('textureName', '')):
                x, y = (float(v) for v in tile['entityPosition'].split(','))
                placed.append({'texture': tile['textureName'], 'x': x, 'y': y,
                               'rotation': float(tile.get('entityRotation') or 0)})
        sections.append({'name': section.get('name'), 'hidden': bool(section.get('invisibleUntilActivated')),
                         'tiles': placed})
    return sections


def run(session, root=None, log=print):
    out = (root or settings.STAGING) / 'ic2'
    out.mkdir(parents=True, exist_ok=True)

    def get(url):
        response = session.get(url, timeout=60)
        response.raise_for_status()
        return response

    paths = [entry['path'] for entry in get(TREE).json()['tree'] if entry['type'] == 'blob']
    tiles = parse_dimensions(get(RAW + DIMENSIONS).text)
    missions = []
    for path in sorted(p for p in paths if MISSIONS.match(p)):
        folder, file = MISSIONS.match(path).groups()
        text = get(RAW + path).content.decode('utf-8-sig')
        name, campaign, used = parse_mission(text)
        missions.append({'file': file, 'folder': folder, 'name': name, 'campaign': campaign, 'tiles': used,
                         'sections': parse_sections(text)})
        log(f'  {folder}/{file}: {name} ({sum(used.values())} tiles)')
    cache = {'commit': COMMIT, 'tiles': tiles, 'missions': missions}
    (out / 'ic2.json').write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding='utf-8')
    return cache


def fetch_textures(session, root=None, log=print):
    """{texture name: path} of IC2's tile images, downloaded once into staging/ic2/textures/."""
    out = (root or settings.STAGING) / 'ic2' / 'textures'
    out.mkdir(parents=True, exist_ok=True)
    response = session.get(TREE, timeout=60)
    response.raise_for_status()
    found = {}
    for entry in response.json()['tree']:
        match = TEXTURES.match(entry['path'])
        if match:
            path = out / f'{match[1]}.png'
            if not path.exists():
                image = session.get(RAW + entry['path'], timeout=60)
                image.raise_for_status()
                path.write_bytes(image.content)
                log(f'  {path.name}')
            found[match[1]] = path
    return found


def correct(cache, corrections=None):
    """The cache with CORRECTIONS applied. A correction naming a section, or a texture, the mission hasn't is an
    error, so a typo can't go unnoticed."""
    corrections = CORRECTIONS if corrections is None else corrections
    for mission in cache['missions']:
        fix = corrections.get(mission['file'])
        if fix:
            apply(mission, fix)
    return cache


def apply(mission, fix):
    def fail(message):
        raise ValueError(f"{mission['file']} ({mission['name']}): {message}")

    sections = {s['name']: s for s in mission['sections']}

    def section(name):
        if name not in sections:
            fail(f'no section {name!r}')
        return sections[name]

    def swap(tiles, swaps, where):
        missing = set(swaps) - {t['texture'] for t in tiles}
        if missing:
            fail(f'no {sorted(missing)} in {where}')
        for tile in tiles:
            tile['texture'] = swaps.get(tile['texture'], tile['texture'])

    unknown = set(fix) - {'sides', 'section sides', 'drop', 'add', 'counts', 'main'}
    if unknown:
        fail(f'unknown corrections {sorted(unknown)}')
    for drop in fix.get('drop', []):
        if isinstance(drop, str):
            mission['sections'].remove(section(drop))
            del sections[drop]
        else:
            name, texture = drop
            tiles = section(name)['tiles']
            if texture not in {t['texture'] for t in tiles}:
                fail(f'no {texture} in {name!r}')
            tiles[:] = [t for t in tiles if t['texture'] != texture]
    swap([t for s in mission['sections'] for t in s['tiles']], fix.get('sides', {}), 'the mission')
    for name, swaps in fix.get('section sides', {}).items():
        swap(section(name)['tiles'], swaps, repr(name))
    for name, tiles in fix.get('add', {}).items():
        section(name)['tiles'].extend(dict(t) for t in tiles)
    for tile in (t for s in mission['sections'] for t in s['tiles']):
        if not TEXTURE.match(tile['texture']):
            fail(f"{tile['texture']!r} isn't a tile texture")
    tiles = Counter(t['texture'] for s in mission['sections'] for t in s['tiles'])
    for texture, count in fix.get('counts', {}).items():
        if texture not in tiles:
            fail(f'no {texture} to count')
        tiles[texture] = count
    mission['tiles'] = dict(sorted(tiles.items()))
    if 'main' in fix:
        for name in fix['main']:
            section(name)
        mission['main'] = list(fix['main'])


def load(root=None):
    return correct(json.loads(((root or settings.STAGING) / 'ic2' / 'ic2.json').read_text(encoding='utf-8')))
