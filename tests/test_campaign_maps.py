import json

import numpy as np

from ia_tools import campaign_maps, ic2


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
