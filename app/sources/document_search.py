"""Поиск по явно зарегистрированным локальным PDF-документам."""

import json
from pathlib import Path
from typing import Any

from app.sources.pdf_reader import extract_pdf_text
from app.sources.text_search import SearchResult, search_document


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
DOCUMENT_CATALOG_PATH = PROJECT_ROOT / "data" / "document_catalog.json"


def load_document_catalog() -> list[dict[str, Any]]:
    """Возвращает только включённые документы с полными метаданными."""
    if not DOCUMENT_CATALOG_PATH.is_file():
        return []

    with DOCUMENT_CATALOG_PATH.open(encoding="utf-8") as file:
        catalog = json.load(file)

    if not isinstance(catalog, list):
        raise ValueError("Каталог документов должен быть списком.")

    enabled_documents = []
    for item in catalog:
        if not isinstance(item, dict) or item.get("enabled") is not True:
            continue

        required_fields = ("id", "filename", "title", "source_id", "source_url")
        if any(
            not isinstance(item.get(field), str) or not item[field].strip()
            for field in required_fields
        ):
            continue

        filename = item["filename"]
        if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
            continue

        enabled_documents.append(item)

    return enabled_documents


def search_documents(query: str, limit: int = 5) -> list[SearchResult]:
    """Ищет совпадения по всем включённым и зарегистрированным PDF."""
    if limit < 1:
        raise ValueError("limit должен быть не меньше 1")

    if not DOCUMENTS_DIR.is_dir():
        return []

    results: list[SearchResult] = []
    catalog = load_document_catalog()
    registered_names = set()

    for item in catalog:
        filename = item["filename"]
        # Не обрабатываем один файл повторно при случайном дубликате записи.
        if filename in registered_names:
            continue
        registered_names.add(filename)

        pdf_path = DOCUMENTS_DIR / filename
        if not pdf_path.is_file():
            continue

        try:
            document = extract_pdf_text(
                pdf_path,
                source_url=item["source_url"],
                title=item["title"],
            )
            results.extend(search_document(document, query, limit=limit))
        except (OSError, ValueError):
            # Один повреждённый PDF не должен останавливать поиск по остальным.
            continue

    results.sort(key=lambda result: (-result.score, result.page_number))
    return results[:limit]
