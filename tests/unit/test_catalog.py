from importlib import resources
import json
from pathlib import Path

import pytest

from content_planner.domain import Fault


ROOT = Path(__file__).resolve().parents[2]


def test_default_data_is_packaged_and_matches_spec_fixtures():
    data = resources.files('content_planner').joinpath('data')
    for name in ('materials.json', 'pricing.json', 'aliases.json'):
        assert data.joinpath(name).is_file(), name
        assert data.joinpath(name).read_bytes() == (ROOT / 'contracts/fixtures' / name).read_bytes()


def test_catalog_loads_hashes_from_package_outside_repository(tmp_path, monkeypatch):
    import hashlib
    from content_planner.catalog import load_catalog

    monkeypatch.chdir(tmp_path)
    catalog = load_catalog()
    assert [material.material_id for material in catalog.materials] == ['M01', 'M02']
    assert catalog.pricing.version == 'pricing-v1'
    assert catalog.catalog_hash == hashlib.sha256((ROOT / 'contracts/fixtures/materials.json').read_bytes()).hexdigest()
    assert catalog.pricing_hash == hashlib.sha256((ROOT / 'contracts/fixtures/pricing.json').read_bytes()).hexdigest()


@pytest.fixture
def data_directory(tmp_path):
    for name in ('materials', 'pricing', 'aliases'):
        (tmp_path / (name + '.json')).write_bytes((ROOT / 'contracts/fixtures' / (name + '.json')).read_bytes())
    return tmp_path


def test_invalid_pricing_is_rejected_without_default_quote(data_directory):
    from content_planner.catalog import load_catalog

    path = data_directory / 'pricing.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['video_edit']['basic']['fee_units'] = True
    path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(Fault, match='PRICING_INVALID'):
        load_catalog(data_directory)


def test_duplicate_material_ids_are_rejected(data_directory):
    from content_planner.catalog import load_catalog

    path = data_directory / 'materials.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['materials'].append(payload['materials'][0])
    path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(Fault, match='CATALOG_UNAVAILABLE'):
        load_catalog(data_directory)


@pytest.mark.parametrize('name,code', [('materials', 'CATALOG_UNAVAILABLE'),
                                     ('aliases', 'CATALOG_UNAVAILABLE'), ('pricing', 'ESTIMATOR_UNAVAILABLE')])
def test_missing_data_file_has_explicit_error(data_directory, name, code):
    from content_planner.catalog import load_catalog

    (data_directory / (name + '.json')).unlink()
    with pytest.raises(Fault, match=code):
        load_catalog(data_directory)


@pytest.mark.parametrize('name,code', [('materials', 'CATALOG_UNAVAILABLE'),
                                     ('aliases', 'CATALOG_UNAVAILABLE'), ('pricing', 'PRICING_INVALID')])
def test_malformed_data_has_explicit_error(data_directory, name, code):
    from content_planner.catalog import load_catalog

    (data_directory / (name + '.json')).write_text('not JSON', encoding='utf-8')
    with pytest.raises(Fault, match=code):
        load_catalog(data_directory)


def test_empty_alias_is_rejected(data_directory):
    from content_planner.catalog import load_catalog

    path = data_directory / 'aliases.json'
    path.write_text(json.dumps({'version': 'aliases-v1', 'aliases': {' ': '字幕'}}), encoding='utf-8')
    with pytest.raises(Fault, match='CATALOG_UNAVAILABLE'):
        load_catalog(data_directory)


def test_catalog_search_counts_distinct_tags_and_handles_empty_results():
    from content_planner.catalog import load_catalog

    catalog = load_catalog()
    assert catalog.search('不存在的功能', 5) == []
    matches = catalog.search('字幕 字幕 自动字幕 字幕编辑', 5)
    assert [(item['material_id'], item['score']) for item in matches] == [('M01', 3)]


def test_search_normalizes_aliases_and_returns_stable_top_k():
    from content_planner.catalog import load_catalog

    catalog = load_catalog()
    assert [item['material_id'] for item in catalog.search('  CAPTION  ', 5)] == ['M01']
    assert [item['material_id'] for item in catalog.search('字幕 裁剪', 5)] == ['M01', 'M02']
    assert [item['material_id'] for item in catalog.search('字幕 裁剪', 1)] == ['M01']


def test_long_alias_precedes_short_alias_and_unicode_is_normalized(data_directory):
    from content_planner.catalog import load_catalog

    path = data_directory / 'aliases.json'
    path.write_text(json.dumps({'version': 'aliases-v1',
                               'aliases': {'cap': '裁剪', 'caption': '字幕', 'Café': '字幕'}}), encoding='utf-8')
    catalog = load_catalog(data_directory)
    assert [item['material_id'] for item in catalog.search(' CAPTION ', 5)] == ['M01']
    assert [item['material_id'] for item in catalog.search(' Cafe\u0301 ', 5)] == ['M01']


@pytest.mark.parametrize('field,value', [('fee_units', -1), ('lead_minutes', True),
                                        ('facts', []), ('tags', [' '])])
def test_invalid_material_values_are_rejected(data_directory, field, value):
    from content_planner.catalog import load_catalog

    path = data_directory / 'materials.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['materials'][0][field] = value
    path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(Fault, match='CATALOG_UNAVAILABLE'):
        load_catalog(data_directory)


@pytest.mark.parametrize('value', [1, 1.0])
def test_synthetic_flag_requires_boolean_true(data_directory, value):
    from content_planner.catalog import load_catalog

    path = data_directory / 'materials.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['synthetic'] = value
    path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(Fault, match='CATALOG_UNAVAILABLE'):
        load_catalog(data_directory)
