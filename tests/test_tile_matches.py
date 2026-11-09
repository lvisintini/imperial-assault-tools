import cv2
import numpy as np
import pytest

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
    coarse, fine, shift = tm.compare(one, two)
    assert coarse > 0.95 and fine > 0.95 and shift == (0, 0)
    coarse, fine, _ = tm.compare(one, other)
    assert coarse < tm.COARSE and fine < tm.FINE


def test_the_same_art_turned_isnt_a_match():
    """Sides are stored upright: art that lines up only turned has its pill elsewhere, so it's other art."""
    image, pill = side(1, '35A')
    turned = tm.prepare(np.ascontiguousarray(np.rot90(image, -1)), ((216, 20), (70, 20)))  # a quarter clockwise
    coarse, fine, _ = tm.compare(turned, tm.prepare(image, pill))
    assert coarse < tm.COARSE and fine < tm.FINE


def test_groups_join_linked_pairs():
    pairs = [{'sides': ['a', 'b']}, {'sides': ['c', 'b']}, {'sides': ['d', 'e']}]
    assert tm.groups_of(pairs, ['a', 'b', 'c', 'd', 'e']) == [['a', 'b', 'c'], ['d', 'e']]


def test_a_pill_box_turns_with_its_image():
    image, pill = side(1, '35A')
    for q in range(4):
        turned, ((x, y), (h, w)) = tm.rotated(image, pill, q)
        crop = np.rot90(turned[y:y + h, x:x + w], -q)  # back upright
        (x0, y0), (h0, w0) = pill
        assert (crop == image[y0:y0 + h0, x0:x0 + w0]).all()


def test_copied_art_scores_better_as_stored_than_turned():
    image, pill = side(1, '35A')
    one = tm.prepare(image, pill)
    fine = tm.compare(one, tm.prepare(*side(1, '10A')))[1]
    assert tm.turned_score(one, *side(1, '10A')) < fine - tm.PLAIN


def test_a_small_fit_error_is_taken_out():
    """Two scans fitted separately can sit a degree and a few px apart: the same art still scores as the same."""
    image, pill = side(1, '35A')
    turn = cv2.getRotationMatrix2D((128, 128), 1.5, 1.0)
    turn[:, 2] += (6, -4)
    moved = image.copy()
    moved[..., :3] = cv2.warpAffine(image[..., :3], turn, (256, 256), borderMode=cv2.BORDER_REFLECT)
    one, two = tm.prepare(image, pill), tm.prepare(moved, pill)
    as_stored = tm._scores(one, two)[1]
    assert as_stored < 0.9 and tm.compare(one, two)[1] > as_stored + 0.1


def test_rulings_are_read_by_side_not_group_number():
    rules = [{'same': [['a', 'b', 'c']], 'not': ['d']}, {'same': [['e', 'f']]}, {'apart': [['a', 'b'], ['g']]}]
    assert tm.ruled(rules, 'a', 'c') == 'same'
    assert tm.ruled(rules, 'a', 'd') == 'not'
    assert tm.ruled(rules, 'g', 'b') == 'not'
    assert tm.ruled(rules, 'a', 'e') is None
    assert tm.ruled_extra(rules, {'sides': ['a', 'b']}) == ['c']


def fake_sides(monkeypatch):
    """Four tiles' sides as hires_tiles.sides gives them: (key, product, tile, side, field)."""
    from ia_tools import hires_tiles

    tiles = [{'id': f't{n}', 'squares': 4 if n < 3 else 2} for n in range(4)]
    every = [(f'T{n} {s}', 'P', tiles[n], s, f'side_{s.lower()}') for n in range(4) for s in 'AB']
    monkeypatch.setattr(hires_tiles, 'sides', lambda dataset: every)


def test_rows_pair_every_two_sides_of_a_set_in_tile_order(monkeypatch):
    fake_sides(monkeypatch)
    rows = tm.rows_of(None, [{'same': [['T2 A', 'T0 B', 'T1 A']]}, {'same': [['T0 A', 'T1 B']], 'not': ['T2 B']}])
    assert [(r['tile_id'], r['side'], r['other_tile_id'], r['other_side']) for r in rows] == [
        ('t0', 'A', 't1', 'B'), ('t0', 'B', 't1', 'A'), ('t0', 'B', 't2', 'A'), ('t1', 'A', 't2', 'A')]


def test_rows_refuse_bad_sets(monkeypatch):
    fake_sides(monkeypatch)
    for rules in ([{'same': [['T0 A', 'T9 A']]}], [{'same': [['T0 A', 'T1 A']]}, {'same': [['T0 A', 'T2 A']]}],
                  [{'same': [['T0 A', 'T0 B']]}], [{'same': [['T0 A', 'T3 A']]}]):
        with pytest.raises(ValueError):
            tm.rows_of(None, rules)
