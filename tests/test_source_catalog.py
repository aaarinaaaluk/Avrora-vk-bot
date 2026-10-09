
from app.core.source_catalog import load_sources
from app.core.source_catalog import find_sources_by_claim_types


def test_catalog_loads_as_a_list():
    sources = load_sources()
    assert isinstance(sources, list)


def test_catalog_contains_ministry_source():
    sources = load_sources()

    assert any(
        source["id"] == "ru_moh_clinical_guidelines"
        for source in sources
    )


def test_loaded_sources_have_required_fields():
    required_fields = {
        "id",
        "name",
        "url",
        "resource_type",
        "status",
    }

    for source in load_sources():
        assert required_fields.issubset(source.keys())
        
def test_find_sources_by_claim_type():
    sources = find_sources_by_claim_types(["SAFETY"])

    assert any(
        source["id"] == "ru_moh_clinical_guidelines"
        for source in sources
    )


def test_find_sources_by_multiple_claim_types():
    sources = find_sources_by_claim_types(["SAFETY", "CAUSAL"])

    assert any(
        "SAFETY" in source["supported_claim_types"]
        or "CAUSAL" in source["supported_claim_types"]
        for source in sources
    )


def test_find_sources_with_empty_claim_types():
    assert find_sources_by_claim_types([]) == []