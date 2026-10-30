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
is in degrees; IC2 draws a tile turned by -rotation about its pivot (TileRenderer.cs)."""
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


def load(root=None):
    return json.loads(((root or settings.STAGING) / 'ic2' / 'ic2.json').read_text(encoding='utf-8'))
