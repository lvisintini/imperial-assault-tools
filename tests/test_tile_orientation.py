import cv2
import numpy as np
import pytest

from ia_tools import tile_orientation as to


def pill(width=118, height=44):
    """A generated upright pill (never a dataset image): light, a dark frame, an icon at the left, two tall digits and
    a shorter letter on their baseline."""
    image = np.full((height, width), 140, np.uint8)
    cv2.rectangle(image, (0, 0), (width - 1, height - 1), 50, 2)
    cv2.circle(image, (24, 22), 16, 60, -1)
    cv2.rectangle(image, (50, 5), (64, 38), 60, -1)
    cv2.rectangle(image, (70, 5), (84, 38), 60, -1)
    cv2.rectangle(image, (91, 12), (103, 38), 60, -1)
    return image


@pytest.mark.parametrize('k', range(4))
def test_turns_and_quarter_turns_go_both_ways(k):
    assert to.k_of_turn(to.turn_of_k(k)) == k
    image = np.arange(6).reshape(2, 3)
    assert (to.turned(np.rot90(image, -k), to.turn_of_k(k)) == image).all()  # k clockwise turns, undone


def test_an_upright_pill_has_two_digits_and_a_letter():
    boxes = to.glyph_boxes(pill())
    assert boxes is not None and [b[0] for b in boxes] == [50, 70, 91]
    assert to.glyph_boxes(np.ascontiguousarray(np.rot90(pill(), 2))) is None  # upside down


@pytest.mark.parametrize('k', range(4))
def test_a_pill_is_found_whatever_its_turn(k):
    rng = np.random.default_rng(k)
    scan = rng.integers(0, 255, (400, 500)).astype(np.uint8)
    scan = cv2.GaussianBlur(scan, (0, 0), 3)
    turned = np.ascontiguousarray(np.rot90(pill(), -k))  # as a scan k counter-clockwise turns make upright shows it
    scan[100:100 + turned.shape[0], 200:200 + turned.shape[1]] = turned
    best = to.match(scan.astype(np.float32), pill().astype(np.float32))[0]
    assert best[1] == k and best[2] == (200, 100)
    assert to.glyph_boxes(to.upright_crop(scan, best)) is not None


def test_a_glyph_is_read_by_its_neighbours():
    """Three generated pills whose second digit is a bar or a ring, labelled 11A and 10A: a fourth reads by them."""
    def digit_pill(ring):
        image = pill()
        if ring:
            cv2.rectangle(image, (70, 5), (84, 38), 140, -1)
            cv2.rectangle(image, (70, 5), (84, 38), 60, 3)
        return image

    def noisy(image, seed):
        return (image.astype(np.int16) + np.random.default_rng(seed).integers(-6, 6, image.shape)).clip(0, 255) \
            .astype(np.uint8)

    cells = to.glyph_boxes(pill())
    pills = {'a': ('11A', noisy(pill(), 1), cells), 'b': ('10A', noisy(digit_pill(True), 2), cells),
             'c': ('11A', noisy(pill(), 3), cells), 'd': ('00A', noisy(digit_pill(True), 4), cells)}
    assert to.read_codes(pills)['d'][0] == '10A'  # its first digit like the 1s, its second like 10A's 0

