"""Быстрый поиск по разрешённым русскоязычным локальным PDF."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.sources.pdf_reader import PDFDocument, extract_pdf_text
from app.sources.text_search import SearchResult, search_document


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
DOCUMENT_CATALOG_PATH = PROJECT_ROOT / "data" / "document_catalog.json"


def _normalise_terms(text: str) -> set[str]:
    """Упрощённая нормализация русских окончаний для предварительного отбора."""
    suffixes = (
        "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими",
        "ать", "ять", "ов", "ев", "ей", "ам", "ям", "ах", "ях",
        "ы", "и", "а", "я", "у", "е", "ом", "ем", "ой", "ий", "ый",
    )
    terms: set[str] = set()
    for word in re.findall(r"[а-яёa-z0-9]+", text.casefold()):
        if len(word) <= 2 and not word.isdigit():
            continue
        stem = word
        for suffix in suffixes:
            if len(stem) - len(suffix) >= 4 and stem.endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        terms.add(stem)
    return terms


def _document_relevance_score(item: dict[str, Any], query: str) -> int:
    """Оценивает релевантность по каталогу, не открывая сам PDF."""
    query_terms = _normalise_terms(query)
    # Общие слова не должны запускать чтение тематически чужого PDF:
    # например, слово «диета» само по себе не делает рекомендации по целиакии
    # релевантными утверждению о средиземноморской диете.
    generic_terms = {
        "диет", "питан", "рацион", "заболев", "болезн", "риск", "снижа",
        "повыш", "человек", "дет", "взросл", "общ", "организм", "здоров",
        "может", "могут", "связан", "связ", "состояни", "польз", "эффект",
        "привод", "развит", "уровен", "контрол", "рекомендац", "влияни",
    }
    query_terms = query_terms - generic_terms
    if not query_terms:
        return 0

    title_terms = _normalise_terms(f"{item.get('title', '')} {item.get('filename', '')}") - generic_terms
    title_hits = len(query_terms.intersection(title_terms))

    configured_keywords = item.get("search_keywords", [])
    keyword_terms: set[str] = set()
    if isinstance(configured_keywords, list):
        for keyword in configured_keywords:
            if isinstance(keyword, str) and keyword.strip():
                keyword_terms.update(_normalise_terms(keyword) - generic_terms)
    keyword_hits = len(query_terms.intersection(keyword_terms))

    # Название конкретной рекомендации важнее общего тематического ключа.
    return title_hits * 4 + keyword_hits * 2


def _document_matches_query(item: dict[str, Any], query: str) -> bool:
    """Совместимый булев фильтр для предварительного отбора PDF."""
    return _document_relevance_score(item, query) > 0


@lru_cache(maxsize=32)
def _extract_pdf_text_cached(
    path: str,
    source_url: str,
    title: str,
    mtime_ns: int,
    size: int,
) -> PDFDocument:
    """Кэширует извлечённый текст; изменение файла автоматически сбрасывает ключ."""
    return extract_pdf_text(path, source_url=source_url, title=title)


def load_document_catalog() -> list[dict[str, Any]]:
    """Возвращает только включённые русскоязычные PDF с безопасными именами."""
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

        # ВОЗ проверяется по русскоязычным веб-страницам, не по английским PDF.
        if item.get("source_id") == "who":
            continue
        language = item.get("language")
        if isinstance(language, str) and language.strip().lower() not in {"ru", "rus", "russian"}:
            continue

        enabled_documents.append(item)

    return enabled_documents


def search_documents(query: str, limit: int = 5) -> list[SearchResult]:
    """Ищет в тематически подходящих PDF; неразрешённые файлы не открываются."""
    if limit < 1:
        raise ValueError("limit должен быть не меньше 1")
    if not query.strip() or not DOCUMENTS_DIR.is_dir():
        return []

    results: list[SearchResult] = []
    registered_names: set[str] = set()

    candidates = []
    for item in load_document_catalog():
        score = _document_relevance_score(item, query)
        if score <= 0:
            continue
        filename = item["filename"]
        if filename in registered_names:
            continue
        registered_names.add(filename)
        candidates.append((score, item))

    # Клинические рекомендации бывают сотнями страниц. Даже если каталог
    # содержит несколько совпадений, разбираем только 2 наиболее подходящих PDF.
    # Текст каждого выбранного файла кэшируется между последующими запросами.
    candidates.sort(key=lambda pair: (-pair[0], pair[1].get("title", "")))
    for _, item in candidates[:2]:
        filename = item["filename"]
        pdf_path = DOCUMENTS_DIR / filename
        if not pdf_path.is_file():
            continue

        try:
            stat = pdf_path.stat()
            document = _extract_pdf_text_cached(
                str(pdf_path), item["source_url"], item["title"],
                stat.st_mtime_ns, stat.st_size,
            )
            results.extend(search_document(document, query, limit=limit))
        except (OSError, ValueError):
            # Один повреждённый PDF не должен останавливать поиск по остальным.
            continue

    results.sort(key=lambda result: (-result.score, result.page_number))
    return results[:limit]
