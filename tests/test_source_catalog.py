
from app.core.source_catalog import load_sources


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