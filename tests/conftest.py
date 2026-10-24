import io
import shutil
import uuid
from pathlib import Path

import pytest
from PIL import Image

from ia_tools import settings
from ia_tools.dataset import Dataset

FIXTURES = Path(__file__).parent / 'fixtures'


def fixture_html(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


def png_bytes(size, color=(200, 30, 30, 255)):
    """A generated test image (never a dataset image)."""
    buffer = io.BytesIO()
    Image.new('RGBA', size, color).save(buffer, 'PNG')
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def no_tinypng(monkeypatch):
    """Tests encode locally: a TINIFY_KEY in the environment would spend the account's monthly compressions."""
    monkeypatch.setattr(settings, 'TINIFY_KEY', None)


# How data 2.0.0 derived its UUIDs from 1.x ids (migrations/2.0.0/01_uuid_ids.py in the data repo).
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/lvisintini/imperial-assault-data')


def legacy_id(dataset, content_type, old_id):
    """A record's id given its 1.x number: the number itself in 1.x data, its derived UUID from 2.0.0 on.
    None stays None."""
    if old_id is None or not dataset.uses_uuids(content_type):
        return old_id
    return str(uuid.uuid5(UUID_NAMESPACE, f'{content_type}:{old_id}'))


@pytest.fixture(scope='session')
def real_dataset():
    if not (settings.DATA_ROOT / 'data' / 'sources.json').is_file():
        pytest.skip(f'No imperial-assault-data checkout at {settings.DATA_ROOT} (set IA_DATA_ROOT)')
    return Dataset(settings.DATA_ROOT)


@pytest.fixture
def dataset_copy(real_dataset, tmp_path):
    """data/ and schemas/ of the real checkout (and its test fixtures, data 2.0.0), copied to a temp folder with empty
    image trees."""
    root = tmp_path / 'imperial-assault-data'
    shutil.copytree(real_dataset.root / 'data', root / 'data')
    shutil.copytree(real_dataset.root / 'schemas', root / 'schemas')
    if (real_dataset.root / 'tests' / 'fixtures').is_dir():
        shutil.copytree(real_dataset.root / 'tests' / 'fixtures', root / 'tests' / 'fixtures')
    (root / 'images' / 'large').mkdir(parents=True)
    (root / 'images' / 'small').mkdir(parents=True)
    return Dataset(root)


@pytest.fixture
def hash_files(tmp_path, monkeypatch):
    seen, skipped = tmp_path / 'seen.txt', tmp_path / 'skipped.txt'
    seen.write_text('aaa\n')
    monkeypatch.setattr(settings, 'SEEN_HASHES', seen)
    monkeypatch.setattr(settings, 'SKIPPED_HASHES', skipped)
    return seen, skipped
