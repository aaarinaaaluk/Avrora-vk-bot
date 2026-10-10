import re

from pydantic import BaseModel

from app.sources.pdf_reader import PDFDocument


class SearchResult(BaseModel):
    page_number: int
    text: str
    matched_terms: list[str]
    score: int


def search_document(
    document: PDFDocument,
    query: str,
    limit: int = 5,
) -> list[SearchResult]:
    """Ищет совпадения по словам и возвращает страницы с контекстом."""
    if limit < 1:
        raise ValueError("limit должен быть не меньше 1")

    terms = {
        word.lower()
        for word in re.findall(r"\w+", query.lower())
        if len(word) > 2
    }

    if not terms:
        return []

    results = []

    for page in document.pages:
        page_words = {
            word.lower()
            for word in re.findall(r"\w+", page.text.lower())
        }
        matched = sorted(terms.intersection(page_words))

        if matched:
            results.append(
                SearchResult(
                    page_number=page.page_number,
                    text=page.text,
                    matched_terms=matched,
                    score=len(matched),
                )
            )

    results.sort(key=lambda item: (-item.score, item.page_number))
    return results[:limit]
