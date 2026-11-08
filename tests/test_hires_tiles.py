import cv2
import numpy as np
import pytest

from ia_tools import hires_tiles


def textured(width, height, seed=0):
    """A generated tile side (never a dataset image): width x height squares at 128 px, blobs of colour (so SIFT has
    features), opaque, with a notch cut out of its top-left corner so its outline has one way up."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (height * 8, width * 8, 3), dtype=np.uint8)
    rgb = cv2.resize(small, (width * 128, height * 128), interpolation=cv2.INTER_CUBIC)
    alpha = np.full(rgb.shape[:2], 255, np.uint8)
    alpha[:64, :64] = 0
    return np.dstack([rgb, alpha])


def plain(width, height):
    """A generated side with one flat colour: only its outline (an L) tells its turn."""
    image = np.zeros((height * 128, width * 128, 4), np.uint8)
    image[..., :3] = (120, 90, 60)
    image[..., 3] = 255
    image[:128, 128:] = 0
    return image


@pytest.mark.parametrize('k', range(4))
def test_a_scan_is_fitted_onto_ours_whatever_its_turn(k):
    ours = textured(3, 2, seed=1)
    scan = np.ascontiguousarray(np.rot90(ours, k))  # turned counter-clockwise k times
    scan = cv2.resize(scan, None, fx=1.03, fy=1.03, interpolation=cv2.INTER_CUBIC)  # and a little off in scale
    M, how, (corr, iou) = hires_tiles.register(ours, scan)
    assert how.startswith('features') and corr > 0.97 and iou > 0.98
    assert hires_tiles.turn_of(M) == (k * 90) % 360  # turning it back is k quarter turns clockwise


@pytest.mark.parametrize('k', range(4))
def test_a_plain_scan_is_fitted_by_its_outline(k):
    ours = plain(2, 2)
    scan = np.ascontiguousarray(np.rot90(ours, k))
    M = hires_tiles.by_outline(ours, scan)
    warped = hires_tiles.warp(scan, M, (ours.shape[1], ours.shape[0]))
    assert hires_tiles.score(ours, warped)[1] > 0.99


def test_tone_curves_map_one_histogram_onto_another():
    rng = np.random.default_rng(2)
    dst = rng.integers(40, 220, 50000).astype(np.uint8)
    src = (dst.astype(int) // 2 + 100).astype(np.uint8)  # washed out: half the contrast, lifted
    curve = hires_tiles.tone_curve(src, dst)
    assert np.abs(curve[src].astype(int) - dst).mean() < 2
    image = np.dstack([np.full((2, 2), 150, np.uint8)] * 3 + [np.full((2, 2), 255, np.uint8)])
    out = hires_tiles.apply_curves(image, np.stack([curve] * 3))
    assert out[0, 0, 0] == curve[150] and out[0, 0, 3] == 255


def test_a_sides_scan_is_found_whatever_its_names_case(tmp_path):
    (tmp_path / 'heart_1B.png').write_bytes(b'')
    (tmp_path / 'Core_10A.png').write_bytes(b'')
    assert hires_tiles.scan_file('Heart of the Empire', 1, 'B', tmp_path).name == 'heart_1B.png'
    assert hires_tiles.scan_file('Imperial Assault', 10, 'A', tmp_path).name == 'Core_10A.png'
    assert hires_tiles.scan_file('Imperial Assault', 1, 'A', tmp_path) is None


def test_a_scan_of_another_side_is_found_out_and_not_staged(dataset_copy, tmp_path):
    """Two same-sized sides with generated art; one's scan is a copy of the other's (as Heart_13A.png was 15A's)."""
    from PIL import Image

    tiles = [t for t in dataset_copy.records('map-tiles') if t['name'].startswith('Core Set')]
    first, second = [t for t in tiles if (t['width'], t['height'], t['squares']) == (2, 2, 4)][:2]
    scans = tmp_path / 'scans'
    scans.mkdir()
    for n, tile in enumerate((first, second)):
        art = textured(2, 2, seed=10 + n)
        art[..., 3] = 255
        path = dataset_copy.root / 'images' / 'large' / tile['side_a']
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(cv2.resize(art, (128, 128), interpolation=cv2.INTER_AREA)).save(path)
        scan = cv2.resize(art, (2 * 299, 2 * 299), interpolation=cv2.INTER_CUBIC)
        Image.fromarray(scan).save(scans / f"Core_{tile['number']}A.png")
    # The first side's scan is the second's.
    (scans / f"Core_{first['number']}A.png").write_bytes((scans / f"Core_{second['number']}A.png").read_bytes())
    keys = [f"{t['name']} A" for t in (first, second)]
    manifest, problems = hires_tiles.run(dataset_copy, scans=scans, out=tmp_path / 'out', only=keys, log=lambda *_: None)
    assert any(p.startswith(f'{keys[0]}: its scan') and f'looks like {keys[1]}' in p for p in problems)
    assert list(manifest['sides']) == [keys[1]]
    assert not (tmp_path / 'out' / first['side_a']).exists() and (tmp_path / 'out' / second['side_a']).exists()
