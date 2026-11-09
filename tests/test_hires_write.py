import json

import numpy as np
from PIL import Image

from ia_tools import hires_tiles


class Data:
    """A data repo with one tile (generated images, never the dataset's)."""

    def __init__(self, root):
        self.root = root
        self.tile = {'id': 't', 'name': 'Core Set 01', 'number': 1, 'side_a': 'map-tiles/core-set-01-a.png',
                     'side_b': 'map-tiles/core-set-01-b.png'}
        for size in ('large', 'small'):
            (root / 'images' / size / 'map-tiles').mkdir(parents=True)
            for field in ('side_a', 'side_b'):
                Image.new('RGBA', (160, 128), (1, 2, 3, 255)).save(root / 'images' / size / self.tile[field])

    def records(self, content_type):
        return [self.tile]


def stage(out, sides, size=(320, 256)):
    (out / 'map-tiles').mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    for path in ('map-tiles/core-set-01-a.png', 'map-tiles/core-set-01-b.png'):
        Image.fromarray(rng.integers(0, 255, (size[1], size[0], 4), dtype=np.uint8)).save(out / path)
    (out / 'manifest.json').write_text(json.dumps({'sides': sides}))


def test_write_puts_large_and_halved_small_images(tmp_path):
    data = Data(tmp_path / 'data')
    stage(tmp_path / 'out', {'Core Set 01 A': {'turn': 90, 'scan_turn': 90}, 'Core Set 01 B': {'turn': 0, 'scan_turn': 0}})
    assert hires_tiles.write(data, tmp_path / 'out', log=lambda *a: None) == []
    root = data.root / 'images'
    assert (root / 'large' / data.tile['side_a']).read_bytes() == (tmp_path / 'out' / data.tile['side_a']).read_bytes()
    with Image.open(root / 'small' / data.tile['side_a']) as small:
        assert small.size == (160, 128)


def test_write_refuses_a_side_off_its_pill_turn_or_the_wrong_size(tmp_path):
    data = Data(tmp_path / 'data')
    stage(tmp_path / 'out', {'Core Set 01 A': {'turn': 180, 'scan_turn': 0}}, size=(300, 256))
    problems = hires_tiles.write(data, tmp_path / 'out', log=lambda *a: None)
    assert any('not at its pill' in p for p in problems) and any('small image is' in p for p in problems)
    assert any('Core Set 01 B: not staged' in p for p in problems)
    with Image.open(data.root / 'images' / 'large' / data.tile['side_a']) as large:
        assert large.size == (160, 128)  # nothing written
