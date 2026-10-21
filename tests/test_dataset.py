import pytest

from ia_tools.dataset import CONTENT_TYPES, dumps


@pytest.mark.parametrize('content_type', CONTENT_TYPES)
def test_saving_unchanged_data_is_byte_identical(real_dataset, content_type):
    path = real_dataset.path(content_type)
    if not path.exists():
        pytest.skip(f'{content_type} is new in data 2.0.0')
    assert dumps(real_dataset.records(content_type)) == path.read_text(encoding='utf-8')


def test_new_ids_follow_the_schema(dataset_copy):
    """UUIDs from data 2.0.0 on; before that, the numbers after the highest id."""
    ids = dataset_copy.new_ids('heroes')
    first, second = next(ids), next(ids)
    heroes = dataset_copy.records('heroes')
    if dataset_copy.uses_uuids('heroes'):
        assert isinstance(first, str) and len(first) == 36 and first != second
        assert first not in {h['id'] for h in heroes}
        assert dataset_copy.parse_id('heroes', first) == first
    else:
        assert (first, second) == (max(h['id'] for h in heroes) + 1, max(h['id'] for h in heroes) + 2)
        assert dataset_copy.parse_id('heroes', '3') == 3


def test_schema_refs_are_resolved(real_dataset):
    affiliation = real_dataset.schema('deployment-cards')['properties']['affiliation']
    assert 'Rebel' in affiliation['enum']


def test_has_ids_follows_the_schemas(real_dataset):
    assert real_dataset.has_ids('command-cards') and real_dataset.has_ids('form-cards')
    assert not real_dataset.has_ids('source-contents')
    assert real_dataset.has_ids('card-backs') == real_dataset.uses_uuids('sources')  # card backs got ids in 2.0.0
