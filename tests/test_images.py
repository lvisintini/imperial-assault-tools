import io
import re

import pytest
from PIL import Image

from ia_tools import images
from ia_tools.dataset import BACK_KEYS
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
    out = images.process(original, 'maps')
    assert out['large'] == out['small']
    with Image.open(io.BytesIO(out['large'])) as im:
        assert im.size == (800, 1200)


def test_round_corners_cuts_transparent_corners_on_the_card():
    card = Image.new('RGBA', (476, 740), (200, 30, 30, 255))
    rounded = images.round_corners(card, 32)
    alpha = rounded.getchannel('A')
    assert alpha.getpixel((0, 0)) == 0 and alpha.getpixel((475, 739)) == 0
    assert alpha.getpixel((5, 5)) == 0 and alpha.getpixel((16, 16)) == 255   # inside the curve
    assert alpha.getpixel((238, 0)) == 255 and alpha.getpixel((238, 370)) == 255
    assert rounded.getpixel((238, 370))[:3] == (200, 30, 30)


def test_round_corners_follows_the_card_not_the_canvas():
    canvas = Image.new('RGBA', (476, 740))
    canvas.paste(Image.new('RGBA', (400, 700), (0, 0, 0, 255)), (38, 20))
    alpha = images.round_corners(canvas, 32).getchannel('A')
    assert alpha.getpixel((38, 20)) == 0 and alpha.getpixel((238, 20)) == 255


def test_corner_radius_scales_with_the_small_size():
    assert images.radius_for('deployment-cards', None, 'large') == 32
    assert images.radius_for('deployment-cards', None, 'small') == round(32 * 301 / 476)
    assert images.radius_for('heroes', None, 'large') is None  # hero sheets keep square corners


def test_process_rounds_cards_but_not_hero_sheets(tmp_path):
    original = tmp_path / 'card.png'
    original.write_bytes(png_bytes((600, 930)))
    for content_type, rounded in (('deployment-cards', True), ('heroes', False)):
        out = images.process(original, content_type, image_field='healthy' if content_type == 'heroes' else 'image')
        with Image.open(io.BytesIO(out['large'])) as im:
            alpha = im.convert('RGBA').getchannel('A')
            box = alpha.getbbox()
            assert (alpha.getpixel(box[:2]) == 0) is rounded, content_type


def test_card_backs_size_by_what_they_are_the_back_of():
    assert images.sizes_for('card-backs', 'heroes') == images.MINI
    assert images.sizes_for('card-backs', 'deployment-cards') == images.STANDARD
    assert images.sizes_for('card-backs', 'skirmish-missions') == images.STANDARD_FLIPPED
    with pytest.raises(KeyError):
        images.sizes_for('card-backs', 'sources')
    for back_of, sizes in images.BACK_SIZES.items():  # a back has its cards' size
        cards = [t for t, key in BACK_KEYS.items() if key == back_of] or [back_of]
        assert all(images.SIZES[t] == sizes for t in cards), back_of


def test_sizes_match_the_data_repo_tests(real_dataset):
    """Cross-check against the data repo's ImageTestHelper, the source of truth for sizes. Parsed as text: importing
    it would clash with this repo's own tests package."""
    tests_dir = real_dataset.root / 'tests'
    constants = dict(re.findall(r"^\s+(\w+) = '([a-z-]+)'$", (tests_dir / 'constants.py').read_text(), re.M))
    source = (tests_dir / 'test_images.py').read_text()
    dims = {name: (int(w), int(h)) for name, w, h in re.findall(r'^\s+(\w+) = \((\d+), (\d+)\)$', source, re.M)}
    dims['ANY'] = None
    dims['CARDS_USING_IT'] = 'skip'  # 2.0.0: a back is checked at its cards' size (the test above)
    dims['TILE'] = 'skip'  # 2.0.0: map tiles come from the Vassal module as they are (ia tiles checks them)
    definitions = re.findall(
        r"ImageDefinition\('(large|small)', CONTENT_TYPES\.(\w+), '\w+', dims=(\w+)(?:, content_type=CONTENT_TYPES\.(\w+))?\)",
        source)
    assert len(definitions) > 40
    for size, content_type, dim_name, back_of in definitions:
        if dims[dim_name] == 'skip':
            continue
        sizes = images.sizes_for(constants[content_type], constants[back_of] if back_of else None)
        assert (None if sizes is None else sizes[size]) == dims[dim_name], (size, content_type, back_of)
