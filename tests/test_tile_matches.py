import cv2
import numpy as np

from ia_tools import tile_matches as tm


def side(seed, pill_text, size=256):
    """A generated side (never a dataset image) at 128 px per square: random blobs as its art, a pill drawn at the
    top left."""
    rng = np.random.default_rng(seed)
    image = np.full((size, size, 3), 120, np.uint8)
    for _ in range(40):
        x, y, r = rng.integers(0, size, 2).tolist() + [int(rng.integers(4, 20))]
        cv2.circle(image, (x, y), r, tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
    cv2.rectangle(image, (20, 20), (90, 40), (230, 230, 230), -1)
    cv2.putText(image, pill_text, (24, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    return np.dstack([image, np.full((size, size), 255, np.uint8)]), ((20, 20), (20, 70))


def test_same_art_with_another_pill_matches_and_other_art_doesnt():
    one, two, other = (tm.prepare(*side(seed, text)) for seed, text in ((1, '35A'), (1, '10A'), (2, '35A')))
    coarse, turn, fine, shift = tm.compare(one, two)
    assert coarse > 0.95 and fine > 0.95 and turn == 0 and shift == (0, 0)
    coarse, _, fine, _ = tm.compare(one, other)
    assert coarse < tm.COARSE and fine < tm.FINE


def test_turned_art_is_found_turned():
    image, pill = side(1, '35A')
    turned = tm.prepare(np.ascontiguousarray(np.rot90(image, -1)), ((216, 20), (70, 20)))  # a quarter clockwise
    assert tm.compare(turned, tm.prepare(image, pill))[1] == 90


def test_groups_join_linked_pairs():
    pairs = [{'sides': ['a', 'b']}, {'sides': ['c', 'b']}, {'sides': ['d', 'e']}]
    assert tm.groups_of(pairs, ['a', 'b', 'c', 'd', 'e']) == [['a', 'b', 'c'], ['d', 'e']]
