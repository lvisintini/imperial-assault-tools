import json

import numpy as np
import pytest

from ia_tools import campaign_maps, ic2
from ia_tools.layouts import sort_rows


def side(width, height, seed=0, tabs=(False, False)):
    """A generated opaque tile side (never a dataset image): width x height squares, with the 16 px margins of an axis
    with tabs left transparent."""
    w, h = width * 64 + 32 * tabs[0], height * 64 + 32 * tabs[1]
    image = np.random.default_rng(seed).integers(0, 255, (h, w, 4), dtype=np.uint8)
    image[..., 3] = 0
    image[16 * tabs[1]:h - 16 * tabs[1], 16 * tabs[0]:w - 16 * tabs[0], 3] = 255
    return image


def test_the_grid_is_centred_between_the_tab_margins():
    assert campaign_maps.grid_rect(side(3, 2, tabs=(True, True))[..., 3]) == (16, 16, 3, 2)
    assert campaign_maps.grid_rect(side(3, 2)[..., 3]) == (0, 0, 3, 2)
    assert campaign_maps.grid_rect(np.zeros((40, 56)), px=16) == (4, 4, 3, 2)


def test_tiles_turn_clockwise_about_their_top_left_corner():
    tile = side(2, 1, tabs=(True, False))  # 160 x 64
    image, left, top = campaign_maps.placed(tile, 0, 100, 200, 0)
    assert image.shape[:2] == (64, 160) and (left, top) == (10 * 64 - 16, 20 * 64)
    # Turned 90 degrees clockwise about (10, 20), the 2 x 1 grid covers x 9-10 and y 20-22.
    image, left, top = campaign_maps.placed(tile, 0, 100, 200, 90)
    assert image.shape[:2] == (160, 64) and (left, top) == (9 * 64, 20 * 64 - 16)
    assert campaign_maps.rotate_point(1, 0, 90) == (0, 1) and campaign_maps.rotate_point(1, 0, 270) == (0, -1)


