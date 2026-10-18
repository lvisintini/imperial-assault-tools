import io
import re

import pytest
from PIL import Image

from ia_tools import images
from tests.conftest import png_bytes


def test_fit_pads_to_exact_size_and_keeps_aspect():
    fitted = images.fit(Image.new('RGBA', (1000, 1000), (255, 0, 0, 255)), (424, 657))
    assert fitted.size == (424, 657)
    assert fitted.getpixel((0, 0))[3] == 0          # transparent padding
    assert fitted.getpixel((212, 328))[3] == 255    # the card itself


def test_process_card_makes_palette_pngs_at_both_sizes(tmp_path):
    original = tmp_path / 'card.png'
    original.write_bytes(png_bytes((600, 930)))
    out = images.process(original, 'deployment-cards')
    for size, expected in (('large', (476, 740)), ('small', (301, 470))):
        with Image.open(io.BytesIO(out[size])) as im:
            assert (im.format, im.size, im.mode) == ('PNG', expected, 'P')
    assert out['upscaled'] is False


def test_process_flags_upscaling(tmp_path):
    original = tmp_path / 'small.png'
    original.write_bytes(png_bytes((200, 300)))
    assert images.process(original, 'command-cards')['upscaled'] is True


def test_skirmish_maps_keep_their_size_in_both_trees(tmp_path):
    original = tmp_path / 'map.png'
    original.write_bytes(png_bytes((800, 1200)))
    out = images.process(original, 'skirmish-maps')
    assert out['large'] == out['small']
    with Image.open(io.BytesIO(out['large'])) as im:
        assert im.size == (800, 1200)


def test_card_backs_size_by_what_they_are_the_back_of():
    assert images.sizes_for('card-backs', 'heroes') == images.MINI
    assert images.sizes_for('card-backs', 'deployment-cards') == images.STANDARD
    with pytest.raises(KeyError):
        images.sizes_for('card-backs', 'sources')


def test_sizes_match_the_data_repo_tests(real_dataset):
    """Cross-check against the data repo's ImageTestHelper, the source of truth for sizes. Parsed as text: importing
    it would clash with this repo's own tests package."""
    tests_dir = real_dataset.root / 'tests'
    constants = dict(re.findall(r"^\s+(\w+) = '([a-z-]+)'$", (tests_dir / 'constants.py').read_text(), re.M))
    source = (tests_dir / 'test_images.py').read_text()
    dims = {name: (int(w), int(h)) for name, w, h in re.findall(r'^\s+(\w+) = \((\d+), (\d+)\)$', source, re.M)}
    dims['ANY'] = None
    definitions = re.findall(
        r"ImageDefinition\('(large|small)', CONTENT_TYPES\.(\w+), '\w+', dims=(\w+)(?:, content_type=CONTENT_TYPES\.(\w+))?\)",
        source)
    assert len(definitions) > 50
    for size, content_type, dim_name, back_of in definitions:
        sizes = images.sizes_for(constants[content_type], constants[back_of] if back_of else None)
        assert (None if sizes is None else sizes[size]) == dims[dim_name], (size, content_type, back_of)
