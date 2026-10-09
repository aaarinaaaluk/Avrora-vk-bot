
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