@pytest.mark.parametrize('k', range(4))
@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_a_placement_is_its_grid_corner_and_the_stored_image_turned_clockwise(k, rotation):
    tile = side(3, 1, seed=k, tabs=(True, False))
    image, left, top = campaign_maps.placed(tile, k, 100, 200, rotation)
    gx, gy = campaign_maps.grid_corner(tile[..., 3], k, 100, 200, rotation)
    x0, y0, _, _ = campaign_maps.grid_rect(image[..., 3])
    assert (gx, gy) == ((left + x0) / 64, (top + y0) / 64) and gx.is_integer() and gy.is_integer()
    assert np.array_equal(np.rot90(tile, -campaign_maps.rotation_of(k, rotation) // 90), image)


def test_the_whole_map_draws_sections_in_the_order_given():
    sides = {'Imperial Assault 1A': {'image': side(1, 1, seed=1)}, 'Imperial Assault 2A': {'image': side(1, 1, seed=2)}}
    turns = {key: {'turn': 0} for key in sides}
    two = mission((False, [{'texture': 'Core_1A', 'x': 0, 'y': 0, 'rotation': 0}]),
                  (True, [{'texture': 'Core_2A', 'x': 0, 'y': 0, 'rotation': 0}]))
    top = lambda order: campaign_maps.draw(two, sides, turns, sections=order, ordered=True)[0].getpixel((32, 32))
    assert top(['S0', 'S1']) == tuple(sides['Imperial Assault 2A']['image'][32, 32])  # the later section on top
    assert top(['S1', 'S0']) == tuple(sides['Imperial Assault 1A']['image'][32, 32])


def test_placements_follow_the_sections_draw_shows():
    sides = {'Imperial Assault 1A': {'image': side(2, 1, seed=1)}}
    turns = {'Imperial Assault 1A': {'turn': 1}}
    tile = {'texture': 'Core_1A', 'x': 30, 'y': 40, 'rotation': 90}
    two = mission((False, [tile]), (True, [tile | {'x': 0}]))
    assert campaign_maps.placements(two, sides, turns, start_only=True) == [
        {'texture': 'Core_1A', 'x': 1, 'y': 4, 'rotation': 0}]  # turned 90 about (3, 4), its 1 x 2 grid starts at x 1
    assert [p['x'] for p in campaign_maps.placements(two, sides, turns)] == [1, -2]
    assert [p['x'] for p in campaign_maps.placements(two, sides, turns, sections=['S1'])] == [-2]


def test_a_sides_turn_is_the_one_whose_colours_match():
    tile = side(2, 1, seed=3)
    texture = np.rot90(tile, 3)[..., :3].repeat(4, axis=0).repeat(4, axis=1)  # IC2's, larger and turned
    scores = campaign_maps.turn_scores(np.ascontiguousarray(texture), tile)
    assert set(scores) == {1, 3} and max(scores, key=scores.get) == 3


def mission(*sections):
    return {'name': 'Test', 'sections': [{'name': f'S{i}', 'hidden': hidden, 'tiles': tiles}
                                         for i, (hidden, tiles) in enumerate(sections)]}


def test_draw_places_tiles_side_by_side_on_a_transparent_page():
    sides = {'Imperial Assault 1A': {'image': side(2, 1, seed=1)}, 'Imperial Assault 2A': {'image': side(1, 1, seed=2)}}
    turns = {key: {'turn': 0} for key in sides}
    image, overlap = campaign_maps.draw(mission((False, [
        {'texture': 'Core_1A', 'x': 0, 'y': 0, 'rotation': 0},
        {'texture': 'Core_2A', 'x': 20, 'y': 10, 'rotation': 0},  # right of tile 1, a square lower
    ])), sides, turns)
    assert image.size == (3 * 64, 2 * 64) and overlap == 0
    assert image.getpixel((0, 127))[3] == 0 and image.getpixel((0, 0))[3] == 255


def test_draw_can_keep_to_the_start_section():
    sides = {'Imperial Assault 1A': {'image': side(1, 1)}}
    turns = {'Imperial Assault 1A': {'turn': 0}}
    tile = {'texture': 'Core_1A', 'x': 0, 'y': 0, 'rotation': 0}
    replaced = mission((False, [tile]), (True, [tile]))
    assert campaign_maps.draw(replaced, sides, turns)[1] == 1.0  # both sections cover the square
    assert campaign_maps.draw(replaced, sides, turns, start_only=True)[1] == 0
    only_hidden = mission((True, [tile]))
    assert campaign_maps.draw(only_hidden, sides, turns, start_only=True)[0].size == (64, 64)


def test_sections_keep_each_tiles_placement():
    text = json.dumps({'mapSections': [
        {'name': 'Start Section', 'invisibleUntilActivated': False, 'mapTiles': [
            {'textureName': 'Core_7A', 'entityPosition': '980,1000', 'entityRotation': 90.0}]},
        {'name': 'Section 2', 'invisibleUntilActivated': True, 'mapTiles': [
            {'textureName': 'Door', 'entityPosition': '0,0'}]}]})
    assert ic2.parse_sections('﻿' + text) == [
        {'name': 'Start Section', 'hidden': False, 'tiles': [{'texture': 'Core_7A', 'x': 980, 'y': 1000, 'rotation': 90}]},
        {'name': 'Section 2', 'hidden': True, 'tiles': []}]


def ic2_mission():
    at = {'x': 1000.0, 'y': 980.0, 'rotation': 270.0}
    return {'file': 'CORE4.json', 'name': 'Test', 'tiles': {}, 'sections': [
        {'name': 'Start', 'hidden': False, 'tiles': [{'texture': 'Core_32A', **at}, {'texture': 'Core_18B', **at}]},
        {'name': 'Two', 'hidden': True, 'tiles': [{'texture': 'Core_24A', **at}, {'texture': 'Core_32A', **at},
                                                  {'texture': 'Core_18B', **at}]},
        {'name': 'Three', 'hidden': True, 'tiles': [{'texture': 'Core_36B', **at}]}]}


def textures(mission):
    return {s['name']: [t['texture'] for t in s['tiles']] for s in mission['sections']}


def test_corrections_swap_sides_and_keep_placements():
    cache = {'missions': [ic2_mission(), {**ic2_mission(), 'file': 'CORE5.json'}]}
    fixed, other = ic2.correct(cache, {'CORE4.json': {'sides': {'Core_24A': 'Core_24B', 'Core_32A': 'Core_32B'}},
                                       'CORE5.json': {'section sides': {'Two': {'Core_32A': 'Core_32B'}}}})['missions']
    assert textures(fixed) == {'Start': ['Core_32B', 'Core_18B'], 'Two': ['Core_24B', 'Core_32B', 'Core_18B'],
                               'Three': ['Core_36B']}
    assert fixed['tiles'] == {'Core_18B': 2, 'Core_24B': 1, 'Core_32B': 2, 'Core_36B': 1}
    assert all((t['x'], t['y'], t['rotation']) == (1000, 980, 270) for s in fixed['sections'] for t in s['tiles'])
    assert textures(other)['Start'] == ['Core_32A', 'Core_18B'] and textures(other)['Two'][1] == 'Core_32B'


def test_corrections_drop_add_count_and_choose_the_main_sections():
    added = {'texture': 'Core_18B', 'x': 0.0, 'y': 0.0, 'rotation': 90.0}
    (fixed,) = ic2.correct({'missions': [ic2_mission()]}, {'CORE4.json': {
        'drop': ['Three', ['Start', 'Core_18B']], 'add': {'Two': [added]}, 'counts': {'Core_18B': 1},
        'main': ['Start']}})['missions']
    assert textures(fixed) == {'Start': ['Core_32A'], 'Two': ['Core_24A', 'Core_32A', 'Core_18B', 'Core_18B']}
    assert fixed['tiles'] == {'Core_18B': 1, 'Core_24A': 1, 'Core_32A': 2}
    assert fixed['main'] == ['Start']
    assert fixed['hidden'] == [{'name': 'Two', 'sections': ['Two']}]  # each other section with tiles, by default


def test_corrections_move_a_placement_and_name_the_hidden_sections():
    (fixed,) = ic2.correct({'missions': [ic2_mission()]}, {'CORE4.json': {
        'move': {'Two': [['Core_32A', [1000.0, 980.0], [1000.0, 970.0]]]},
        'main': ['Start'], 'hidden': [['Back rooms', ['Two', 'Three']]]}})['missions']
    assert [(t['texture'], t['y']) for t in fixed['sections'][1]['tiles']] == [
        ('Core_24A', 980), ('Core_32A', 970), ('Core_18B', 980)]
    assert fixed['hidden'] == [{'name': 'Back rooms', 'sections': ['Two', 'Three']}]
    at = {'x': 0.0, 'y': 0.0, 'rotation': 0.0}
    two = {'name': 'Two', 'hidden': True, 'tiles': [{'texture': 'Core_18B', **at}, {'texture': 'Core_18B', **at, 'x': 10.0}]}
    (dropped,) = ic2.correct({'missions': [{**ic2_mission(), 'sections': [two]}]},
                             {'CORE4.json': {'drop': [['Two', 'Core_18B', [10.0, 0.0]]]}})['missions']
    assert [t['x'] for t in dropped['sections'][0]['tiles']] == [0.0]
    (renamed,) = ic2.correct({'missions': [{**ic2_mission(), 'sections': [
        {**s, 'name': n} for s, n in zip(ic2_mission()['sections'], ('Start', 'Section 2 - Cave', 'Section 3'))]}]},
        {'CORE4.json': {'main': ['Start']}})['missions']
    assert [h['name'] for h in renamed['hidden']] == ['Cave', 'Section 3']


@pytest.mark.parametrize('fix', [
    {'sides': {'Core_7A': 'Core_7B'}}, {'section sides': {'Three': {'Core_32A': 'Core_32B'}}}, {'drop': ['Four']},
    {'drop': [['Three', 'Core_18B']]}, {'add': {'Four': []}}, {'counts': {'Core_7A': 1}}, {'main': ['Four']},
    {'add': {'Two': [{'texture': 'Door', 'x': 0, 'y': 0, 'rotation': 0}]}}, {'side': {}},
    {'move': {'Two': [['Core_32A', [0.0, 0.0], [1.0, 1.0]]]}}, {'drop': [['Two', 'Core_32A', [0.0, 0.0]]]}, {'hidden': [['Two', ['Two']]]},
    {'main': ['Start'], 'hidden': [['Start', ['Start']]]}, {'main': ['Start'], 'hidden': [['Four', ['Four']]]},
])
def test_corrections_name_what_the_mission_has(fix):
    with pytest.raises(ValueError):
        ic2.correct({'missions': [ic2_mission()]}, {'CORE4.json': fix})



def fake_run(dataset, out):
    """A manifest and IC2 cache that draw every campaign map with the tiles the data has for it, and the drawn files
    (1 x 1 px)."""
    from PIL import Image

    from ia_tools.tiles import EXPANSIONS, NAMES

    codes = {NAMES.get(product, product): code for code, product in EXPANSIONS.items()}
    tiles = {t['id']: t['name'] for t in dataset.records('map-tiles')}
    rows = {}
    for row in dataset.records('map-layouts'):
        product, number = tiles[row['tile_id']].rsplit(' ', 1)
        rows.setdefault(row['map_id'], {})[f"{codes[product]}_{int(number)}{row['side']}"] = row['count']
    out.mkdir(parents=True, exist_ok=True)
    maps, missions = [], []
    for i, record in enumerate({r['id']: r for r in campaign_maps.campaign_maps(dataset).values()}.values()):
        file = record['image'].split('/')[-1]
        Image.new('RGBA', (1, 1)).save(out / file)
        tiles = dict(sorted(rows[record['id']].items()))
        placements = [{'texture': t, 'section': None, 'x': 10 + 3 * j, 'y': 5 + n, 'rotation': 90}
                      for n, (t, count) in enumerate(tiles.items()) for j in range(count)]
        maps.append({'name': record['name'], 'map_id': record['id'], 'ic2': f'F/M{i}.json', 'file': file, 'hidden': [],
                     'placements': placements})
        missions.append({'folder': 'F', 'file': f'M{i}.json', 'tiles': tiles})
    return {'maps': maps}, {'missions': missions}


def test_write_puts_the_maps_hidden_sections_and_layouts_in_the_data(dataset_copy, tmp_path):
    from PIL import Image

    out = tmp_path / 'campaign-maps'
    manifest, cache = fake_run(dataset_copy, out)
    before = {p: dataset_copy.path(p).read_text(encoding='utf-8') for p in ('maps', 'map-layouts')}
    assert campaign_maps.write(manifest, cache, dataset_copy, out=out, log=lambda *a: None) == []
    layouts = json.loads(dataset_copy.path('map-layouts').read_text(encoding='utf-8'))
    counted = [(r['map_id'], r['tile_id'], r['side'], r['count']) for r in layouts]
    assert counted == [(r['map_id'], r['tile_id'], r['side'], r['count'])  # the same tiles: the same rows, sorted
                       for r in sort_rows(dataset_copy, json.loads(before['map-layouts']))]
    drawn = {m['map_id'] for m in manifest['maps']}
    assert all(len(r['placements']) == r['count'] for r in layouts if r['map_id'] in drawn)
    first = [p for r in layouts if r['map_id'] == manifest['maps'][0]['map_id'] for p in r['placements']]
    assert min(p['x'] for p in first) == 0 and min(p['y'] for p in first) == 0  # the frame starts at 0, 0
    assert {p['rotation'] for p in first} == {90} and {p['section'] for p in first} == {None}
    maps = json.loads(dataset_copy.path('maps').read_text(encoding='utf-8'))
    assert all(list(m) == ['id', 'name', 'image', 'hidden_sections', 'whole_image'] and m['hidden_sections'] == []
               and m['whole_image'] is None for m in maps)

    entry, mission = manifest['maps'][0], cache['missions'][0]
    stem = entry['file'][:-4]
    Image.new('RGBA', (1, 1)).save(out / f'{stem}-hidden-1.png')
    (dataset_copy.root / 'images' / 'large' / 'maps' / f'{stem}-hidden-2.png').write_bytes(b'stale')
    Image.new('RGBA', (1, 1)).save(out / f'{stem}-whole.png')
    entry['hidden'] = [{'name': 'Cave', 'sections': ['Two'], 'file': f'{stem}-hidden-1.png'}]
    entry['whole'] = {'file': f'{stem}-whole.png'}
    mission['tiles'] = {'Core_1A': 2}
    entry['placements'] = [{'texture': 'Core_1A', 'section': None, 'x': 5, 'y': 3, 'rotation': 90},
                           {'texture': 'Core_1A', 'section': 'Cave', 'x': 4, 'y': 3, 'rotation': 0},
                           {'texture': 'Core_1A', 'section': 'Cave', 'x': 6, 'y': 3, 'rotation': 0}]
    assert campaign_maps.write(manifest, cache, dataset_copy, out=out, log=lambda *a: None) == []
    maps = json.loads(dataset_copy.path('maps').read_text(encoding='utf-8'))
    record = next(m for m in maps if m['id'] == entry['map_id'])
    assert record['hidden_sections'] == [{'name': 'Cave', 'image': f'maps/{stem}-hidden-1.png'}]
    assert record['whole_image'] == f'maps/{stem}-whole.png'
    for size in ('large', 'small'):
        assert sorted(p.name for p in (dataset_copy.root / 'images' / size / 'maps').glob(f'{stem}-*')) == [
            f'{stem}-hidden-1.png', f'{stem}-whole.png']
    layouts = json.loads(dataset_copy.path('map-layouts').read_text(encoding='utf-8'))
    own = [r for r in layouts if r['map_id'] == entry['map_id']]
    assert [(r['side'], r['count']) for r in own] == [('A', 2)] and layouts == sort_rows(dataset_copy, layouts)
    assert own[0]['placements'] == [{'section': None, 'x': 1, 'y': 0, 'rotation': 90},
                                    {'section': 'Cave', 'x': 0, 'y': 0, 'rotation': 0},
                                    {'section': 'Cave', 'x': 2, 'y': 0, 'rotation': 0}]

    entry['placements'] = entry['placements'][:1]  # a copy placed nowhere
    assert campaign_maps.write(manifest, cache, dataset_copy, out=out, log=lambda *a: None) != []
    entry['placements'] = [{'texture': 'Core_1A', 'section': None, 'x': x, 'y': 0, 'rotation': 0} for x in range(2)]

    del manifest['maps'][1]
    assert campaign_maps.write(manifest, cache, dataset_copy, out=out, log=lambda *a: None) != []


def test_a_shared_maps_file_joins_its_missions_slugs():
    assert campaign_maps.file_stem('Desperate Hour / Last Stand') == 'desperate-hour--last-stand'
    assert campaign_maps.file_stem("Jabba's Realm") == campaign_maps.slugify("Jabba's Realm")
