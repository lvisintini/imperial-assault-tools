import cv2
import numpy
import pytest
from PIL import Image

from ia_tools import align, images, settings

LEIA = 'deployment-cards/leia-organa-rebel-commander-campaign.png'


def template(name, size):
    with Image.open(settings.TEMPLATES / name) as im:
        return images.fit(im, size)


def grey_difference(a, b):
    return float(numpy.abs(align.grey(numpy.asarray(a)) - align.grey(numpy.asarray(b))).mean())


@pytest.mark.parametrize('names', list(align.TEMPLATES.values()) + list(align.BACK_TEMPLATES.values()))
def test_every_template_exists(names):
    for name in names:
        assert (settings.TEMPLATES / name).is_file(), name


def test_a_shifted_and_rotated_card_is_put_back():
    size = images.STANDARD['large']
    card = template(LEIA, size)
    moved = cv2.warpAffine(numpy.asarray(card), cv2.getRotationMatrix2D((238, 370), 1.5, 1.0) + [[0, 0, 7], [0, 0, -5]],
                           size, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    aligned, result = align.align(Image.fromarray(moved, 'RGBA'), 'deployment-cards')
    assert result['template'] == LEIA and result['cc'] > 0.95
    assert grey_difference(aligned, card) < grey_difference(moved, card) / 3


def test_cards_that_match_no_template_are_left_alone():
    noise = numpy.random.default_rng(1).integers(0, 255, (740, 476, 4), dtype=numpy.uint8)
    noise[:, :, 3] = 255
    image = Image.fromarray(noise, 'RGBA')
    aligned, result = align.align(image, 'deployment-cards')
    assert result is None and aligned is image


def test_types_without_templates_are_left_alone():
    image = Image.new('RGBA', (300, 300), (10, 20, 30, 255))
    assert align.align(image, 'sources') == (image, None)


def test_hero_sides():
    assert align.templates_for('heroes', 'wounded') == ['heroes/diala-passil-wounded.png']
    assert len(align.templates_for('heroes')) == 2  # the entry app's preview doesn't say which side
    assert align.templates_for('card-backs', back_content_type='deployment-cards') == ['card-backs/deployment-imperial.png']
