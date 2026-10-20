import pytest

from ia_tools.dataset import CONTENT_TYPES, dumps


@pytest.mark.parametrize('content_type', CONTENT_TYPES)
def test_saving_unchanged_data_is_byte_identical(real_dataset, content_type):
    path = real_dataset.path(content_type)
    assert dumps(real_dataset.records(content_type)) == path.read_text(encoding='utf-8')


def test_next_id_follows_the_highest(dataset_copy):
    heroes = dataset_copy.records('heroes')
    assert dataset_copy.next_id('heroes') == max(h['id'] for h in heroes) + 1


def test_schema_refs_are_resolved(real_dataset):
    affiliation = real_dataset.schema('deployment-cards')['properties']['affiliation']
    assert 'Rebel' in affiliation['enum']


def test_has_ids_follows_the_schemas(real_dataset):
    assert real_dataset.has_ids('command-cards') and real_dataset.has_ids('form-cards')
    assert not real_dataset.has_ids('card-backs') and not real_dataset.has_ids('source-contents')
