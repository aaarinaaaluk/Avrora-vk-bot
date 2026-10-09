
import json
from pathlib import Path


SOURCES_PATH = Path(__file__).resolve().parents[1] / "data" / "sources.json"


def load_sources():
    with SOURCES_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def test_sources_file_is_not_empty():
    sources = load_sources()
    assert len(sources) > 0


def test_each_source_has_required_fields():
    required_fields = {
        "id",
        "name",
        "url",
        "resource_type",
        "intended_use",
        "limitations",
        "access",
        "status",
        "supported_claim_types",
    }

    for source in load_sources():
        assert required_fields.issubset(source.keys())


def test_source_ids_are_unique():
    sources = load_sources()
    ids = [source["id"] for source in sources]
    assert len(ids) == len(set(ids))


def test_source_status_is_allowed():
    allowed_statuses = {"pending", "verified", "unavailable"}

    for source in load_sources():
        assert source["status"] in allowed_statuses
        
def test_source_name_and_url_are_not_empty():
    for source in load_sources():
        assert source["name"].strip()
        assert source["url"].startswith("https://")