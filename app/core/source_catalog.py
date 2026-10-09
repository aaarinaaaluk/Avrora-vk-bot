
import json
from pathlib import Path
from typing import Any


SOURCES_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "sources.json"
)


def load_sources() -> list[dict[str, Any]]:
    """Загружает каталог медицинских источников из JSON."""
    with SOURCES_PATH.open(encoding="utf-8") as file:
        sources = json.load(file)

    if not isinstance(sources, list):
        raise ValueError("Каталог источников должен быть списком.")

    return sources


def find_sources_by_claim_types(
    claim_types: list[str],
) -> list[dict[str, Any]]:
    """Находит источники, подходящие хотя бы по одной метке."""
    requested_types = set(claim_types)

    if not requested_types:
        return []

    return [
        source
        for source in load_sources()
        if requested_types.intersection(
            source.get("supported_claim_types", [])
        )
    ]