"""Read a Vassal module's map tiles, and the pieces in its saved games.

The Imperial Assault campaign module (vassal/ in this repo: buildFile and images/) has a "Map Tiles" palette with a
panel per product, and a piece per tile side: "01A" (Core Set), "TS 1A", "H01A", "BG01A", "JR01A", "HotE01A",
"ToL01A". Each piece's image is the side cut on its real outline (tabs kept, notches transparent), 64 px per square
plus 32 px on each axis that has tabs. Pieces that combine tiles for one mission ("02B+19A for Loose Cannon",
"SWI25_Gunrunner") aren't tiles.

A saved game (.vsav) is a zip whose savedGame entry is obfuscated: "!VCSK", a hex key, then hex pairs XOR'd with it.
"""
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

PALETTE = 'Map Tiles'
# The palette's panels, as the dataset's products.
PRODUCTS = {
    'Core': 'Imperial Assault', 'Twin Shadows': 'Twin Shadows', 'Return to Hoth': 'Return to Hoth',
    'Besbin Gambit': 'The Bespin Gambit', "Jabba's Realm": "Jabba's Realm", 'Heart of the Empire': 'Heart of the Empire',
    'Tyrants of Lothal': 'Tyrants of Lothal',
}
PIECE = re.compile(r'^(?:TS |H|BG|JR|HotE|ToL)?(\d+)([AB])$')
IMAGE = re.compile(r'piece;[^;]*;[^;]*;([^;]+\.png);')


def tiles(build_file):
    """[{"product", "number", "side", "piece", "image"}] in the palette's order."""
    root = ET.parse(build_file).getroot()
    parent = {child: node for node in root.iter() for child in node}
    found = []
    for slot in root.iter('VASSAL.build.widget.PieceSlot'):
        panel, names = parent.get(slot), []
        node = panel
        while node is not None:
            names.append(node.get('entryName') or node.get('name'))
            node = parent.get(node)
        piece, image = slot.get('entryName') or '', IMAGE.search(slot.text or '')
        if PALETTE not in names or panel.get('entryName') not in PRODUCTS or not PIECE.match(piece) or not image:
            continue
        number, side = PIECE.match(piece).groups()
        found.append({'product': PRODUCTS[panel.get('entryName')], 'number': int(number), 'side': side,
                      'piece': piece, 'image': image[1]})
    return found


def decode_save(path):
    """A saved game's text."""
    data = zipfile.ZipFile(path).read('savedGame')
    if not data.startswith(b'!VCSK'):
        return data.decode('latin-1')
    key, body = int(data[5:7], 16), data[7:]
    return bytes(int(body[i:i + 2], 16) ^ key for i in range(0, len(body) - 1, 2)).decode('latin-1')


def save_tiles(path, known):
    """Counter of the tile images a saved game places, among known (image file names)."""
    return Counter(image for image in IMAGE.findall(decode_save(path)) if image in known)
