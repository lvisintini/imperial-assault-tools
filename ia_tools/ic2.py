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
# - drop: section names IC2 has but the mission doesn't, or [section name, texture] for that section's placements of it,
#   or [section name, texture, [x, y]] for the one at x, y;
# - add: {section name: [{"texture", "x", "y", "rotation"}]}, placements IC2 lacks;
# - counts: {texture: count}, the copies the mission takes where that isn't its placements' sum (sections that reuse
#   the same tiles);
# - move: {section name: [[texture, [x, y], [x, y]]]}, a placement of that texture moved from IC2's position to another
#   ([x, y, rotation] to turn it too: it turns about its x, y, so the same squares take another x, y);
# - shift: {section or hidden section name: [dx, dy]}, every placement in it moved by dx, dy (IC2's units, 10 to a
#   square), to close up the gaps IC2 leaves between a map's sections;
# - main: the sections the map's image shows. Without main, the image shows every section;
# - hidden: [[name, [section names]]], with main: the map's hidden sections, revealed during the mission, each an image
#   of those IC2 sections. Without it, each other section with tiles is one, named after it ("Section 2 - Cave" is
#   "Cave").
CORRECTIONS = {
    'CORE4.json': {'sides': {'Core_24A': 'Core_24B', 'Core_32A': 'Core_32B'}},  # Desperate Hour
    'CORE6.json': {  # Fly Solo: the second 18B, right of 6B and under 16B
        'add': {'Start Section': [{'texture': 'Core_18B', 'x': 1030.0, 'y': 970.0, 'rotation': 270.0}]}},
    'CORE9.json': {'sides': {'Core_24A': 'Core_24B', 'Core_32A': 'Core_32B'}},  # Last Stand, on Desperate Hour's map
    'CORE17.json': {  # High Moon: the 18B above 5B a square to the left, so their tabs meet
        'move': {'Start Section': [['Core_18B', [970.0, 920.0], [960.0, 920.0]]]}},
    'CORE26.json': {'drop': ['Section 3 - Control']},  # The Spice Job
    'CORE29.json': {'sides': {'Core_19A': 'Core_19B'}},  # Captured: the Trash Compactor is 19B
    'CORE31.json': {'drop': ['Section 3 - Control Room']},  # Means of Production
    'EMPIRE1.json': {  # Capital Escape: the 18B under 2B a square to the right; the Command Center a square from the map
        'move': {'Start Section': [['Empire_18B', [1020.0, 1050.0], [1030.0, 1050.0]]]},
        'shift': {'Command Center': [-90.0, 0.0]},
        'main': ['Start Section'],
        'hidden': [['Command Center', ['Section 2 - Crash', 'Section 3 - Facility']]]},
    'EMPIRE2.json': {'section sides': {'Start Section': {'Empire_17A': 'Empire_17B'}}},  # Dark Recon
    'EMPIRE3.json': {  # Disruption: the 17B in R3 (below 10B, above 28B) is a 16B, so 16B x3 and 17B x3; the hidden
        # sections a square right of the map
        'section sides': {'R3': {'Empire_17B': 'Empire_16B'}},
        'shift': {name: [-140.0, 0.0] for name in ('Underworld (Visible area)', 'Underworld (Obscured area)',
                                                   'Landing Platform', 'Hideaway')},
        'main': ['Start Section'],
        'hidden': [['Underworld (Visible area)', ['Section 2 - Underworld']],
                   ['Underworld (Obscured area)', ['R1', 'R2', 'R3', 'R4', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6',
                                                   'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7']],
                   ['Landing Platform', ['Section 3 - Landing Platform']],
                   ['Hideaway', ['Section 4 - Hideaway']]]},
    'EMPIRE6.json': {  # From Dark Clutches
        'main': ['Start Section'],
        'hidden': [['Hidden area', ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'M1-Corridor', 'M2', 'M3', 'M4', 'M5',
                                    'M6-Hall', 'M7-Cell', 'L1', 'L2-Interrogation Chamber', 'L3', 'L4', 'L5', 'L6']]]},
    'EMPIRE9.json': {  # Into a Corner
        'sides': {'Empire_13B': 'Empire_13A'},
        # City Square without 18Bs, Main Street's two on 3B's long sides, Landing's three on 1B (17B on the fourth)
        'drop': [['Start Section', 'Empire_18B'], ['Section 2 - City Square N', 'Empire_18B'],
                 ['Section 3 - Main Street NW', 'Empire_18B', [880.0, 940.0]],
                 ['Section 3 - Main Street NW', 'Empire_18B', [900.0, 900.0]]],
        'add': {'Section 4 - Landing NWN': [{'texture': 'Empire_18B', 'x': 850.0, 'y': 870.0, 'rotation': 90.0},
                                            {'texture': 'Empire_18B', 'x': 930.0, 'y': 890.0, 'rotation': 270.0}]},
        'counts': {'Empire_1B': 1, 'Empire_2B': 1, 'Empire_3B': 1, 'Empire_7B': 1, 'Empire_17B': 1, 'Empire_18B': 5},
        'main': ['Start Section'],
        # IC2 places each copy of a section on every side of the map; the mission's book shows one of each
        'hidden': [['Main Street', ['Section 3 - Main Street NW']], ['City Square', ['Section 2 - City Square N']],
                   ['Landing', ['Section 4 - Landing NWN']]]},
    'EMPIRE10.json': {  # On the Run: 7A turned round, on the same squares, so its tabs meet 5A's and 14A's
        'move': {'Section 3 - Forest': [['Core_7A', [1050.0, 910.0], [1010.0, 950.0, 270.0]]]}},
    'EMPIRE12.json': {  # The Realm of the Dark Side: the 18B left of 4B a square higher
        'sides': {'Empire_4A': 'Empire_4B'},
        'move': {'Section 3 - Temple': [['Empire_18B', [980.0, 940.0], [980.0, 930.0]]]}},
    'EMPIRE14.json': {  # Extraction: one elevator, on 15B; the roof a square from the building, tops level
        'drop': ['Section 3 - Penthouse Elevator'],
        'shift': {name: [-10.0, 20.0] for name in ('Section 2 - Roof', 'Section 4 - Roof Elevator')}},
    'HOTH1.json': {'sides': {'Hoth_9A': 'Hoth_9B'}},  # Disaster
    'HOTH2.json': {'sides': {'Core_36B': 'Core_36A'}},  # Home Front
    'HOTH3.json': {'sides': {'Core_24A': 'Core_24B'}},  # One Step Behind
    'HOTH4.json': {  # Our Last Hope
        'section sides': {'Section 2 - Rebel Base': {'Hoth_6A': 'Hoth_6B'}},
        'main': ['Start Section']},
    'HOTH12.json': {'sides': {'Hoth_7A': 'Hoth_7B'}},  # Preventative Measures
    'HOTH13.json': {'sides': {'Core_24B': 'Core_24A'}},  # Escape from Cloud City
    'HOTH15.json': {  # Survival of the Fittest
        'main': ['Start Section'],
        'hidden': [['Hidden area', ['Section 2 - Cave', 'Section 3 - NW', 'Section 4 - Pass', 'Section 5 - SW',
                                    'Section 6 - S', 'Section 7 - Cavern']]]},
    'JABBA2.json': {  # Dangerous Allies: one Khetanna; the Canyon's 39B (IC2's 2nd Khetanna's) in place of its left 18B,
        # and the Canyon 16 squares up, its 39B on the Khetanna's right 36B
        'drop': ['Section 3 - 2nd Khetanna', ['Section 5 - Canyon', 'Core_18B', [1000.0, 1140.0]]],
        'add': {'Section 5 - Canyon': [{'texture': 'Core_39B', 'x': 1000.0, 'y': 1160.0, 'rotation': 180.0}]},
        'shift': {'Canyon': [0.0, -160.0]},
        'main': ['Start Section - First Khetanna'],
        'hidden': [['Skiff', ['Section 2 - Skiff']], ['Canyon', ['Section 4 - Spaceport', 'Section 5 - Canyon']]]},
    'JABBA5.json': {'sides': {'Jabba_9A': 'Jabba_9B'}},  # Hostile Negotiations
    'JABBA7.json': {  # Mutiny: the Khetanna a square from the map
        'shift': {'Khetanna': [-10.0, 0.0]},
        'main': ['Start Section', 'Skiff'],
        'hidden': [['Second Skiff', ['Red Skiff']], ['Khetanna', ['Khetanna']]]},
    'JABBA9.json': {'main': ['Start Section', 'Section 2 - Throne Room', 'Section 4 - Back Room']},  # Storming the Palace
    'JABBA10.json': {'main': ['Start Section', 'Section 2 - Command Post']},  # Trespass
    'LOTHAL1.json': {'main': ['Start Section']},  # Call to Action
    'LOTHAL3.json': {  # Race on Ryloth
        'counts': {'Core_18B': 4, 'Lothal_12B': 3},
        'main': ['Start Section', 'Section 2']},
    'LOTHAL4.json': {  # Sands of Seelos: the AT-AT a square from the battleground
        'shift': {name: [-50.0, 0.0] for name in ('Section 2 - AT-AT Aft', 'Section 3 - AT-AT Mid',
                                                  'Section 4 - AT-AT Cockpit')}},
    'LOTHAL6.json': {  # The Final Order
        'sides': {'Lothal_2A': 'Lothal_2B', 'Lothal_5A': 'Lothal_5B', 'Lothal_6A': 'Lothal_6B', 'Lothal_7A': 'Lothal_7B'}},
    'TWIN5.json': {  # Fire in the Sky: 34A a quarter turn back, on the same squares, to match its art
        'move': {'Section 2 - Inner Ship': [['Core_34A', [1030.0, 1020.0], [1010.0, 1020.0, 0.0]]]}},
    'TWIN6.json': {  # Infiltrated, on Fire in the Sky's map
        'move': {'Start Section': [['Core_34A', [1030.0, 1020.0], [1010.0, 1020.0, 0.0]]]}},
    'OTHER2.json': {  # A Light in the Darkness: 1B and the tiles on its side of the map (16B, the 18B above 1B) a square
        # lower, so 1B's tabs meet Jabba's Realm 8B's
        'move': {'Start Section': [['Core_1B', [970.0, 1050.0], [970.0, 1060.0]],
                                   ['Core_16B', [910.0, 1010.0], [910.0, 1020.0]],
                                   ['Core_18B', [950.0, 990.0], [950.0, 1000.0]]]}},
    'OTHER23.json': {  # Intimidation Factor: 24B turned round, on the same squares, so its tabs meet 9A's, 32B's, 33B's
        'move': {'Start Section': [['Core_24B', [970.0, 990.0], [1010.0, 1030.0, 180.0]]]}},
    'OTHER10.json': {  # Communication Breakdown: 21B turned round, on the same squares, to match its art
        'move': {'Start Section': [['Hoth_21B', [930.0, 960.0], [910.0, 980.0, 270.0]]]}},
    'OTHER24.json': {  # Into the Unknown
        'main': ['Start Section'],
        'hidden': [['Hidden area', ['Up 1', 'Up 2', 'Up 3', 'Up 4', 'Up 5', 'Middle 1', 'Middle 2 - Hall',
                                    'Middle 3 - Cross', 'Down 1', 'Down 2', 'Down 3', 'Down 4', 'Down 5', 'Down 6']]]},
    'OTHER32.json': {  # Salvage Operatives: one Sand Crawler, IC2's left one, its 39B turned round to match its art
        'drop': ['Sand Crawler Middle', 'Sand Crawler Right'],
        'move': {'Sand Crawler Left': [['Core_39B', [960.0, 950.0], [940.0, 960.0, 270.0]]]},
        'main': ['Start Section'],
        'hidden': [['Sand Crawler', ['Sand Crawler Left']]]},
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

    unknown = set(fix) - {'sides', 'section sides', 'drop', 'add', 'move', 'shift', 'counts', 'main',
                       'hidden'}
    if unknown:
        fail(f'unknown corrections {sorted(unknown)}')
    for drop in fix.get('drop', []):
        if isinstance(drop, str):
            mission['sections'].remove(section(drop))
            del sections[drop]
        else:
            name, texture, *at = drop
            tiles = section(name)['tiles']
            dropped = [t for t in tiles if t['texture'] == texture and (not at or [t['x'], t['y']] == at[0])]
            if not dropped:
                fail(f"no {texture}{f' at {at[0]}' if at else ''} in {name!r}")
            tiles[:] = [t for t in tiles if t not in dropped]
    swap([t for s in mission['sections'] for t in s['tiles']], fix.get('sides', {}), 'the mission')
    for name, swaps in fix.get('section sides', {}).items():
        swap(section(name)['tiles'], swaps, repr(name))
    for name, tiles in fix.get('add', {}).items():
        section(name)['tiles'].extend(dict(t) for t in tiles)
    for name, moves in fix.get('move', {}).items():
        tiles = section(name)['tiles']
        for texture, (x, y), (to_x, to_y, *turned) in moves:
            tile = next((t for t in tiles if (t['texture'], t['x'], t['y']) == (texture, x, y)), None)
            if tile is None:
                fail(f'no {texture} at {x}, {y} in {name!r}')
            tile['x'], tile['y'] = to_x, to_y
            if turned:
                tile['rotation'] = turned[0]
    hidden_names = dict(fix.get('hidden', []))
    for name, (dx, dy) in fix.get('shift', {}).items():
        for tile in (t for n in hidden_names.get(name, [name]) for t in section(n)['tiles']):
            tile['x'], tile['y'] = tile['x'] + dx, tile['y'] + dy
    for tile in (t for s in mission['sections'] for t in s['tiles']):
        if not TEXTURE.match(tile['texture']):
            fail(f"{tile['texture']!r} isn't a tile texture")
    tiles = Counter(t['texture'] for s in mission['sections'] for t in s['tiles'])
    for texture, count in fix.get('counts', {}).items():
        if texture not in tiles:
            fail(f'no {texture} to count')
        tiles[texture] = count
    mission['tiles'] = dict(sorted(tiles.items()))
    if 'hidden' in fix and 'main' not in fix:
        fail('hidden sections without main ones')
    if 'main' in fix:
        for name in fix['main']:
            section(name)
        mission['main'] = list(fix['main'])
        if 'hidden' in fix:
            hidden = [{'name': name, 'sections': list(names)} for name, names in fix['hidden']]
        else:
            hidden = [{'name': re.sub(r'^Section \d+ - ', '', s['name']), 'sections': [s['name']]}
                      for s in mission['sections'] if s['name'] not in mission['main'] and s['tiles']]
        for name in (n for h in hidden for n in h['sections']):
            if name in mission['main']:
                fail(f'{name!r} is a main section')
            section(name)
        mission['hidden'] = hidden


def load(root=None):
    return correct(json.loads(((root or settings.STAGING) / 'ic2' / 'ic2.json').read_text(encoding='utf-8')))
