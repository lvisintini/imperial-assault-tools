import json
import zipfile

from PIL import Image

from ia_tools import ic2, tiles, vassal

BUILD_FILE = """<?xml version="1.0" encoding="UTF-8"?>
<VASSAL.launch.BasicModule name="test">
  <VASSAL.build.module.PieceWindow name="Tiles">
    <VASSAL.build.widget.TabWidget entryName="Map Tiles">
      <VASSAL.build.widget.ListWidget entryName="Map Tiles">
        <VASSAL.build.widget.PanelWidget entryName="Core">
          <VASSAL.build.widget.PieceSlot entryName="01A">+/null/prototype;Tile	piece;;;01A.png;01A/	null;0;0;1</VASSAL.build.widget.PieceSlot>
          <VASSAL.build.widget.PieceSlot entryName="01B">+/null/prototype;Tile	piece;;;01B.png;01B/	null;0;0;2</VASSAL.build.widget.PieceSlot>
          <VASSAL.build.widget.PieceSlot entryName="02B+19A for Loose Cannon">+/null/prototype;Tile	piece;;;02B19A.png;x/	null;0;0;3</VASSAL.build.widget.PieceSlot>
        </VASSAL.build.widget.PanelWidget>
        <VASSAL.build.widget.PanelWidget entryName="Twin Shadows">
          <VASSAL.build.widget.PieceSlot entryName="TS 1A">+/null/prototype;Tile	piece;;;TS1A.png;TS 1A/	null;0;0;4</VASSAL.build.widget.PieceSlot>
          <VASSAL.build.widget.PieceSlot entryName="TS 1B">+/null/prototype;Tile	piece;;;TS1B.png;TS 1B/	null;0;0;5</VASSAL.build.widget.PieceSlot>
        </VASSAL.build.widget.PanelWidget>
      </VASSAL.build.widget.ListWidget>
    </VASSAL.build.widget.TabWidget>
  </VASSAL.build.module.PieceWindow>
</VASSAL.launch.BasicModule>
"""


def save(path, text, key=0x5a):
    body = ''.join(f'{ord(c) ^ key:02x}' for c in text)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('savedGame', f'!VCSK{key:02x}{body}')
    return path


def module(root):
    (root / 'images').mkdir(parents=True)
    (root / 'buildFile').write_text(BUILD_FILE, encoding='utf-8')
    for name, size in {'01A': (416, 288), '01B': (384, 256), '02B19A': (10, 10), 'TS1A': (160, 128),
                       'TS1B': (128, 160)}.items():
        Image.new('RGBA', size).save(root / 'images' / f'{name}.png')
    save(root / 'Aftermath.vsav', 'begin_save\x1b+/1/Tile;piece;;;01A.png;01A/\tnull;0;0;1\x1bend')
    return root


CACHE = {'commit': 'abc', 'tiles': [{'expansion': 'Core', 'number': 1, 'width': 6, 'height': 4},
                                    {'expansion': 'Twin', 'number': 1, 'width': 2, 'height': 2}],
         'missions': [{'file': 'CORE2.json', 'folder': 'Core', 'name': 'Aftermath', 'campaign': 'Core Game',
                       'tiles': {'Core_1A': 1}}]}


class Dataset:
    def records(self, content_type):
        return []


def test_dimensions_allow_trailing_commas():
    assert ic2.parse_dimensions('[{"expansion": "Core", "id": 1, "width": 6, "height": 6, "biomeA": "x",},]') == [
        {'expansion': 'Core', 'number': 1, 'width': 6, 'height': 6}]


def test_a_mission_adds_up_its_sections():
    text = json.dumps({'missionProperties': {'missionName': 'Aftermath', 'campaignName': 'Core Game'},
                       'mapSections': [{'mapTiles': [{'textureName': 'Core_7A'}, {'textureName': 'Core_36B'}]},
                                       {'mapTiles': [{'textureName': 'Core_36B'}, {'textureName': 'Door'}]}]})
    assert ic2.parse_mission('﻿' + text) == ('Aftermath', 'Core Game', {'Core_36B': 2, 'Core_7A': 1})


def test_vassal_tiles_are_the_palettes_sides(tmp_path):
    found = vassal.tiles(module(tmp_path) / 'buildFile')
    assert [(t['product'], t['number'], t['side'], t['image']) for t in found] == [
        ('Imperial Assault', 1, 'A', '01A.png'), ('Imperial Assault', 1, 'B', '01B.png'),
        ('Twin Shadows', 1, 'A', 'TS1A.png'), ('Twin Shadows', 1, 'B', 'TS1B.png')]


def test_saves_are_decoded(tmp_path):
    assert vassal.save_tiles(module(tmp_path) / 'Aftermath.vsav', {'01A.png', '01B.png'}) == {'01A.png': 1}


def test_images_fit_their_squares():
    assert tiles.fits((416, 288), (6, 4)) and tiles.fits((384, 256), (6, 4)) and tiles.fits((288, 416), (6, 4))
    assert not tiles.fits((400, 288), (6, 4))


def test_run_stages_tiles_layouts_and_copies(tmp_path):
    manifest, problems = tiles.run(module(tmp_path / 'module'), CACHE, Dataset(), out=tmp_path / 'out')
    assert problems == []
    assert [(t['name'], t['side_a'], t['side_b']) for t in manifest['tiles']] == [
        ('Core Set 01', 'map-tiles/core-set-01-a.png', 'map-tiles/core-set-01-b.png'),
        ('Twin Shadows 01', 'map-tiles/twin-shadows-01-a.png', 'map-tiles/twin-shadows-01-b.png')]
    assert manifest['layouts'][0]['mission'] is None and manifest['checks']['aftermath save']
    assert (tmp_path / 'out' / 'images' / 'map-tiles' / 'twin-shadows-01-b.png').exists()
    assert (tmp_path / 'out' / 'copies.csv').read_text().splitlines()[1] == 'Imperial Assault,1,Core Set 01,1,1'


def test_a_wrong_size_is_a_problem(tmp_path):
    root = module(tmp_path)
    Image.new('RGBA', (100, 100)).save(root / 'images' / 'TS1B.png')
    _, problems = tiles.plan(root, CACHE, Dataset())
    assert problems == ["TS 1B: 100x100 px isn't 2x2 squares"]
